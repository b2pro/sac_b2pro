import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure import migrate
from sac.infrastructure.provisioning import AlembicTenantProvisioner


async def _schema_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT schema_name FROM information_schema.schemata"))
        return {str(row[0]) for row in result}


async def test_provision_cria_schema_com_version_table(engine: AsyncEngine) -> None:
    provisioner = AlembicTenantProvisioner(engine)
    await provisioner.provision("t_demo")

    assert "t_demo" in await _schema_names(engine)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert "alembic_version" in tables


async def test_falha_na_migracao_desfaz_o_schema(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(schema_name: str) -> None:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(migrate, "upgrade_tenant", explode)
    provisioner = AlembicTenantProvisioner(engine)

    with pytest.raises(RuntimeError):
        await provisioner.provision("t_falha")

    assert "t_falha" not in await _schema_names(engine)
