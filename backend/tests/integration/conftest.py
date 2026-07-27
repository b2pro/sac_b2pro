import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sac.infrastructure.settings import Settings
from sac.interface.app import create_app

ADMIN_URL = "postgresql+asyncpg://sac:sac@localhost:5432/postgres"
TEST_DB_URL = "postgresql+asyncpg://sac:sac@localhost:5432/sac_test"


async def _recreate_database() -> None:
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS sac_test WITH (FORCE)"))
        await conn.execute(text("CREATE DATABASE sac_test"))
    await engine.dispose()


@pytest.fixture(scope="session")
def database() -> str:
    os.environ["SAC_DATABASE_URL"] = TEST_DB_URL
    asyncio.run(_recreate_database())
    from sac.infrastructure.migrate import upgrade_public

    upgrade_public()
    return TEST_DB_URL


@pytest.fixture
async def engine(database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE user_tenants, users, tenants CASCADE"))
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 't\\_%'"
            )
        )
        for row in result.all():
            await conn.execute(text(f'DROP SCHEMA "{row[0]}" CASCADE'))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def app(engine: AsyncEngine, database: str) -> AsyncIterator[FastAPI]:
    application = create_app(Settings(database_url=database))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
