import argparse
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sac.infrastructure.settings import Settings

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _config(section: str) -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"), ini_section=section)


def upgrade_public() -> None:
    command.upgrade(_config("public"), "head")


def upgrade_tenant(schema_name: str) -> None:
    cfg = _config("tenant")
    cfg.attributes["schema"] = schema_name
    command.upgrade(cfg, "head")


async def _tenant_schemas() -> list[str]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 't\\_%'"
            )
        )
        schemas = [str(row[0]) for row in result]
    await engine.dispose()
    return schemas


def upgrade_all_tenants() -> None:
    for schema in asyncio.run(_tenant_schemas()):
        upgrade_tenant(schema)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-migrate")
    parser.add_argument("target", choices=["public", "tenants", "all"])
    args = parser.parse_args()
    if args.target in ("public", "all"):
        upgrade_public()
    if args.target in ("tenants", "all"):
        upgrade_all_tenants()


if __name__ == "__main__":
    main()
