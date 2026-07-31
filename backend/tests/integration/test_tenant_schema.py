from uuid import uuid4

from sqlalchemy import inspect, select, text
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

# Indices de performance para as queries pesadas de relatorio/dashboard/galeria
# (repositories_reporting.py e repositories_tickets.py). Toda query de ticket
# filtra deleted_at IS NULL, entao a exclusao logica entra como PREDICADO
# PARCIAL, nao como coluna lider: como coluna ela custaria 8 bytes por entrada
# sem entregar seletividade (99% das linhas sao vivas).
EXPECTED_TICKET_INDEXES = {
    "ix_tickets_status",
    "ix_tickets_brand_id",
    "ix_tickets_opened_at",
    "ix_tickets_last_activity_at",
    "ix_tickets_due_at",
    "ix_tickets_customer_id",
    "ix_tickets_attendant_user_id",
}
# Os compostos liderados por deleted_at foram medidos em 100 mil tickets e
# substituidos pelos parciais acima: status, brand_id e opened_at eram usados,
# mas o parcial equivalente faz o mesmo trabalho em menos paginas; closed_at
# nunca foi escolhido por plano nenhum e nao tem substituto.
# approved_at/declined_at nunca existiram: no dashboard elas so aparecem dentro
# de count(*) FILTER (...), avaliado depois da varredura, nunca como predicado.
FORBIDDEN_TICKET_INDEXES = {
    "ix_tickets_deleted_at_status",
    "ix_tickets_deleted_at_brand_id",
    "ix_tickets_deleted_at_opened_at",
    "ix_tickets_deleted_at_closed_at",
    "ix_tickets_deleted_at_approved_at",
    "ix_tickets_deleted_at_declined_at",
}
EXPECTED_TICKET_ATTACHMENT_INDEXES = {
    "ix_ticket_attachments_ticket_id",
    "ix_ticket_attachments_status_created_at",
}
FORBIDDEN_TICKET_ATTACHMENT_INDEXES = {
    "ix_ticket_attachments_deleted_at_status_created_at",
    "ix_ticket_attachments_status",
}
# Indices de FK das tabelas filhas do ticket. Existem desde a 0003/0004 mas so
# passaram a ser declarados em models_tenant.py na 0007 — sem esta afirmacao o
# "__table_args__ reflete o schema real" nao teria trava de regressao. Nenhum
# deles e parcial: essas tabelas nao tem deleted_at (o filho some com o ticket).
EXPECTED_CHILD_INDEXES = {
    "ticket_items": "ix_ticket_items_ticket_id",
    "ticket_comments": "ix_ticket_comments_ticket_id",
    "ticket_timeline_events": "ix_ticket_timeline_events_ticket_id",
    "reverse_codes": "ix_reverse_codes_ticket_id",
}
_ALIVE_PREDICATE = "WHERE (deleted_at IS NULL)"


def _tenant_sessionmaker(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


async def test_migration_tenant_cria_tabelas_de_cadastro(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_demo")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert EXPECTED_TABLES <= set(tables)


async def test_migration_tenant_cria_indices_de_relatorio(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_indices")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename IN ('tickets', 'ticket_attachments')"
            ),
            {"schema": "t_indices"},
        )
        by_table: dict[str, set[str]] = {}
        definitions: dict[str, str] = {}
        for table, index, definition in rows.all():
            by_table.setdefault(table, set()).add(index)
            definitions[index] = definition
    assert EXPECTED_TICKET_INDEXES <= by_table.get("tickets", set())
    assert not (FORBIDDEN_TICKET_INDEXES & by_table.get("tickets", set()))
    assert EXPECTED_TICKET_ATTACHMENT_INDEXES <= by_table.get("ticket_attachments", set())
    assert not (FORBIDDEN_TICKET_ATTACHMENT_INDEXES & by_table.get("ticket_attachments", set()))
    # Todo indice de ticket e parcial: sem o predicado o indice volta a carregar
    # as ~1% de linhas excluidas logicamente e deixa de dispensar a recheck de
    # deleted_at no heap (o que transforma Index Only Scan em Bitmap + recheck).
    for name in EXPECTED_TICKET_INDEXES:
        assert _ALIVE_PREDICATE in definitions[name], name
    # O indice de anexos NAO e parcial de proposito: o varredor de pendentes
    # (list_pending_before) filtra so por status/created_at, sem deleted_at, e
    # um indice parcial seria inalcancavel para ele.
    assert _ALIVE_PREDICATE not in definitions["ix_ticket_attachments_status_created_at"]


async def test_migration_tenant_cria_indices_de_fk_das_tabelas_filhas(
    engine: AsyncEngine,
) -> None:
    await AlembicTenantProvisioner(engine).provision("t_indices_filhas")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = ANY(:tables)"
            ),
            {"schema": "t_indices_filhas", "tables": list(EXPECTED_CHILD_INDEXES)},
        )
        definitions = {index: definition for _, index, definition in rows.all()}
    for table, name in EXPECTED_CHILD_INDEXES.items():
        assert name in definitions, f"{name} ausente em {table}"
        assert _ALIVE_PREDICATE not in definitions[name], name


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
