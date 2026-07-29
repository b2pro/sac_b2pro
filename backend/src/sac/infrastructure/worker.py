import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.application.ports_attachments import StoragePort
from sac.application.use_cases.attachments import ExpirePendingUseCase
from sac.application.use_cases.previews import ProcessPreviewJobUseCase
from sac.domain.attachments import PreviewJobStatus
from sac.infrastructure.db import build_engine
from sac.infrastructure.images import generate_previews
from sac.infrastructure.models import PreviewJobModel, TenantModel
from sac.infrastructure.repositories_attachments import build_attachment_repos
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import build_storage


async def _next_tenant_slug(engine: AsyncEngine, now: datetime) -> str | None:
    """Descobre de qual tenant e o proximo job, para abrir UMA sessao capaz de
    escrever tanto em preview_jobs (schema publico) quanto nas tabelas do tenant.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        slug = await session.scalar(
            select(PreviewJobModel.tenant_slug)
            .where(
                PreviewJobModel.status == str(PreviewJobStatus.PENDENTE),
                PreviewJobModel.next_attempt_at <= now,
            )
            .order_by(PreviewJobModel.next_attempt_at)
            .limit(1)
        )
        return str(slug) if slug is not None else None


async def run_once(engine: AsyncEngine, storage: StoragePort, settings: Settings) -> bool:
    now = datetime.now(UTC)
    slug = await _next_tenant_slug(engine, now)
    if slug is None:
        return False
    # Uma unica sessao, traduzida para o schema deste tenant: claim_next grava em
    # preview_jobs (schema publico, fora do translate map) e a atualizacao do
    # anexo/foto grava no schema do tenant - ambas na MESMA transacao, commitada
    # uma unica vez no fim. Assim uma falha ao gravar o anexo desfaz tambem a
    # baixa do job (nao fica um job "processando" com o anexo intacto), e o lock
    # de linha do claim so e liberado depois que a conversao termina e tudo foi
    # persistido.
    translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        repos = build_attachment_repos(session)
        use_case = ProcessPreviewJobUseCase(
            jobs=repos.jobs,
            storage=storage,
            generate=generate_previews,
            attachments_for=lambda _slug: repos.attachments,
            photos_for=lambda _slug: repos.photos,
        )
        try:
            processou = await use_case.execute(now)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return processou


async def _expire_pending(engine: AsyncEngine, slug: str, minutes: int) -> None:
    translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        repos = build_attachment_repos(session)
        await ExpirePendingUseCase(repos.attachments, minutes=minutes).execute()
        await session.commit()


async def _active_tenant_slugs(engine: AsyncEngine) -> list[str]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = await session.scalars(
            select(TenantModel.slug).where(TenantModel.status != "inativa")
        )
        return list(rows)


async def expire_pending_all(engine: AsyncEngine, minutes: int) -> None:
    for slug in await _active_tenant_slugs(engine):
        await _expire_pending(engine, slug, minutes)


async def run_forever(
    engine: AsyncEngine,
    storage: StoragePort,
    settings: Settings,
    interval_seconds: float = 2.0,
    expire_every_seconds: float = 300.0,
) -> None:
    proxima_expiracao = 0.0
    while True:
        agora = asyncio.get_running_loop().time()
        if agora >= proxima_expiracao:
            await expire_pending_all(engine, settings.pending_expiration_minutes)
            proxima_expiracao = agora + expire_every_seconds
        processou = await run_once(engine, storage, settings)
        if not processou:
            await asyncio.sleep(interval_seconds)


async def _main_async(once: bool) -> None:
    settings = Settings()
    engine = build_engine(settings.database_url)
    storage = build_storage(settings)
    try:
        if once:
            await run_once(engine, storage, settings)
        else:
            await run_forever(engine, storage, settings)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-worker")
    parser.add_argument("--once", action="store_true", help="processa um job e sai")
    args = parser.parse_args()
    asyncio.run(_main_async(args.once))


if __name__ == "__main__":
    main()
