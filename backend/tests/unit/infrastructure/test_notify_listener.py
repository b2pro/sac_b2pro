import asyncio
import json
from collections.abc import Callable
from uuid import UUID, uuid4

import asyncpg
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


class _ConexaoFake:
    """Conexao asyncpg de mentira. `prova` decide como ela responde ao
    SELECT 1 do watchdog: viva, pendurada (socket blackholed) ou com erro."""

    def __init__(self, prova: str = "viva") -> None:
        self._prova = prova
        self.terminada = False
        self.provas = 0

    def is_closed(self) -> bool:
        return self.terminada

    async def add_listener(self, canal: str, callback: object) -> None:
        self.canal = canal

    async def fetchval(self, sql: str) -> int:
        self.provas += 1
        if self._prova == "pendurada":
            await asyncio.sleep(60)
        if self._prova == "erro":
            raise ConnectionError("socket morto")
        return 1

    def terminate(self) -> None:
        self.terminada = True

    async def close(self) -> None:
        self.terminada = True


class _ListenerComConexaoFake(NotificationListener):
    """Substitui so o _connect: entrega conexoes fake na ordem de `provas`."""

    def __init__(self, *provas: str, **kwargs: float) -> None:
        super().__init__("postgresql://ignorado", **kwargs)
        self._provas = provas
        self.conexoes: list[_ConexaoFake] = []

    async def _connect(self) -> None:
        indice = len(self.conexoes)
        conn = _ConexaoFake(self._provas[indice] if indice < len(self._provas) else "viva")
        self.conexoes.append(conn)
        self._conn = conn  # type: ignore[assignment]


async def _esperar(condicao: Callable[[], bool], timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    limite = loop.time() + timeout
    while loop.time() < limite:
        if condicao():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condicao nao ocorreu no tempo esperado")


async def test_start_concorrente_abre_uma_unica_conexao() -> None:
    # o lock interno existe para isso: dez streams subindo juntos no primeiro
    # request nao podem virar dez conexoes LISTEN.
    conexoes: list[object] = []

    class _ContaConexoes(NotificationListener):
        async def _connect(self) -> None:
            await asyncio.sleep(0.01)  # janela para a corrida acontecer
            conexoes.append(object())
            self._conn = _ConexaoFake()  # type: ignore[assignment]

    listener = _ContaConexoes("postgresql://ignorado")
    try:
        await asyncio.gather(*(listener.start() for _ in range(10)))
        assert len(conexoes) == 1
    finally:
        await listener.stop()


async def test_stop_cancela_a_task_de_reconexao() -> None:
    # nenhuma task orfa entre testes: stop() tem de encerrar o watchdog.
    listener = _ListenerComConexaoFake()
    await listener.start()
    task = listener._task
    assert task is not None

    await listener.stop()
    assert task.done()
    assert listener._task is None


async def test_watchdog_reconecta_quando_a_conexao_nao_responde_a_prova_de_vida() -> None:
    # o cenario que is_closed() nao detecta: socket blackholed, conexao que
    # parece aberta e nunca mais entrega NOTIFY. O SELECT 1 com timeout e o que
    # transforma isso em reconexao.
    listener = _ListenerComConexaoFake(
        "pendurada", healthcheck_seconds=0.01, probe_timeout_seconds=0.05
    )
    try:
        await listener.start()
        assert len(listener.conexoes) == 1
        assert not listener.conexoes[0].is_closed()  # is_closed sozinho nao acusa

        await _esperar(lambda: len(listener.conexoes) == 2)
        # a conexao morta e terminada (nao close(), que penduraria no mesmo socket)
        assert listener.conexoes[0].terminada is True
        assert listener.conexoes[1].terminada is False
    finally:
        await listener.stop()


async def test_watchdog_reconecta_quando_a_prova_de_vida_da_erro() -> None:
    listener = _ListenerComConexaoFake("erro", healthcheck_seconds=0.01, probe_timeout_seconds=0.05)
    try:
        await listener.start()
        await _esperar(lambda: len(listener.conexoes) == 2)
        assert listener.conexoes[0].terminada is True
    finally:
        await listener.stop()


async def test_watchdog_mantem_a_conexao_viva_sem_reconectar() -> None:
    # a prova de vida nao pode virar churn: conexao que responde e mantida.
    listener = _ListenerComConexaoFake("viva", healthcheck_seconds=0.01, probe_timeout_seconds=0.5)
    try:
        await listener.start()
        await _esperar(lambda: listener.conexoes[0].provas >= 3)
        assert len(listener.conexoes) == 1
        assert listener.conexoes[0].terminada is False
    finally:
        await listener.stop()


async def test_reconexao_acorda_os_inscritos_para_resincronizar() -> None:
    # NOTIFY emitido durante a janela de queda esta perdido para sempre; sem o
    # resync o stream aberto ficaria obsoleto ate o proximo evento.
    listener = _ListenerComConexaoFake(
        "pendurada", healthcheck_seconds=0.01, probe_timeout_seconds=0.05
    )
    try:
        fila = await listener.subscribe("acme", uuid4())
        assert fila.qsize() == 0

        await _esperar(lambda: len(listener.conexoes) == 2)
        await _esperar(lambda: fila.qsize() == 1)
    finally:
        await listener.stop()


@pytest.mark.parametrize("falha", [asyncio.CancelledError, RuntimeError])
async def test_connect_interrompido_nao_deixa_conexao_orfa(
    monkeypatch: pytest.MonkeyPatch, falha: type[BaseException]
) -> None:
    # o caso critico e o CancelledError (BaseException, que um except Exception
    # nao pegaria): interrompido entre o connect retornar e o self._conn = conn,
    # a conexao ficaria viva e invisivel para o stop() -- socket LISTEN orfao no
    # servidor. Exercita o _connect REAL, com asyncpg.connect trocado.
    class _ConexaoQueFalhaNoListen(_ConexaoFake):
        async def add_listener(self, canal: str, callback: object) -> None:
            raise falha

    conn = _ConexaoQueFalhaNoListen()

    async def _fake_connect(*args: object, **kwargs: object) -> _ConexaoFake:
        return conn

    monkeypatch.setattr(asyncpg, "connect", _fake_connect)
    listener = NotificationListener("postgresql://ignorado")

    with pytest.raises(falha):
        await listener.start()

    assert conn.terminada is True
    assert listener._conn is None
    assert listener._task is None  # nao deixa watchdog para tras
