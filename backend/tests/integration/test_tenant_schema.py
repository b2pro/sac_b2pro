from uuid import uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.infrastructure.models_tenant import BrandModel
from sac.infrastructure.provisioning import AlembicTenantProvisioner

EXPECTED_TABLES = {
    "brands",
    "defect_types",
    "solution_types",
    "purchase_channels",
    "products",
    "customers",
}

# Indices de performance para as queries pesadas de relatorio/dashboard/galeria
# (Fase 3, repositories_reporting.py). deleted_at e a marca de exclusao logica
# presente em quase todo filtro dessas queries, por isso lidera os compostos.
EXPECTED_TICKET_INDEXES = {
    "ix_tickets_deleted_at_status",
    "ix_tickets_deleted_at_brand_id",
    "ix_tickets_deleted_at_opened_at",
    "ix_tickets_deleted_at_closed_at",
}
# approved_at/declined_at nao entram: no dashboard elas so aparecem dentro de
# count(*) FILTER (...), que e avaliado depois da varredura e nunca vira busca
# por indice — um composto ali seria custo de escrita sem ganho de leitura.
FORBIDDEN_TICKET_INDEXES = {
    "ix_tickets_deleted_at_approved_at",
    "ix_tickets_deleted_at_declined_at",
}
EXPECTED_TICKET_ATTACHMENT_INDEXES = {
    "ix_ticket_attachments_deleted_at_status_created_at",
}


def _tenant_sessionmaker(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


async def test_migration_tenant_cria_tabelas_de_cadastro(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_demo")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert EXPECTED_TABLES <= set(tables)


async def test_migration_tenant_cria_indices_de_relatorio(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_indices")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename, indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename IN ('tickets', 'ticket_attachments')"
            ),
            {"schema": "t_indices"},
        )
        by_table: dict[str, set[str]] = {}
        for table, index in rows.all():
            by_table.setdefault(table, set()).add(index)
    assert EXPECTED_TICKET_INDEXES <= by_table.get("tickets", set())
    assert not (FORBIDDEN_TICKET_INDEXES & by_table.get("tickets", set()))
    assert EXPECTED_TICKET_ATTACHMENT_INDEXES <= by_table.get("ticket_attachments", set())


async def test_schema_translate_map_isola_tenants(engine: AsyncEngine) -> None:
    provisioner = AlembicTenantProvisioner(engine)
    await provisioner.provision("t_alfa")
    await provisioner.provision("t_beta")

    async with _tenant_sessionmaker(engine, "t_alfa")() as session:
        session.add(BrandModel(id=uuid4(), name="MARCA-ALFA"))
        await session.commit()

    async with _tenant_sessionmaker(engine, "t_alfa")() as session:
        names = list(await session.scalars(select(BrandModel.name)))
    assert "MARCA-ALFA" in names

    async with _tenant_sessionmaker(engine, "t_beta")() as session:
        names = list(await session.scalars(select(BrandModel.name)))
    assert "MARCA-ALFA" not in names
