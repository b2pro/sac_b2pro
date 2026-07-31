from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure.provisioning import AlembicTenantProvisioner

# Indices GIN de busca livre da Task 1 (Fase 3B): sem eles, ilike '%termo%'
# cai em Seq Scan (25,8 ms medidos em 40 mil clientes, docs/medicao-indices-tenant.md).
EXPECTED_TRGM_INDEXES = {
    "ix_customers_name_trgm",
    "ix_products_name_trgm",
    "ix_tickets_order_code_trgm",
}


async def test_migration_public_cria_tabelas_globais(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
    assert {"users", "tenants", "user_tenants", "alembic_version"} <= set(tables)


async def test_migration_public_cria_extensao_pg_trgm(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
    assert result.first() is not None


async def test_migration_tenant_cria_indices_gin_trgm(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_busca_trgm")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = ANY(:names)"
            ),
            {"schema": "t_busca_trgm", "names": list(EXPECTED_TRGM_INDEXES)},
        )
        found = {row[0] for row in rows.all()}
    assert EXPECTED_TRGM_INDEXES <= found
