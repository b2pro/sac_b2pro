import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_attachments import ObjectHead
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from sac.infrastructure.models_tenant import BrandModel, TicketModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    build_attachment_repos,
)
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.infrastructure.worker import run_once
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _png(width: int = 1000, height: int = 500) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket_id(ts: AsyncSession, attendant: UUID) -> UUID:
    brand_id = (await ts.scalars(select(BrandModel.id))).first()
    assert brand_id is not None
    ticket = TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=attendant,
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    ts.add(ticket)
    await ts.flush()
    return ticket.id


async def test_worker_gera_os_dois_previews_e_marca_pronto(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="workerok")
    user = await seed_user(session, email="worker@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        chave = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="foto.png",
            content_type="image/png",
            size_bytes=len(_png()),
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
            confirmed_at=datetime.now(UTC),
        )
        await repos.attachments.add(anexo)
        await ts.commit()

    storage.put_bytes(chave, _png(), "image/png")
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=uuid4(),
            tenant_slug=tenant.slug,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=anexo.id,
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    thumb_key, medium_key = preview_keys_for(chave)
    head_thumb = storage.head(thumb_key)
    head_medium = storage.head(medium_key)
    assert isinstance(head_thumb, ObjectHead) and head_thumb.content_type == "image/webp"
    assert isinstance(head_medium, ObjectHead)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        atualizado = await repos.attachments.get(anexo.id)
        assert atualizado is not None
        assert atualizado.preview_status is PreviewStatus.PRONTO
        assert atualizado.preview_key == thumb_key
        assert atualizado.preview_medium_key == medium_key


async def test_worker_sem_job_devolve_false(
    engine: AsyncEngine, storage: S3Storage, storage_settings: Settings
) -> None:
    assert await run_once(engine, storage, storage_settings) is False


async def test_job_de_objeto_inexistente_esgota_na_primeira_tentativa(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    """Desvio deliberado do teste do brief: o brief (Task 8) foi escrito sem
    conhecer a classificacao de falhas ja implementada e testada na Task 6
    (ProcessPreviewJobUseCase / tests/unit/application/test_previews_use_case.py
    ::test_original_ausente_falha_definitivamente_sem_esperar_cinco_tentativas):
    objeto original ausente e falha PERMANENTE (esgota na 1a tentativa, status
    falhou), nao transitoria. Reproduzir a expectativa literal do brief
    (reagenda com PENDENTE) contradiria esse comportamento ja revisado e
    coberto por teste unitario, entao este teste de integracao verifica o
    comportamento real contra Postgres/MinIO de verdade."""
    tenant = await seed_provisioned_tenant(session, engine, slug="workerfail")
    job_id = uuid4()
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=job_id,
            tenant_slug=tenant.slug,
            object_key=f"{tenant.slug}/inexistente/x.png",
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=uuid4(),
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    relido = await SqlPreviewJobRepository(session).get(job_id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.FALHOU
    assert relido.attempts == 1
    assert relido.last_error is not None and "nao encontrado" in relido.last_error


async def test_expiracao_de_pendentes_varre_os_tenants(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    from sqlalchemy import text

    from sac.infrastructure.worker import expire_pending_all

    tenant = await seed_provisioned_tenant(session, engine, slug="workerexp")
    user = await seed_user(session, email="workerexp@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="pendente.png",
            content_type="image/png",
            size_bytes=10,
            object_key=f"{tenant.slug}/{ticket_id}/{uuid4()}.png",
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.PENDENTE,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
        )
        await repos.attachments.add(anexo)
        await ts.execute(
            text(
                f'UPDATE "{tenant.schema_name}".ticket_attachments '
                "SET created_at = now() - interval '2 hours'"
            )
        )
        await ts.commit()

    await expire_pending_all(engine, minutes=30)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        relido = await repos.attachments.get(anexo.id)
        assert relido is not None
        assert relido.status is AttachmentStatus.EXPIRADO
