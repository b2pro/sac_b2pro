import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from sac.infrastructure.models_tenant import TenantBase
from sac.infrastructure.settings import Settings

target_metadata = TenantBase.metadata


def _schema() -> str:
    schema = context.config.attributes.get("schema") or context.get_x_argument(
        as_dictionary=True
    ).get("schema")
    if not schema:
        raise RuntimeError("informe o schema do tenant: -x schema=t_<slug>")
    return str(schema)


def do_run_migrations(connection: Connection, schema: str) -> None:
    connection = connection.execution_options(schema_translate_map={"tenant": schema})
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(schema: str) -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(lambda conn: do_run_migrations(conn, schema))
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("modo offline nao suportado")
asyncio.run(run_async_migrations(_schema()))
