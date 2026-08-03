import asyncio
import json
from uuid import UUID, uuid4

import pytest

from sac.infrastructure.notify_listener import NotificationListener, asyncpg_dsn


class _ListenerSemBanco(NotificationListener):
    """Sobrescreve SO a conexao: registry, dispatch e unsubscribe sao os reais.

    O valor destes testes esta na logica de roteamento em memoria, que nao
    precisa de Postgres. Herdar e neutralizar start() e melhor do que chamar
    o registry direto porque mantem o caminho publico (subscribe) sob teste.
    """

    async def start(self) -> None:
        return None


def test_asyncpg_dsn_remove_o_sufixo_do_driver_do_sqlalchemy() -> None:
    assert (
        asyncpg_dsn("postgresql+asyncpg://sac:sac@localhost:5432/sac")
        == "postgresql://sac:sac@localhost:5432/sac"
    )


def test_asyncpg_dsn_mantem_url_que_ja_esta_sem_sufixo() -> None:
    assert (
        asyncpg_dsn("postgresql://sac:sac@localhost:5432/sac")
        == "postgresql://sac:sac@localhost:5432/sac"
    )


def _payload(tenant: str, *users: UUID) -> str:
    return json.dumps({"tenant": tenant, "users": [str(u) for u in users]})


async def test_dispatch_entrega_apenas_nas_filas_dos_usuarios_do_payload() -> None:
    listener = _ListenerSemBanco("postgresql://ignorado")
    user_a, user_b = uuid4(), uuid4()
    fila_a = await listener.subscribe("acme", user_a)
    fila_b = await listener.subscribe("acme", user_b)
    fila_outro_tenant = await listener.subscribe("outra", user_a)

    listener._dispatch(_payload("acme", user_a))

    assert fila_a.qsize() == 1
    assert fila_b.qsize() == 0
    assert fila_outro_tenant.qsize() == 0


async def test_dispatch_entrega_em_todas_as_filas_do_mesmo_par() -> None:
    # varias abas do mesmo usuario: cada stream tem a sua fila
    listener = _ListenerSemBanco("postgresql://ignorado")
    user = uuid4()
    aba_1 = await listener.subscribe("acme", user)
    aba_2 = await listener.subscribe("acme", user)

    listener._dispatch(_payload("acme", user))

    assert aba_1.qsize() == 1
    assert aba_2.qsize() == 1


async def test_dispatch_coalesce_eventos_quando_o_consumidor_esta_lento() -> None:
    # o evento nao carrega dado (o cliente refaz o GET), entao dois avisos
    # pendentes valem o mesmo que um: a fila fica em 1 e o callback nao bloqueia.
    listener = _ListenerSemBanco("postgresql://ignorado")
    user = uuid4()
    fila = await listener.subscribe("acme", user)

    for _ in range(50):
        listener._dispatch(_payload("acme", user))

    assert fila.qsize() == 1


@pytest.mark.parametrize(
    "payload",
    [
        "nao e json",
        "",
        "[]",
        '{"tenant": "acme"}',
        '{"users": ["x"]}',
        '{"tenant": 7, "users": []}',
        '{"tenant": "acme", "users": "nao e lista"}',
        '{"tenant": "acme", "users": ["nao-e-uuid"]}',
    ],
)
async def test_dispatch_ignora_payload_malformado_sem_derrubar_o_listener(payload: str) -> None:
    listener = _ListenerSemBanco("postgresql://ignorado")
    user = uuid4()
    fila = await listener.subscribe("acme", user)

    listener._dispatch(payload)
    assert fila.qsize() == 0

    # o listener segue vivo: um payload valido depois do lixo ainda entrega
    listener._dispatch(_payload("acme", user))
    assert fila.qsize() == 1


async def test_unsubscribe_remove_a_fila_e_e_tolerante_a_repeticao() -> None:
    listener = _ListenerSemBanco("postgresql://ignorado")
    user = uuid4()
    fila = await listener.subscribe("acme", user)

    listener.unsubscribe("acme", user, fila)
    listener._dispatch(_payload("acme", user))
    assert fila.qsize() == 0

    # cliente que cai no meio pode levar o finally a chamar duas vezes
    listener.unsubscribe("acme", user, fila)
    listener.unsubscribe("acme", uuid4(), fila)


async def test_stop_sem_start_nao_falha_e_e_idempotente() -> None:
    listener = NotificationListener("postgresql://ignorado")
    await listener.stop()
    await listener.stop()


class _ConexaoFalsa:
    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        return None


async def test_start_concorrente_abre_uma_unica_conexao() -> None:
    # o lock interno existe para isso: dez streams subindo juntos no primeiro
    # request nao podem virar dez conexoes LISTEN.
    conexoes: list[object] = []

    class _ContaConexoes(NotificationListener):
        async def _connect(self) -> None:
            await asyncio.sleep(0.01)  # janela para a corrida acontecer
            conexoes.append(object())
            self._conn = _ConexaoFalsa()  # type: ignore[assignment]

    listener = _ContaConexoes("postgresql://ignorado")
    try:
        await asyncio.gather(*(listener.start() for _ in range(10)))
        assert len(conexoes) == 1
    finally:
        await listener.stop()


async def test_stop_cancela_a_task_de_reconexao() -> None:
    # nenhuma task orfa entre testes: stop() tem de encerrar o watchdog.
    class _SemBancoMasComTask(NotificationListener):
        async def _connect(self) -> None:
            self._conn = _ConexaoFalsa()  # type: ignore[assignment]

    listener = _SemBancoMasComTask("postgresql://ignorado")
    await listener.start()
    task = listener._task
    assert task is not None

    await listener.stop()
    assert task.done()
    assert listener._task is None
