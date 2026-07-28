from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.infrastructure.models_tenant import BrandModel, SlaPolicyModel, TicketModel
from tests.integration.helpers import seed_provisioned_tenant


def _tenant_factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


def _ticket_model(brand_id: UUID) -> TicketModel:
    return TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=uuid4(),
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )


async def test_sequence_numera_sem_reuso(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="seqtest")
    factory = _tenant_factory(engine, tenant.schema_name)
    async with factory() as ts:
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        first = _ticket_model(brand_id)
        second = _ticket_model(brand_id)
        ts.add(first)
        await ts.flush()
        ts.add(second)
        await ts.flush()
        assert first.number == 1
        assert second.number == 2
        await ts.commit()


async def test_provisionamento_semeia_sla_policies(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="slatest")
    factory = _tenant_factory(engine, tenant.schema_name)
    async with factory() as ts:
        rows = (await ts.scalars(select(SlaPolicyModel))).all()
        by_priority = {r.priority: r for r in rows}
        assert by_priority["urgente"].hours == 24
        assert by_priority["alta"].hours == 48
        assert by_priority["media"].hours == 72
        assert by_priority["baixa"].hours == 120
        assert all(r.warn_hours == 12 for r in rows)


async def test_sequences_isoladas_por_tenant(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant_a = await seed_provisioned_tenant(session, engine, slug="seqa")
    tenant_b = await seed_provisioned_tenant(session, engine, slug="seqb")
    for schema in (tenant_a.schema_name, tenant_b.schema_name):
        factory = _tenant_factory(engine, schema)
        async with factory() as ts:
            brand_id = (await ts.scalars(select(BrandModel.id))).first()
            assert brand_id is not None
            ticket = _ticket_model(brand_id)
            ts.add(ticket)
            await ts.flush()
            assert ticket.number == 1
            await ts.commit()
