import asyncio
import contextlib
import json
from types import TracebackType
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from sac.interface.routers import notifications
from tests.integration.helpers import seed_link, seed_provisioned_tenant, seed_user, token_for

STREAM_PATH = "/api/notificacoes/stream"


class StreamSSE:
    """Consome o endpoint SSE falando ASGI direto com a app.

    Por que nao httpx: o ASGITransport do httpx 0.28 aguarda o app TERMINAR
    antes de montar a Response (ele acumula body_parts e afirma
    response_complete), entao client.stream() sobre um stream infinito nunca
    retorna -- o teste travaria para sempre. Falar ASGI na mao tambem e o unico
    jeito de simular o cliente caindo (http.disconnect), que e justamente o
    caminho que exercita o finally/unsubscribe do endpoint.

    O scope de proposito NAO declara asgi.spec_version >= 2.4: nessa versao o
    StreamingResponse do Starlette deixa de escutar http.disconnect e passa a
    esperar OSError no send, o que nao existe aqui.
    """

    def __init__(self, app: FastAPI, headers: dict[str, str], path: str = STREAM_PATH) -> None:
        self._app = app
        self._headers = headers
        self._path = path
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.frames: asyncio.Queue[str] = asyncio.Queue()
        self._corpo_enviado = False
        self._respondeu = asyncio.Event()
        self._desconectar = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "StreamSSE":
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._respondeu.wait(), timeout=10)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._desconectar.set()
        task = self._task
        self._task = None
        if task is not None:
            # o disconnect encerra o gerador; o cancel e a rede de seguranca
            # para o teste nunca deixar task pendurada.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _receive(self) -> dict[str, Any]:
        if not self._corpo_enviado:
            self._corpo_enviado = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._desconectar.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {k.decode(): v.decode() for k, v in message.get("headers", [])}
            self._respondeu.set()
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                await self.frames.put(bytes(body).decode())
            if not message.get("more_body", False):
                # resposta que termina sem stream (erro de auth, por exemplo)
                self._respondeu.set()

    async def _run(self) -> None:
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in self._headers.items()],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        }
        await self._app(scope, self._receive, self._send)

    async def proximo_frame(self, timeout: float) -> str:
        return await asyncio.wait_for(self.frames.get(), timeout=timeout)


async def _setup_dupla(
    session: AsyncSession, engine: AsyncEngine, slug: str
) -> tuple[dict[str, str], dict[str, str]]:
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    a = await seed_user(session, email=f"a@{slug}.com", name="Usuario A")
    await seed_link(session, user=a, tenant=tenant, role=Role.ADMIN)
    b = await seed_user(session, email=f"b@{slug}.com", name="Usuario B")
    await seed_link(session, user=b, tenant=tenant, role=Role.SUPERVISOR)
    return (
        token_for(a, tenant_slug=tenant.slug, role=Role.ADMIN),
        token_for(b, tenant_slug=tenant.slug, role=Role.SUPERVISOR),
    )


async def _abrir_ticket(client: AsyncClient, headers: dict[str, str]) -> str:
    # sem attendant_user_id: quem abre vira o atendente, ou seja, o destinatario
    # do fan-out do comentario do outro usuario.
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets",
        json={"brand_id": marcas[0]["id"], "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_stream_empurra_evento_quando_chega_notificacao(
    app: FastAPI, client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_a, headers_b = await _setup_dupla(session, engine, "notifsse1")
    ticket_id = await _abrir_ticket(client, headers_a)

    async with StreamSSE(app, headers_a) as stream:
        assert stream.status == 200
        assert stream.headers["content-type"].startswith("text/event-stream")

        # o subscribe (e portanto o LISTEN) acontece antes dos headers sairem,
        # entao o NOTIFY deste POST nao pode ser perdido por corrida.
        res = await client.post(
            f"/api/tickets/{ticket_id}/comentarios",
            json={"body": "comentario de B"},
            headers=headers_b,
        )
        assert res.status_code == 201

        frame = await stream.proximo_frame(timeout=10)

    assert frame.startswith("data: ")
    assert json.loads(frame.removeprefix("data: ").strip()) == {"tipo": "nova"}


async def test_stream_nao_entrega_evento_de_outro_usuario(
    app: FastAPI, client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    # B comenta no ticket de A: a notificacao e de A. O stream de B (mesmo
    # tenant, outro usuario) nao pode receber nada -- o par (tenant, user) vem
    # do token, nao da URL.
    headers_a, headers_b = await _setup_dupla(session, engine, "notifsse2")
    ticket_id = await _abrir_ticket(client, headers_a)

    async with StreamSSE(app, headers_b) as stream:
        assert stream.status == 200
        res = await client.post(
            f"/api/tickets/{ticket_id}/comentarios",
            json={"body": "comentario de B"},
            headers=headers_b,
        )
        assert res.status_code == 201

        with pytest.raises(TimeoutError):
            await stream.proximo_frame(timeout=2)


async def test_stream_manda_heartbeat_para_atravessar_proxies(
    app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # o intervalo real e de 25s; o teste encurta a constante do modulo para
    # provar o comentario ': ping' sem esperar meio minuto. O endpoint nao toca
    # no schema do tenant (o registry e em memoria), por isso um usuario sem
    # tenant provisionado basta.
    monkeypatch.setattr(notifications, "HEARTBEAT_SECONDS", 0.2)
    user = await seed_user(session, email="heartbeat@sse.com")
    headers = token_for(user, tenant_slug="notifsse3", role=Role.ADMIN)

    async with StreamSSE(app, headers) as stream:
        assert stream.status == 200
        frame = await stream.proximo_frame(timeout=10)

    assert frame == ": ping\n\n"


async def test_stream_libera_a_fila_quando_o_cliente_desconecta(
    app: FastAPI, session: AsyncSession
) -> None:
    # o finally do gerador tem de rodar mesmo com o cliente caindo, senao o
    # registry acumularia filas de streams mortos para sempre.
    user = await seed_user(session, email="desconecta@sse.com")
    headers = token_for(user, tenant_slug="notifsse4", role=Role.ADMIN)
    listener = app.state.notify_listener

    async with StreamSSE(app, headers) as stream:
        assert stream.status == 200
        assert len(listener._queues) == 1

    for _ in range(50):
        if not listener._queues:
            break
        await asyncio.sleep(0.05)
    assert listener._queues == {}


async def test_stream_exige_autenticacao(app: FastAPI, database: str) -> None:
    async with StreamSSE(app, {}) as stream:
        assert stream.status == 401
