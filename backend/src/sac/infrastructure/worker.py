import argparse
import asyncio
import logging
import signal
from datetime import UTC, datetime
from types import FrameType
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_attachments import StoragePort
from sac.application.use_cases.attachments import ExpirePendingUseCase
from sac.application.use_cases.previews import PermanentJobError, ProcessPreviewJobUseCase
from sac.domain.attachments import PreviewJob
from sac.domain.entities import TenantStatus
from sac.infrastructure.db import build_engine
from sac.infrastructure.images import generate_previews
from sac.infrastructure.models import TenantModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    build_attachment_repos,
)
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import build_storage

logger = logging.getLogger(__name__)


async def _bind_tenant_schema(session: AsyncSession, slug: str) -> None:
    """Aponta a conexao desta sessao para o schema real do tenant do job que
    ACABOU de ser reivindicado por claim_next - nunca para um slug adivinhado
    antes do claim. Connection.execution_options muta a conexao viva em vigor
    (confirmado: a mesma conexao e devolvida por session.connection() durante
    toda a transacao), entao a traducao vale para as queries de anexo/foto
    feitas depois, na MESMA transacao que fez o claim (rota (a) do finding 1:
    resolver o schema depois do claim, e nao antes, elimina a divergencia
    entre "job mais antigo, sem lock" e "job realmente reivindicado" quando o
    mais antigo esta bloqueado por outro worker)."""
    conn = await session.connection()
    await conn.execution_options(schema_translate_map={"tenant": f"t_{slug}"})


def _same_tenant[T](slug: str, job: PreviewJob, repo: T) -> T:
    """attachments_for/photos_for recebem do use case o tenant_slug do job
    que ele mesmo reivindicou (sempre o job desta chamada, ver
    _PreClaimedJobs.claim_next). Aqui honramos esse argumento de verdade: em
    vez de descartar o slug e devolver sempre o mesmo repositorio (o bug do
    finding 1), confirmamos que bate com o tenant para o qual a sessao foi
    traduzida.

    Uma divergencia e erro de programacao: retry nunca resolve, e insistir
    gravaria dados no tenant errado. Por isso levantamos PermanentJobError, que
    o use case reconhece e esgota na primeira tentativa, com a mensagem gravada
    em last_error. Um AssertionError aqui nao serviria: ele cairia no
    `except Exception` do use case e o job seria reagendado 5 vezes com backoff,
    disfarcando o bug de instabilidade transitoria."""
    if slug != job.tenant_slug:
        raise PermanentJobError(
            f"resolucao de tenant inconsistente: sessao traduzida para "
            f"{job.tenant_slug!r} mas o use case pediu repositorio de {slug!r}"
        )
    return repo


class _PreClaimedJobs:
    """Adapta SqlPreviewJobRepository para o use case dentro de run_once: o
    job ja foi reivindicado (claim_next) ANTES do schema da sessao ser
    vinculado ao tenant real (_bind_tenant_schema so pode rodar depois que
    sabemos qual job foi mesmo travado), entao o use case nao deve reivindicar
    de novo - so precisa do job ja conhecido. add/get/mark_done/mark_failed
    passam direto para o repositorio real."""

    def __init__(self, inner: SqlPreviewJobRepository, job: PreviewJob) -> None:
        self._inner = inner
        self._job = job

    async def add(self, job: PreviewJob) -> None:
        await self._inner.add(job)

    async def get(self, job_id: UUID) -> PreviewJob | None:
        return await self._inner.get(job_id)

    async def claim_next(self, now: datetime) -> PreviewJob | None:
        return self._job

    async def mark_done(self, job_id: UUID) -> None:
        await self._inner.mark_done(job_id)

    async def mark_failed(
        self, job_id: UUID, error: str, next_attempt_at: datetime, exhausted: bool
    ) -> None:
        await self._inner.mark_failed(job_id, error, next_attempt_at, exhausted)


async def run_once(engine: AsyncEngine, storage: StoragePort, settings: Settings) -> bool:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        real_jobs = SqlPreviewJobRepository(session)
        job = await real_jobs.claim_next(now)
        if job is None:
            return False
        atualizado: PreviewJob | None = None
        try:
            await _bind_tenant_schema(session, job.tenant_slug)
            repos = build_attachment_repos(session)
            use_case = ProcessPreviewJobUseCase(
                jobs=_PreClaimedJobs(real_jobs, job),
                storage=storage,
                generate=generate_previews,
                attachments_for=lambda slug: _same_tenant(slug, job, repos.attachments),
                photos_for=lambda slug: _same_tenant(slug, job, repos.photos),
            )
            processou = await use_case.execute(now)
            # leitura so para observabilidade (log abaixo) - nao decide nada,
            # apenas relata o que o use case ja decidiu e persistiu.
            atualizado = await real_jobs.get(job.id)
            await session.commit()
        except Exception:
            logger.exception(
                "falha inesperada ao processar job de preview id=%s tenant=%s",
                job.id,
                job.tenant_slug,
            )
            await session.rollback()
            raise
    if atualizado is not None:
        logger.info(
            "job de preview processado id=%s tenant=%s status=%s tentativas=%d%s",
            atualizado.id,
            atualizado.tenant_slug,
            atualizado.status,
            atualizado.attempts,
            f" erro={atualizado.last_error}" if atualizado.last_error else "",
        )
    return processou


async def _expire_pending(
    engine: AsyncEngine, storage: StoragePort, slug: str, minutes: int
) -> int:
    translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        repos = build_attachment_repos(session)
        total = await ExpirePendingUseCase(repos.attachments, storage, minutes=minutes).execute()
        await session.commit()
        return total


async def _active_tenant_slugs(engine: AsyncEngine) -> list[str]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = await session.scalars(
            select(TenantModel.slug).where(TenantModel.status != str(TenantStatus.INATIVA))
        )
        return list(rows)


async def expire_pending_all(engine: AsyncEngine, storage: StoragePort, minutes: int) -> None:
    """Varre todos os tenants ativos. A falha de UM tenant (ex.: tenant ativo
    cujo schema nao foi provisionado) e logada e a varredura segue: esta funcao
    roda dentro de run_forever, entao deixar a excecao subir mataria o processo,
    o restart traria o worker de volta na mesma falha e nenhuma preview seria
    gerada para nenhum tenant."""
    tenants = await _active_tenant_slugs(engine)
    total = 0
    falhas = 0
    for slug in tenants:
        try:
            total += await _expire_pending(engine, storage, slug, minutes)
        except Exception:  # noqa: BLE001 - um tenant ruim nao derruba a varredura
            falhas += 1
            logger.exception("falha ao expirar pendentes do tenant %s", slug)
    logger.info(
        "varredura de expiracao de pendentes: %d anexo(s) expirados em %d tenant(s) ativo(s), "
        "%d tenant(s) com falha",
        total,
        len(tenants),
        falhas,
    )


class _Shutdown:
    """Flag mutavel setada pelos handlers de SIGTERM/SIGINT. run_forever so
    consulta 'requested' ENTRE iteracoes do laco (nunca no meio do
    processamento de um job, que roda inteiro dentro de run_once) - assim
    'docker compose stop' encerra o loop depois do job em andamento, nunca no
    meio de uma transacao."""

    def __init__(self) -> None:
        self.requested = False

    def handle(self, signum: int, frame: FrameType | None) -> None:
        logger.info(
            "sinal %s recebido: worker vai parar apos o job em andamento",
            signal.Signals(signum).name,
        )
        self.requested = True


_shutdown = _Shutdown()


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _shutdown.handle)
    signal.signal(signal.SIGINT, _shutdown.handle)


async def run_forever(
    engine: AsyncEngine,
    storage: StoragePort,
    settings: Settings,
    interval_seconds: float = 2.0,
    expire_every_seconds: float = 300.0,
) -> None:
    logger.info(
        "worker de previews em execucao (poll=%.1fs, varredura de expiracao a cada %.0fs)",
        interval_seconds,
        expire_every_seconds,
    )
    proxima_expiracao = 0.0
    while not _shutdown.requested:
        agora = asyncio.get_running_loop().time()
        if agora >= proxima_expiracao:
            await expire_pending_all(engine, storage, settings.pending_expiration_minutes)
            proxima_expiracao = agora + expire_every_seconds
        processou = await run_once(engine, storage, settings)
        if not processou and not _shutdown.requested:
            await asyncio.sleep(interval_seconds)
    logger.info("worker de previews encerrado (sinal de parada recebido)")


async def _main_async(once: bool) -> None:
    settings = Settings()
    logger.info(
        "iniciando worker de previews: bucket=%s endpoint=%s once=%s",
        settings.s3_bucket,
        settings.s3_endpoint_url,
        once,
    )
    engine = build_engine(settings.database_url)
    storage = build_storage(settings)
    try:
        if once:
            processou = await run_once(engine, storage, settings)
            logger.info("execucao unica concluida: job_processado=%s", processou)
        else:
            await run_forever(engine, storage, settings)
    finally:
        await engine.dispose()
        logger.info("worker de previews finalizado")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _install_signal_handlers()
    parser = argparse.ArgumentParser(prog="sac-worker")
    parser.add_argument("--once", action="store_true", help="processa um job e sai")
    args = parser.parse_args()
    asyncio.run(_main_async(args.once))


if __name__ == "__main__":
    main()
