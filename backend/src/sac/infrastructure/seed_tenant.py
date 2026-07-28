import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from sac.domain.entities import validate_slug
from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.repositories import SqlTenantRepository
from sac.infrastructure.settings import Settings
from sac.infrastructure.tenant_seeds import seed_tenant_defaults


async def run(slug: str) -> str:
    validate_slug(slug)
    engine = build_engine(Settings().database_url)
    try:
        factory = build_session_factory(engine)
        async with factory() as session:
            tenant = await SqlTenantRepository(session).get_by_slug(slug)
            if tenant is None:
                return f"tenant nao encontrado: {slug}"
        translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
        tenant_factory = async_sessionmaker(translated, expire_on_commit=False)
        async with tenant_factory() as session:
            created = await seed_tenant_defaults(session)
            await session.commit()
        return f"seeds aplicados: {created} itens criados"
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-seed-tenant")
    parser.add_argument("slug")
    args = parser.parse_args()
    print(asyncio.run(run(args.slug)))


if __name__ == "__main__":
    main()
