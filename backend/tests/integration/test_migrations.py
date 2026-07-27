from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_migration_public_cria_tabelas_globais(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
    assert {"users", "tenants", "user_tenants", "alembic_version"} <= set(tables)
