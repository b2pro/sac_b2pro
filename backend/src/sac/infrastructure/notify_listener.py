import asyncio
import contextlib
import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL = "sac_notifications"

# Unico valor que circula nas filas. O evento e um SINAL, nao um dado: o
# cliente refaz o GET /api/notificacoes ao receber, porque a tabela e a fonte
# de verdade (e o payload do NOTIFY tem limite de 8000 bytes no Postgres).
EVENT_NEW = "nova"

# Cada fila guarda no maximo um sinal pendente (ver _dispatch: coalescencia).
_QUEUE_MAXSIZE = 1

# Intervalo entre checagens de saude da conexao no watchdog. Nao e um retry:
# com a conexao viva, e so um sleep barato -- nunca um busy loop.
_HEALTHCHECK_SECONDS = 5.0
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0


def asyncpg_dsn(url: str) -> str:
    """Traduz a URL do SQLAlchemy para o DSN aceito pelo asyncpg puro.

    Settings.database_url usa o formato do SQLAlchemy
    (postgresql+asyncpg://...), mas asyncpg.connect nao entende o sufixo de
    driver e falha com InvalidCatalogName/scheme invalido. Trocamos so o
    prefixo exato -- nao um replace("+asyncpg", "") solto -- para nao mexer em
    senha ou nome de banco que por acaso contenham a mesma sequencia. URL que
    ja venha sem o sufixo passa intacta.
    """
    prefixo = "postgresql+asyncpg://"
    if url.startswith(prefixo):
        return "postgresql://" + url.removeprefix(prefixo)
    return url


class NotificationListener:
    """Uma conexao asyncpg em LISTEN por instancia do backend, com registry em
    memoria de filas SSE por (tenant_slug, user_id).

    Por que uma conexao unica e nao uma por stream: LISTEN ocupa uma conexao
    inteira do Postgres pelo tempo que durar; abrir uma por aba aberta esgotaria
    o pool. O canal tambem e unico e global (o PgNotifyPublisher emite sempre em
    sac_notifications) -- quem filtra tenant e destinatario e este registry, em
    memoria, o que e ordens de grandeza mais barato do que multiplicar LISTENs.

    Consequencia arquitetural: o registry vale para ESTA instancia. Com varias
    instancias atras de um balanceador, cada uma faz o seu LISTEN e o Postgres
    entrega o NOTIFY a todas; cada uma acorda so os streams que ela mesma
    atende. Nao ha estado compartilhado a sincronizar.

    start() e lazy e idempotente de proposito: create_app nao pode depender de
    banco disponivel (a app sobe e responde /health sem Postgres), entao a
    conexao so e aberta no primeiro subscribe.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._queues: dict[tuple[str, UUID], set[asyncio.Queue[str]]] = {}
        self._conn: asyncpg.Connection[Any] | None = None
        self._task: asyncio.Task[None] | None = None
        # asyncio.Lock nao amarra event loop na construcao (3.10+), por isso
        # pode ser criado em create_app, fora de qualquer loop.
        self._lock = asyncio.Lock()

    async def subscribe(self, tenant_slug: str, user_id: UUID) -> asyncio.Queue[str]:
        """Registra uma fila para o par (tenant, usuario) e devolve ela.

        O start() acontece ANTES de registrar e o chamador (o endpoint SSE)
        chama isso antes de responder os headers: assim, quando o cliente ve o
        stream aberto, o LISTEN ja esta ativo e nenhum NOTIFY posterior se
        perde na janela entre 'assinei' e 'estou ouvindo'.
        """
        await self.start()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._queues.setdefault((tenant_slug, user_id), set()).add(queue)
        return queue

    def unsubscribe(self, tenant_slug: str, user_id: UUID, queue: asyncio.Queue[str]) -> None:
        """Remove a fila do registry. Sincrono e tolerante a chave/fila ausente
        porque e chamado do finally do gerador SSE, que tambem roda quando o
        cliente cai no meio (ou quando stop() ja limpou o registry) -- levantar
        ali mascararia o erro original do stream."""
        key = (tenant_slug, user_id)
        filas = self._queues.get(key)
        if filas is None:
            return
        filas.discard(queue)
        if not filas:
            del self._queues[key]

    async def start(self) -> None:
        """Conecta, faz LISTEN e sobe o watchdog de reconexao. Idempotente.

        O fast path sem lock evita serializar todos os subscribes depois do
        primeiro; o lock com nova checagem dentro (double-checked locking)
        garante que dez streams subindo juntos abram UMA conexao, nao dez.

        A primeira conexao e aguardada (nao delegada ao watchdog) para que uma
        falha de banco apareca como erro do request -- e nao como um stream
        aberto que nunca entrega nada. O EventSource do navegador reconecta
        sozinho nesse caso.
        """
        if self._task is not None:
            return
        async with self._lock:
            if self._task is not None:
                return
            await self._connect()
            self._task = asyncio.create_task(self._watchdog())

    async def stop(self) -> None:
        """Cancela o watchdog e fecha a conexao. Idempotente.

        Ordem importa: cancelar a task ANTES de fechar a conexao, senao o
        watchdog veria a conexao fechada e abriria outra durante o shutdown.
        """
        async with self._lock:
            task, self._task = self._task, None
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            conn, self._conn = self._conn, None
            if conn is not None and not conn.is_closed():
                with contextlib.suppress(Exception):
                    await conn.close()
            # solta as filas: um stream sobrevivente sai no proximo heartbeat e
            # o seu unsubscribe e tolerante a chave ausente.
            self._queues.clear()

    async def _connect(self) -> None:
        conn: asyncpg.Connection[Any] = await asyncpg.connect(dsn=self._dsn)
        try:
            await conn.add_listener(NOTIFY_CHANNEL, self._on_notify)
        except Exception:
            # sem o LISTEN a conexao nao serve para nada: nao deixar pendurada
            await conn.close()
            raise
        self._conn = conn

    async def _watchdog(self) -> None:
        """Task unica (garantida pelo lock em start) que mantem o LISTEN vivo.

        Nao adquire self._lock em nenhum ponto: stop() cancela esta task
        segurando o lock, e pedir o mesmo lock aqui travaria o shutdown.

        Checa is_closed periodicamente em vez de so reagir a
        add_termination_listener porque queda de rede/proxy pode fechar a
        conexao sem que o callback de terminacao seja util para reagendar o
        LISTEN. O backoff so cresce em falha de reconexao (1s, 2s, ... 30s) e
        volta a 1s quando reconecta.
        """
        delay = _BACKOFF_INITIAL_SECONDS
        while True:
            try:
                if self._conn is None or self._conn.is_closed():
                    await self._connect()
                    logger.info("listener reconectado ao canal %s", NOTIFY_CHANNEL)
                    delay = _BACKOFF_INITIAL_SECONDS
                await asyncio.sleep(_HEALTHCHECK_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "falha ao reconectar o listener de %s; nova tentativa em %.0fs",
                    NOTIFY_CHANNEL,
                    delay,
                    exc_info=True,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _BACKOFF_MAX_SECONDS)

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: object) -> None:
        """Callback do asyncpg. Roda no event loop da conexao -- que aqui e o
        mesmo loop da app, porque a conexao e aberta de dentro de um request --,
        entao pode tocar as filas direto, sem call_soon_threadsafe. Nada de I/O
        ou espera aqui: bloquear este callback atrasaria TODO o trafego da
        conexao de LISTEN."""
        self._dispatch(payload if isinstance(payload, str) else str(payload))

    def _dispatch(self, payload: str) -> None:
        """Roteia o payload do canal para as filas dos destinatarios.

        Nunca levanta: um payload malformado (outro processo escrevendo no mesmo
        canal, versao antiga do publisher) so pode gerar log. Deixar a excecao
        subir mataria o callback e, com ele, o tempo real de todos os streams.
        """
        try:
            data = json.loads(payload)
            tenant = data["tenant"]
            users = data["users"]
        except (ValueError, TypeError, KeyError, IndexError):
            logger.warning("payload invalido no canal %s: %r", NOTIFY_CHANNEL, payload)
            return
        if not isinstance(tenant, str) or not isinstance(users, list):
            logger.warning("payload fora do formato no canal %s: %r", NOTIFY_CHANNEL, payload)
            return
        for raw in users:
            try:
                user_id = UUID(str(raw))
            except (ValueError, AttributeError):
                logger.warning("destinatario invalido no canal %s: %r", NOTIFY_CHANNEL, raw)
                continue
            self._push(tenant, user_id)

    def _push(self, tenant_slug: str, user_id: UUID) -> None:
        # tuple(...) porque o unsubscribe de um stream que caiu pode mutar o set
        # entre iteracoes.
        for queue in tuple(self._queues.get((tenant_slug, user_id), ())):
            try:
                queue.put_nowait(EVENT_NEW)
            except asyncio.QueueFull:
                # COALESCENCIA em vez de fila crescendo ou descarte do mais
                # antigo: como o sinal nao carrega dado, "ja existe um aviso
                # pendente" e exatamente equivalente a "chegaram tres avisos" --
                # o cliente vai reler a lista completa de qualquer jeito. Com
                # maxsize=1 o consumidor lento nao consome memoria e o callback
                # nunca espera (put_nowait, jamais await put).
                pass
