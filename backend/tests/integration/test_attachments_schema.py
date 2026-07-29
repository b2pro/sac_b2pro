from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.infrastructure.models import PreviewJobModel
from sac.infrastructure.models_tenant import (
    BrandModel,
    ProductModel,
    TicketAttachmentModel,
    TicketModel,
)
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket(ts: AsyncSession, attendant: UUID) -> TicketModel:
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
    return ticket


async def test_anexo_persiste_com_defaults(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexschema")
    user = await seed_user(session, email="anex@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket = await _ticket(ts, user.id)
        anexo = TicketAttachmentModel(
            id=uuid4(),
            ticket_id=ticket.id,
            filename="foto.jpg",
            content_type="image/jpeg",
            size_bytes=1234,
            object_key=f"{tenant.slug}/{ticket.id}/{uuid4()}.jpg",
            kind="imagem",
            status="pendente",
            preview_status="pendente",
            author_user_id=user.id,
        )
        ts.add(anexo)
        await ts.flush()
        assert anexo.created_at is not None
        assert anexo.deleted_at is None
        await ts.commit()


async def test_tamanho_zero_e_recusado_pelo_check(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexcheck")
    user = await seed_user(session, email="anexcheck@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket = await _ticket(ts, user.id)
        ts.add(
            TicketAttachmentModel(
                id=uuid4(),
                ticket_id=ticket.id,
                filename="vazio.pdf",
                content_type="application/pdf",
                size_bytes=0,
                object_key="x/y/z.pdf",
                kind="pdf",
                status="pendente",
                preview_status="sem_preview",
                author_user_id=user.id,
            )
        )
        with pytest.raises(IntegrityError):
            await ts.flush()


async def test_produto_tem_coluna_de_preview(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexfoto")
    async with _factory(engine, tenant.schema_name)() as ts:
        produto = ProductModel(
            id=uuid4(),
            name="Produto com foto",
            sku="FOTO-1",
            photo_key="acme/catalogo/produtos/x/y.png",
            photo_preview_key="acme/catalogo/produtos/x/previews/y.webp",
        )
        ts.add(produto)
        await ts.flush()
        assert produto.photo_preview_key is not None
        await ts.commit()


async def test_preview_job_global_exige_exatamente_um_dono(session: AsyncSession) -> None:
    job = PreviewJobModel(
        id=uuid4(),
        tenant_slug="acme",
        attachment_id=uuid4(),
        object_key="acme/t/x.jpg",
        kind="imagem",
        status="pendente",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    session.add(
        PreviewJobModel(
            id=uuid4(),
            tenant_slug="acme",
            attachment_id=uuid4(),
            product_id=uuid4(),
            object_key="acme/t/y.jpg",
            kind="imagem",
            status="pendente",
            attempts=0,
            next_attempt_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_indice_da_fila_existe(session: AsyncSession) -> None:
    nomes = (
        await session.scalars(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'preview_jobs'")
        )
    ).all()
    assert "ix_preview_jobs_pendentes" in nomes
