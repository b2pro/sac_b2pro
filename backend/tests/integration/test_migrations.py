from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure.provisioning import AlembicTenantProvisioner

# Indices GIN de busca livre da Task 1 (Fase 3B): sem eles, ilike '%termo%'
# cai em Seq Scan (25,8 ms medidos em 40 mil clientes, docs/medicao-indices-tenant.md).
EXPECTED_TRGM_INDEXES = {
    "ix_customers_name_trgm",
    "ix_products_name_trgm",
    "ix_tickets_order_code_trgm",
}


async def test_migration_public_cria_tabelas_globais(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
    assert {"users", "tenants", "user_tenants", "alembic_version"} <= set(tables)


# user_preferences (Task 6 da Fase 4) roda na chain public, nao na de tenant:
# usuarios sao globais e um mesmo usuario acompanha a preferencia em qualquer
# tenant ao qual esteja vinculado. Por isso este teste confere colunas direto
# no schema public, ao contrario dos indices GIN acima que dependem de
# provisionar um schema de tenant (a migration de tenant roda uma vez por
# tenant; a de public roda uma vez so, por database).
async def test_migration_public_cria_tabela_user_preferences(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
        assert "user_preferences" in tables
        columns = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("user_preferences")}
        )
    assert {"user_id", "theme", "notify_toast", "notify_sound", "updated_at"} <= columns


async def test_migration_public_cria_extensao_pg_trgm(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
    assert result.first() is not None


async def test_migration_tenant_cria_indices_gin_trgm(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_busca_trgm")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = ANY(:names)"
            ),
            {"schema": "t_busca_trgm", "names": list(EXPECTED_TRGM_INDEXES)},
        )
        found = {row[0] for row in rows.all()}
    assert EXPECTED_TRGM_INDEXES <= found


# Indices da tabela de notificacoes (Task 1 da Fase 4): o parcial cobre o
# dropdown (nao lidas de um usuario), o composto cobre a lista paginada
# ordenada por created_at desc.
EXPECTED_NOTIFICATIONS_INDEXES = {
    "ix_notifications_user_unread",
    "ix_notifications_user_created",
}


async def test_migration_tenant_cria_tabela_e_indices_notifications(
    engine: AsyncEngine,
) -> None:
    await AlembicTenantProvisioner(engine).provision("t_notif_migra")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_notif_migra"))
        assert "notifications" in tables
        rows = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = ANY(:names)"
            ),
            {"schema": "t_notif_migra", "names": list(EXPECTED_NOTIFICATIONS_INDEXES)},
        )
        found = {row[0] for row in rows.all()}
    assert EXPECTED_NOTIFICATIONS_INDEXES <= found


# Indices GIN de trigrama da busca global (Task 7 da Fase 4): documento e
# telefone de cliente, email de cliente e SKU de produto. Completam os de
# nome/order_code de 0008_indices_busca.
EXPECTED_SEARCH_INDEXES = {
    "ix_customers_document_trgm",
    "ix_customers_email_trgm",
    "ix_customers_phone_trgm",
    "ix_products_sku_trgm",
}


async def test_migration_tenant_cria_indices_gin_trgm_da_busca_global(
    engine: AsyncEngine,
) -> None:
    await AlembicTenantProvisioner(engine).provision("t_busca_global")
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = ANY(:names)"
            ),
            {"schema": "t_busca_global", "names": list(EXPECTED_SEARCH_INDEXES)},
        )
        found = {row[0] for row in rows.all()}
    assert EXPECTED_SEARCH_INDEXES <= found
