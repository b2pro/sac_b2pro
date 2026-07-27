import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure import migrate


class AlembicTenantProvisioner:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def provision(self, schema_name: str) -> None:
        # schema_name sempre deriva de slug validado por validate_slug
        async with self._engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        try:
            await asyncio.to_thread(migrate.upgrade_tenant, schema_name)
        except Exception:
            await self.drop(schema_name)
            raise

    async def drop(self, schema_name: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
