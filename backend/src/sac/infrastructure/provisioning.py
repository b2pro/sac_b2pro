import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.infrastructure import migrate
from sac.infrastructure.tenant_seeds import seed_tenant_defaults


class AlembicTenantProvisioner:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def provision(self, schema_name: str) -> None:
        # schema_name sempre deriva de slug validado por validate_slug
        async with self._engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        try:
            await asyncio.to_thread(migrate.upgrade_tenant, schema_name)
            translated = self._engine.execution_options(
                schema_translate_map={"tenant": schema_name}
            )
            factory = async_sessionmaker(translated, expire_on_commit=False)
            async with factory() as session:
                await seed_tenant_defaults(session)
                await session.commit()
        except Exception:
            await self.drop(schema_name)
            raise

    async def drop(self, schema_name: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
