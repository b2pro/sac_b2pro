from uuid import uuid4

from sqlalchemy import inspect, select
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


def _tenant_sessionmaker(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


async def test_migration_tenant_cria_tabelas_de_cadastro(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_demo")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert EXPECTED_TABLES <= set(tables)


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
