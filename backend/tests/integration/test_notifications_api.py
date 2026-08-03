import asyncio
import json

import asyncpg
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.entities import Tenant
from sac.domain.permissions import Role
from tests.integration.conftest import TEST_DB_URL
from tests.integration.helpers import seed_link, seed_provisioned_tenant, seed_user, token_for


async def _setup_dupla(
    session: AsyncSession, engine: AsyncEngine, slug: str
) -> tuple[dict[str, str], dict[str, str], Tenant]:
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    a = await seed_user(session, email=f"a@{slug}.com", name="Usuario A")
    await seed_link(session, user=a, tenant=tenant, role=Role.ADMIN)
    b = await seed_user(session, email=f"b@{slug}.com", name="Usuario B")
    await seed_link(session, user=b, tenant=tenant, role=Role.SUPERVISOR)
    headers_a = token_for(a, tenant_slug=tenant.slug, role=Role.ADMIN)
    headers_b = token_for(b, tenant_slug=tenant.slug, role=Role.SUPERVISOR)
    return headers_a, headers_b, tenant


async def _abrir_ticket(client: AsyncClient, headers: dict[str, str]) -> str:
    # sem attendant_user_id explicito: CreateTicketUseCase atribui o proprio
    # ator, entao quem abre o ticket vira o atendente (destinatario do
    # fan-out de comentario de outra pessoa).
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets",
        json={"brand_id": marcas[0]["id"], "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_comentario_gera_notificacao_lista_contador_e_marcar_lidas(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_a, headers_b, tenant = await _setup_dupla(session, engine, "notifapi1")
    ticket_id = await _abrir_ticket(client, headers_a)

    # antes do comentario, contador de A esta zerado
    res = await client.get("/api/notificacoes/contador", headers=headers_a)
    assert res.status_code == 200
    assert res.json() == {"nao_lidas": 0}

    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios",
        json={"body": "comentario de B"},
        headers=headers_b,
    )
    assert res.status_code == 201

    res = await client.get("/api/notificacoes/contador", headers=headers_a)
    assert res.json() == {"nao_lidas": 1}

    res = await client.get("/api/notificacoes", headers=headers_a)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["ticket_id"] == ticket_id
    assert item["ticket_number"] >= 1
    assert item["type"] == "comentario"
    assert item["read_at"] is None
    notif_id = item["id"]

    # notificacoes de A nao aparecem para B (cada um le so as proprias)
    res = await client.get("/api/notificacoes", headers=headers_b)
    assert res.json() == {"items": [], "total": 0}
    res = await client.get("/api/notificacoes/contador", headers=headers_b)
    assert res.json() == {"nao_lidas": 0}

    # marcar-lidas sem ids (null) marca todas as de A e zera o contador
    res = await client.post("/api/notificacoes/marcar-lidas", json={}, headers=headers_a)
    assert res.status_code == 204

    res = await client.get("/api/notificacoes/contador", headers=headers_a)
    assert res.json() == {"nao_lidas": 0}
    res = await client.get("/api/notificacoes", headers=headers_a)
    lida = res.json()["items"][0]
    assert lida["id"] == notif_id
    assert lida["read_at"] is not None


async def test_apenas_nao_lidas_e_paginacao_de_notificacoes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_a, headers_b, _ = await _setup_dupla(session, engine, "notifapi2")
    ticket_1 = await _abrir_ticket(client, headers_a)
    ticket_2 = await _abrir_ticket(client, headers_a)

    for ticket_id in (ticket_1, ticket_2):
        res = await client.post(
            f"/api/tickets/{ticket_id}/comentarios",
            json={"body": "de B"},
            headers=headers_b,
        )
        assert res.status_code == 201

    res = await client.get("/api/notificacoes", headers=headers_a)
    assert res.json()["total"] == 2

    res = await client.get(
        "/api/notificacoes", params={"page": 1, "per_page": 1}, headers=headers_a
    )
    body = res.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1

    notif_id = body["items"][0]["id"]
    res = await client.post(
        "/api/notificacoes/marcar-lidas", json={"ids": [notif_id]}, headers=headers_a
    )
    assert res.status_code == 204

    res = await client.get(
        "/api/notificacoes", params={"apenas_nao_lidas": True}, headers=headers_a
    )
    body = res.json()
    assert body["total"] == 1
    assert all(item["read_at"] is None for item in body["items"])


async def test_marcar_lidas_ignora_ids_de_notificacao_de_outro_usuario(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    # seguranca: user_id vem sempre do token. B nao pode marcar como lida uma
    # notificacao que pertence a A so por conhecer o id.
    headers_a, headers_b, _ = await _setup_dupla(session, engine, "notifapi3")
    ticket_id = await _abrir_ticket(client, headers_a)
    await client.post(
        f"/api/tickets/{ticket_id}/comentarios", json={"body": "de B"}, headers=headers_b
    )
    notif_id_a = (await client.get("/api/notificacoes", headers=headers_a)).json()["items"][0]["id"]

    res = await client.post(
        "/api/notificacoes/marcar-lidas", json={"ids": [notif_id_a]}, headers=headers_b
    )
    assert res.status_code == 204

    res = await client.get("/api/notificacoes/contador", headers=headers_a)
    assert res.json() == {"nao_lidas": 1}


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    return "postgresql://" + sqlalchemy_url.removeprefix("postgresql+asyncpg://")


async def test_publisher_pg_notify_publica_payload_no_canal_global(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    # valor testavel aqui: o publish() de fato dispara um pg_notify visivel a
    # outra conexao, com o payload exato do spec ({"tenant", "users"}) e sem
    # conteudo da notificacao. LISTEN em conexao asyncpg separada prova
    # comportamento real (nao so que o SQL foi montado).
    headers_a, headers_b, tenant = await _setup_dupla(session, engine, "notifapi4")
    ticket_id = await _abrir_ticket(client, headers_a)

    listener = await asyncpg.connect(dsn=_asyncpg_dsn(TEST_DB_URL))
    received: list[str] = []
    try:
        await listener.add_listener("sac_notifications", lambda *args: received.append(args[-1]))

        res = await client.post(
            f"/api/tickets/{ticket_id}/comentarios",
            json={"body": "de B"},
            headers=headers_b,
        )
        assert res.status_code == 201

        for _ in range(30):
            if received:
                break
            await asyncio.sleep(0.1)
    finally:
        await listener.close()

    assert received, "nenhuma notificacao pg_notify chegou no canal sac_notifications"
    payload = json.loads(received[-1])
    # o payload nao carrega titulo/snippet, so tenant e destinatarios
    assert set(payload.keys()) == {"tenant", "users"}
    assert payload["tenant"] == tenant.slug
    assert isinstance(payload["users"], list)
    assert len(payload["users"]) == 1
