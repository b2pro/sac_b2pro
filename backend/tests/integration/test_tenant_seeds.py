from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.catalog import CatalogKind
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository
from sac.infrastructure.seed_tenant import run as seed_tenant_run
from sac.infrastructure.tenant_seeds import seed_tenant_defaults
from tests.integration.helpers import seed_tenant


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def test_provisionamento_semeia_defaults(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_seed")

    async with _factory(engine, "t_seed")() as session:
        brands = SqlCatalogRepository(session, CatalogKind.BRAND)
        assert await brands.get_by_name("KODI") is not None
        assert await brands.get_by_name("STALEKS") is not None

        defects = await SqlCatalogRepository(session, CatalogKind.DEFECT_TYPE).list(None, None)
        assert {"Danificado", "Oxidacao", "Mau uso"} <= {d.name for d in defects}

        channels = await SqlCatalogRepository(session, CatalogKind.PURCHASE_CHANNEL).list(
            None, None
        )
        assert "Mercado Livre" in {c.name for c in channels}


async def test_seed_e_idempotente(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_idem")
    async with _factory(engine, "t_idem")() as session:
        created = await seed_tenant_defaults(session)
        await session.commit()
    assert created == 0


async def test_cli_seed_tenant(engine: AsyncEngine, session: AsyncSession) -> None:
    assert "nao encontrado" in await seed_tenant_run("inexistente")

    await seed_tenant(session, slug="clitenant")
    await AlembicTenantProvisioner(engine).drop("t_clitenant")
    import asyncio

    from sac.infrastructure.migrate import upgrade_tenant

    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text('CREATE SCHEMA "t_clitenant"'))
    await asyncio.to_thread(upgrade_tenant, "t_clitenant")

    resultado = await seed_tenant_run("clitenant")
    assert "seeds aplicados" in resultado
