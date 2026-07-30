from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_reporting import DashboardData, MediaFilters, ReportFilters
from sac.domain.attachments import AttachmentKind
from sac.domain.tickets import TicketStatus
from sac.infrastructure.models_tenant import (
    BrandModel,
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    PurchaseChannelModel,
    SolutionTypeModel,
    TicketAttachmentModel,
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
    # provisionamento do tenant ja cadastra as marcas/defeitos/solucoes/canais
    # padrao (seed_tenant_defaults); reaproveita esses registros em vez de
    # duplicar, o que violaria a unicidade de nome em cada tabela de catalogo.
    brand_a = (await ts.scalars(select(BrandModel.id).where(BrandModel.name == "KODI"))).one()
    brand_b = (await ts.scalars(select(BrandModel.id).where(BrandModel.name == "STALEKS"))).one()
    defect = (
        await ts.scalars(select(DefectTypeModel.id).where(DefectTypeModel.name == "Oxidacao"))
    ).one()
    defect2 = (
        await ts.scalars(select(DefectTypeModel.id).where(DefectTypeModel.name == "Danificado"))
    ).one()
    solution = (
        await ts.scalars(
            select(SolutionTypeModel.id).where(SolutionTypeModel.name == "Troca pelo mesmo item")
        )
    ).one()
    solution2 = (
        await ts.scalars(
            select(SolutionTypeModel.id).where(SolutionTypeModel.name == "Troca por outro item")
        )
    ).one()
    channel_a = (
        await ts.scalars(select(PurchaseChannelModel.id).where(PurchaseChannelModel.name == "SAC"))
    ).one()
    channel_b = (
        await ts.scalars(
            select(PurchaseChannelModel.id).where(PurchaseChannelModel.name == "Site KODI")
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
        "defect2": defect2,
        "solution": solution,
        "solution2": solution2,
        "channel_a": channel_a,
        "channel_b": channel_b,
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
    solution_type_id: UUID | None = None,
    purchase_channel_id: UUID | None = None,
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
        solution_type_id=(
            solution_type_id
            if solution_type_id is not None
            else (ids["solution"] if solution else None)
        ),
        purchase_channel_id=purchase_channel_id,
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


def make_attachment(
    ticket_id: UUID,
    author: UUID,
    *,
    kind: str = "imagem",
    status: str = "disponivel",
    deleted_at: datetime | None = None,
    created_at: datetime | None = None,
) -> TicketAttachmentModel:
    kwargs: dict[str, object] = dict(
        id=uuid4(),
        ticket_id=ticket_id,
        filename="foto.jpg",
        content_type="image/jpeg",
        size_bytes=1000,
        object_key=f"rep/{ticket_id}/{uuid4()}.jpg",
        kind=kind,
        status=status,
        preview_status="pronto" if kind == "imagem" else "sem_preview",
        preview_key="k.webp" if kind == "imagem" else None,
        author_user_id=author,
        deleted_at=deleted_at,
    )
    # so passa created_at quando explicito: a coluna tem server_default e um
    # None explicito quebraria o NOT NULL.
    if created_at is not None:
        kwargs["created_at"] = created_at
    return TicketAttachmentModel(**kwargs)


async def test_list_media_filtra_confirmados_por_kind_e_dados_do_ticket(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep5@t.dev")
    ids = await seed_catalog(tenant_session)
    t = make_ticket(ids, user.id, solution=True)
    tenant_session.add(t)
    await tenant_session.flush()
    tenant_session.add(make_item(t.id, ids["product"], ids["defect"], quantity=1))
    ok = make_attachment(t.id, user.id)
    pendente = make_attachment(t.id, user.id, status="pendente")
    excluido = make_attachment(t.id, user.id, deleted_at=NOW)
    pdf = make_attachment(t.id, user.id, kind="pdf")
    tenant_session.add_all([ok, pendente, excluido, pdf])
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    rows, total = await repo.list_media(MediaFilters(), page=1, per_page=10)
    assert total == 2  # pendente e excluido ficam fora
    assert rows[0].ticket_number == t.number

    so_imagem, total_imagem = await repo.list_media(
        MediaFilters(kind=AttachmentKind.IMAGEM), page=1, per_page=10
    )
    assert total_imagem == 1
    assert so_imagem[0].attachment.id == ok.id

    por_produto, _ = await repo.list_media(
        MediaFilters(product_id=ids["product2"]), page=1, per_page=10
    )
    assert por_produto == []


# --- escopo por actor (dashboard.recent, report.tickets, export_rows, list_media) ---
# Aggregados (kpis, status_counts, rankings) ficam tenant-wide de proposito;
# so a saida linha a linha e restrita ao owner_user_id quando o actor nao tem
# VER_TODOS_TICKETS. Ver GetDashboardUseCase/GetReportUseCase/ExportReportUseCase.


async def test_dashboard_recent_restringe_por_owner_mas_kpis_e_rankings_nao(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    dono = await seed_user(session, email="dono-dash@t.dev")
    colega = await seed_user(session, email="colega-dash@t.dev")
    ids = await seed_catalog(tenant_session)
    proprio = make_ticket(ids, dono.id)
    do_colega = make_ticket(ids, colega.id)
    tenant_session.add_all([proprio, do_colega])
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    escopado = await repo.dashboard(
        brand_id=None, unread_for=dono.id, now=NOW, owner_user_id=dono.id
    )
    assert [r.ticket.id for r in escopado.recent] == [proprio.id]
    assert {k.key: k.count for k in escopado.kpis}["total"] == 2

    irrestrito = await repo.dashboard(
        brand_id=None, unread_for=dono.id, now=NOW, owner_user_id=None
    )
    assert {r.ticket.id for r in irrestrito.recent} == {proprio.id, do_colega.id}
    assert {k.key: k.count for k in irrestrito.kpis}["total"] == 2


async def test_report_tabela_restringe_por_owner_mas_kpis_e_rankings_nao(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    dono = await seed_user(session, email="dono-rel@t.dev")
    colega = await seed_user(session, email="colega-rel@t.dev")
    ids = await seed_catalog(tenant_session)
    proprio = make_ticket(ids, dono.id)
    do_colega = make_ticket(ids, colega.id)
    tenant_session.add_all([proprio, do_colega])
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    escopado = await repo.report(
        ReportFilters(), page=1, per_page=20, unread_for=dono.id, owner_user_id=dono.id
    )
    assert escopado.kpis.total == 2  # kpi permanece tenant-wide
    assert escopado.total == 1  # tabela e restrita ao dono
    assert [t.ticket.id for t in escopado.tickets] == [proprio.id]

    irrestrito = await repo.report(
        ReportFilters(), page=1, per_page=20, unread_for=dono.id, owner_user_id=None
    )
    assert irrestrito.total == 2
    assert irrestrito.kpis.total == 2


async def test_export_rows_restringe_por_owner(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    dono = await seed_user(session, email="dono-csv@t.dev", name="Dono Csv")
    colega = await seed_user(session, email="colega-csv@t.dev", name="Colega Csv")
    ids = await seed_catalog(tenant_session)
    proprio = make_ticket(ids, dono.id)
    do_colega = make_ticket(ids, colega.id)
    tenant_session.add_all([proprio, do_colega])
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    escopado = await repo.export_rows(ReportFilters(), page=1, per_page=10, owner_user_id=dono.id)
    assert [r.attendant for r in escopado] == ["Dono Csv"]

    irrestrito = await repo.export_rows(ReportFilters(), page=1, per_page=10, owner_user_id=None)
    assert {r.attendant for r in irrestrito} == {"Dono Csv", "Colega Csv"}


async def test_list_media_filtra_por_attendant_user_id(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    dono = await seed_user(session, email="dono-media@t.dev")
    colega = await seed_user(session, email="colega-media@t.dev")
    ids = await seed_catalog(tenant_session)
    t_dono = make_ticket(ids, dono.id)
    t_colega = make_ticket(ids, colega.id)
    tenant_session.add_all([t_dono, t_colega])
    await tenant_session.flush()
    anexo_dono = make_attachment(t_dono.id, dono.id)
    anexo_colega = make_attachment(t_colega.id, colega.id)
    tenant_session.add_all([anexo_dono, anexo_colega])
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    rows, total = await repo.list_media(
        MediaFilters(attendant_user_id=dono.id), page=1, per_page=10
    )
    assert total == 1
    assert rows[0].attachment.id == anexo_dono.id

    todos, total_todos = await repo.list_media(MediaFilters(), page=1, per_page=10)
    assert total_todos == 2


# --- cobertura dos filtros de relatorio/midias nunca exercitados (Fase 3) ---


@pytest.fixture
async def filter_dataset(session: AsyncSession, tenant_session: AsyncSession) -> dict[str, object]:
    user_a = await seed_user(session, email="filtro-a@t.dev")
    user_b = await seed_user(session, email="filtro-b@t.dev")
    ids = await seed_catalog(tenant_session)
    ticket_a = make_ticket(
        ids,
        user_a.id,
        brand="brand_a",
        status=TicketStatus.ABERTO,
        opened_at=datetime(2026, 7, 5, tzinfo=UTC),
        purchase_channel_id=ids["channel_a"],
    )
    ticket_b = make_ticket(
        ids,
        user_b.id,
        brand="brand_b",
        status=TicketStatus.FINALIZADO,
        opened_at=datetime(2026, 7, 20, tzinfo=UTC),
        closed_at=datetime(2026, 7, 21, tzinfo=UTC),
        solution_type_id=ids["solution2"],
        purchase_channel_id=ids["channel_b"],
    )
    tenant_session.add_all([ticket_a, ticket_b])
    await tenant_session.flush()
    tenant_session.add_all(
        [
            make_item(ticket_a.id, ids["product"], ids["defect"], quantity=1),
            make_item(ticket_b.id, ids["product2"], ids["defect2"], quantity=1),
        ]
    )
    anexo_a = make_attachment(ticket_a.id, user_a.id, created_at=NOW - timedelta(days=10))
    anexo_b = make_attachment(ticket_b.id, user_b.id, created_at=NOW)
    tenant_session.add_all([anexo_a, anexo_b])
    await tenant_session.flush()
    return {
        "ids": ids,
        "ticket_a": ticket_a,
        "ticket_b": ticket_b,
        "user_a": user_a,
        "user_b": user_b,
        "anexo_a": anexo_a,
        "anexo_b": anexo_b,
    }


_REPORT_FILTER_CASES = [
    ("brand_id", lambda d: d["ids"]["brand_a"], "ticket_a"),
    ("status", lambda d: TicketStatus.FINALIZADO, "ticket_b"),
    ("defect_type_id", lambda d: d["ids"]["defect2"], "ticket_b"),
    ("solution_type_id", lambda d: d["ids"]["solution2"], "ticket_b"),
    ("attendant_user_id", lambda d: d["user_a"].id, "ticket_a"),
    ("purchase_channel_id", lambda d: d["ids"]["channel_b"], "ticket_b"),
]


@pytest.mark.parametrize(
    ("field", "value_fn", "expected_key"),
    _REPORT_FILTER_CASES,
    ids=[c[0] for c in _REPORT_FILTER_CASES],
)
async def test_report_filtra_por_cada_criterio_isolado(
    tenant_session: AsyncSession,
    filter_dataset: dict[str, object],
    field: str,
    value_fn,  # noqa: ANN001
    expected_key: str,
) -> None:
    d = filter_dataset
    filters = ReportFilters(**{field: value_fn(d)})
    repo = SqlReportingRepository(tenant_session)
    data = await repo.report(filters, page=1, per_page=20, unread_for=d["user_a"].id)
    assert data.total == 1
    assert data.tickets[0].ticket.id == d[expected_key].id


async def test_report_filtra_por_combinacao_de_dois_criterios(
    tenant_session: AsyncSession, filter_dataset: dict[str, object]
) -> None:
    d = filter_dataset
    repo = SqlReportingRepository(tenant_session)

    combinado = await repo.report(
        ReportFilters(brand_id=d["ids"]["brand_b"], status=TicketStatus.FINALIZADO),
        page=1,
        per_page=20,
        unread_for=d["user_a"].id,
    )
    assert combinado.total == 1
    assert combinado.tickets[0].ticket.id == d["ticket_b"].id

    # a mesma combinacao cruzada com o outro ticket nao bate com nenhum
    vazio = await repo.report(
        ReportFilters(brand_id=d["ids"]["brand_a"], status=TicketStatus.FINALIZADO),
        page=1,
        per_page=20,
        unread_for=d["user_a"].id,
    )
    assert vazio.total == 0


_MEDIA_FILTER_CASES = [
    ("brand_id", lambda d: d["ids"]["brand_a"], "anexo_a"),
    ("status", lambda d: TicketStatus.FINALIZADO, "anexo_b"),
    ("solution_type_id", lambda d: d["ids"]["solution2"], "anexo_b"),
    ("defect_type_id", lambda d: d["ids"]["defect2"], "anexo_b"),
]


@pytest.mark.parametrize(
    ("field", "value_fn", "expected_key"),
    _MEDIA_FILTER_CASES,
    ids=[c[0] for c in _MEDIA_FILTER_CASES],
)
async def test_list_media_filtra_por_cada_criterio_isolado(
    tenant_session: AsyncSession,
    filter_dataset: dict[str, object],
    field: str,
    value_fn,  # noqa: ANN001
    expected_key: str,
) -> None:
    d = filter_dataset
    filters = MediaFilters(**{field: value_fn(d)})
    repo = SqlReportingRepository(tenant_session)
    rows, total = await repo.list_media(filters, page=1, per_page=20)
    assert total == 1
    assert rows[0].attachment.id == d[expected_key].id


async def test_list_media_filtra_por_periodo(
    tenant_session: AsyncSession, filter_dataset: dict[str, object]
) -> None:
    d = filter_dataset
    repo = SqlReportingRepository(tenant_session)
    rows, total = await repo.list_media(
        MediaFilters(date_from=NOW - timedelta(days=1), date_to=NOW + timedelta(days=1)),
        page=1,
        per_page=20,
    )
    assert total == 1
    assert rows[0].attachment.id == d["anexo_b"].id


# --- paginacao determinística (page 2), incluindo empates no criterio de ordenacao ---


async def test_report_pagina_2_nao_repete_nem_pula_tickets(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="pagina-rel@t.dev")
    ids = await seed_catalog(tenant_session)
    # mesmo opened_at para os tres: forca o empate que so o tiebreaker por id resolve
    tickets = [make_ticket(ids, user.id, opened_at=NOW) for _ in range(3)]
    tenant_session.add_all(tickets)
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    pagina1 = await repo.report(ReportFilters(), page=1, per_page=2, unread_for=user.id)
    pagina2 = await repo.report(ReportFilters(), page=2, per_page=2, unread_for=user.id)
    assert pagina1.total == 3
    ids_pagina1 = {t.ticket.id for t in pagina1.tickets}
    ids_pagina2 = {t.ticket.id for t in pagina2.tickets}
    assert len(ids_pagina1) == 2
    assert len(ids_pagina2) == 1
    assert ids_pagina1.isdisjoint(ids_pagina2)
    assert ids_pagina1 | ids_pagina2 == {t.id for t in tickets}


async def test_list_media_pagina_2_nao_repete_nem_pula_itens(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="pagina-media@t.dev")
    ids = await seed_catalog(tenant_session)
    t = make_ticket(ids, user.id)
    tenant_session.add(t)
    await tenant_session.flush()
    # mesmo created_at (server_default na mesma transacao) para forcar o empate
    anexos = [make_attachment(t.id, user.id) for _ in range(3)]
    tenant_session.add_all(anexos)
    await tenant_session.flush()

    repo = SqlReportingRepository(tenant_session)
    pagina1, total1 = await repo.list_media(MediaFilters(), page=1, per_page=2)
    pagina2, total2 = await repo.list_media(MediaFilters(), page=2, per_page=2)
    assert total1 == 3
    assert total2 == 3
    ids_pagina1 = {r.attachment.id for r in pagina1}
    ids_pagina2 = {r.attachment.id for r in pagina2}
    assert len(ids_pagina1) == 2
    assert len(ids_pagina2) == 1
    assert ids_pagina1.isdisjoint(ids_pagina2)
    assert ids_pagina1 | ids_pagina2 == {a.id for a in anexos}
