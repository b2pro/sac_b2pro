from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_reporting import DashboardData, ReportFilters
from sac.domain.tickets import TicketStatus
from sac.infrastructure.models_tenant import (
    BrandModel,
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    SolutionTypeModel,
    TicketItemModel,
    TicketModel,
)
from sac.infrastructure.repositories_reporting import SqlReportingRepository
from tests.integration.helpers import seed_provisioned_tenant, seed_user


@pytest.fixture
async def tenant_session(session: AsyncSession, engine: AsyncEngine) -> AsyncSession:
    await seed_provisioned_tenant(session, engine, slug="rep")
    scoped = engine.execution_options(schema_translate_map={"tenant": "t_rep"})
    factory = async_sessionmaker(scoped, expire_on_commit=False)
    async with factory() as ts:
        yield ts


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


async def seed_catalog(ts: AsyncSession) -> dict[str, UUID]:
    # provisionamento do tenant ja cadastra as marcas/defeitos/solucoes padrao
    # (seed_tenant_defaults); reaproveita esses registros em vez de duplicar,
    # o que violaria a unicidade de nome em cada tabela de catalogo.
    brand_a = (await ts.scalars(select(BrandModel.id).where(BrandModel.name == "KODI"))).one()
    brand_b = (await ts.scalars(select(BrandModel.id).where(BrandModel.name == "STALEKS"))).one()
    defect = (
        await ts.scalars(select(DefectTypeModel.id).where(DefectTypeModel.name == "Oxidacao"))
    ).one()
    solution = (
        await ts.scalars(
            select(SolutionTypeModel.id).where(SolutionTypeModel.name == "Troca pelo mesmo item")
        )
    ).one()
    product = ProductModel(id=uuid4(), name="Alicate", sku="PLN-10-7")
    product2 = ProductModel(id=uuid4(), name="Esmalte", sku="ESM-1")
    customer = CustomerModel(id=uuid4(), name="Cliente Rep", document="52998224725")
    ts.add_all([product, product2, customer])
    await ts.flush()
    return {
        "brand_a": brand_a,
        "brand_b": brand_b,
        "product": product.id,
        "product2": product2.id,
        "defect": defect,
        "solution": solution,
        "customer": customer.id,
    }


def make_ticket(
    ids: dict[str, UUID],
    attendant: UUID,
    *,
    brand: str = "brand_a",
    status: TicketStatus = TicketStatus.ABERTO,
    opened_at: datetime = NOW - timedelta(days=1),
    due_at: datetime | None = None,
    approved_at: datetime | None = None,
    declined_at: datetime | None = None,
    closed_at: datetime | None = None,
    solution: bool = False,
    deleted_at: datetime | None = None,
) -> TicketModel:
    return TicketModel(
        id=uuid4(),
        brand_id=ids[brand],
        customer_id=ids["customer"],
        status=str(status),
        priority="media",
        attendant_user_id=attendant,
        opened_at=opened_at,
        due_at=due_at or (opened_at + timedelta(hours=72)),
        last_activity_at=opened_at,
        approved_at=approved_at,
        declined_at=declined_at,
        closed_at=closed_at,
        solution_type_id=ids["solution"] if solution else None,
        deleted_at=deleted_at,
    )


def make_item(ticket_id: UUID, product_id: UUID, defect_id: UUID, quantity: int) -> TicketItemModel:
    return TicketItemModel(
        id=uuid4(),
        ticket_id=ticket_id,
        product_id=product_id,
        defect_type_id=defect_id,
        quantity=quantity,
    )


async def test_dashboard_kpis_distribuicao_rankings_e_tempo_medio(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep@t.dev")
    ids = await seed_catalog(tenant_session)
    aberto = make_ticket(ids, user.id)
    atrasado = make_ticket(
        ids,
        user.id,
        status=TicketStatus.AGUARDANDO_ANALISE,
        opened_at=NOW - timedelta(days=10),
    )
    finalizado = make_ticket(
        ids,
        user.id,
        status=TicketStatus.FINALIZADO,
        opened_at=NOW - timedelta(days=2),
        approved_at=NOW - timedelta(days=1),
        closed_at=NOW - timedelta(hours=24),
        solution=True,
    )
    declinado_mes_passado = make_ticket(
        ids,
        user.id,
        status=TicketStatus.DECLINADO,
        opened_at=datetime(2026, 6, 10, tzinfo=UTC),
        declined_at=datetime(2026, 6, 11, tzinfo=UTC),
        closed_at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    excluido = make_ticket(ids, user.id, deleted_at=NOW)
    tenant_session.add_all([aberto, atrasado, finalizado, declinado_mes_passado, excluido])
    await tenant_session.flush()
    tenant_session.add_all(
        [
            make_item(aberto.id, ids["product"], ids["defect"], quantity=2),
            make_item(finalizado.id, ids["product"], ids["defect"], quantity=1),
            make_item(finalizado.id, ids["product2"], ids["defect"], quantity=1),
        ]
    )
    await tenant_session.flush()

    data: DashboardData = await SqlReportingRepository(tenant_session).dashboard(
        brand_id=None, unread_for=user.id, now=NOW
    )

    kpis = {k.key: k.count for k in data.kpis}
    assert kpis["total"] == 4  # excluido fica fora
    assert kpis["abertos"] == 1
    assert kpis["aguardando_analise"] == 1
    assert kpis["atrasados"] == 1  # so o aguardando_analise vencido e nao encerrado
    assert kpis["aprovados_no_mes"] == 1
    assert kpis["declinados_no_mes"] == 0  # declinado foi em junho
    assert kpis["finalizados_no_mes"] == 1
    kpi_filters = {k.key: k.filters for k in data.kpis}
    assert kpi_filters == {
        "total": {},
        "abertos": {"status": "aberto"},
        "aguardando_analise": {"status": "aguardando_analise"},
        "atrasados": {"overdue": "1"},
        "aprovados_no_mes": {"status": "aprovado"},
        "declinados_no_mes": {"status": "declinado"},
        "finalizados_no_mes": {"status": "finalizado"},
    }
    assert data.status_counts[TicketStatus.ABERTO] == 1
    assert data.status_counts[TicketStatus.FINALIZADO] == 1
    # ranking pondera quantidade: Alicate 2+1=3, Esmalte 1
    assert [(r.name, r.count) for r in data.products] == [("Alicate", 3), ("Esmalte", 1)]
    assert data.solutions[0].count == 1
    # tempo medio: finalizado abriu NOW-2d e fechou NOW-24h -> 24h
    assert data.avg_resolution_hours == pytest.approx(24.0)
    assert len(data.recent) == 4


async def test_dashboard_filtra_por_marca_e_sem_finalizados_da_none(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep2@t.dev")
    ids = await seed_catalog(tenant_session)
    tenant_session.add(make_ticket(ids, user.id, brand="brand_b"))
    await tenant_session.flush()

    data = await SqlReportingRepository(tenant_session).dashboard(
        brand_id=ids["brand_a"], unread_for=user.id, now=NOW
    )
    assert {k.key: k.count for k in data.kpis}["total"] == 0
    assert data.avg_resolution_hours is None


async def test_report_aplica_mesmo_recorte_em_kpis_rankings_e_tabela(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep3@t.dev")
    ids = await seed_catalog(tenant_session)
    dentro = make_ticket(
        ids,
        user.id,
        status=TicketStatus.FINALIZADO,
        opened_at=datetime(2026, 7, 10, tzinfo=UTC),
        closed_at=datetime(2026, 7, 12, tzinfo=UTC),
        solution=True,
    )
    fora_do_periodo = make_ticket(ids, user.id, opened_at=datetime(2026, 5, 1, tzinfo=UTC))
    tenant_session.add_all([dentro, fora_do_periodo])
    await tenant_session.flush()
    tenant_session.add(make_item(dentro.id, ids["product"], ids["defect"], quantity=2))
    await tenant_session.flush()

    filters = ReportFilters(
        date_from=datetime(2026, 7, 1, tzinfo=UTC),
        date_to=datetime(2026, 8, 1, tzinfo=UTC),
    )
    repo = SqlReportingRepository(tenant_session)
    data = await repo.report(filters, page=1, per_page=20, unread_for=user.id)
    assert data.kpis.total == 1
    assert data.kpis.finalized == 1
    assert data.kpis.declined == 0
    assert data.total == 1
    assert len(data.tickets) == 1
    assert data.products[0].count == 2
    assert data.tickets[0].first_product_name == "Alicate"

    # filtro por produto usa EXISTS nos itens
    com_produto = await repo.report(
        ReportFilters(product_id=ids["product2"]), page=1, per_page=20, unread_for=user.id
    )
    assert com_produto.kpis.total == 0


async def test_export_rows_traz_cliente_produtos_e_pagina(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep4@t.dev", name="Atendente Rep")
    ids = await seed_catalog(tenant_session)
    t = make_ticket(ids, user.id, status=TicketStatus.FINALIZADO, closed_at=NOW, solution=True)
    tenant_session.add(t)
    await tenant_session.flush()
    tenant_session.add_all(
        [
            make_item(t.id, ids["product"], ids["defect"], quantity=2),
            make_item(t.id, ids["product2"], ids["defect"], quantity=1),
        ]
    )
    await tenant_session.flush()

    rows = await SqlReportingRepository(tenant_session).export_rows(
        ReportFilters(), page=1, per_page=10
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.customer_name == "Cliente Rep"
    assert row.brand == "KODI"
    assert row.products == "Alicate x2; Esmalte x1"
    assert row.solution == "Troca pelo mesmo item"
    assert row.attendant == "Atendente Rep"

    vazia = await SqlReportingRepository(tenant_session).export_rows(
        ReportFilters(), page=2, per_page=10
    )
    assert vazia == []
