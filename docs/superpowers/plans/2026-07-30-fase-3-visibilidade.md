# Fase 3 (Visibilidade) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard com KPIs clicaveis e graficos, relatorios com filtros completos e export CSV fiel a tela, e galeria de midias do tenant — tudo somente leitura sobre os dados das Fases 1 e 2.

**Architecture:** Read model por SQL de agregacao, sem tabelas novas. Tres routers (`/api/dashboard`, `/api/relatorios` + `/export`, `/api/midias`) seguindo o padrao router -> use case -> port -> repositorio. No front, tres paginas novas com graficos em Recharts.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL, pytest (integracao contra Postgres real via docker compose), React + TypeScript + Vite, Recharts, Playwright.

**Spec:** `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3-visibilidade-design.md`

## Global Constraints

- PROIBIDO usar emojis em codigo, comentarios, commits, UI e documentacao.
- Clean Architecture: dominio sem framework; dependencias apontam para dentro; application define ports (Protocol), infrastructure implementa.
- TDD: escrever o teste, ver falhar, implementar o minimo, ver passar, commitar.
- Antes de CADA commit de backend (rodar em `backend/`): `ruff check .`, `ruff format --check .`, `mypy .`, `pytest` (integracao exige `docker compose up -d` na raiz: Postgres em localhost:5432 e MinIO em localhost:9000).
- Antes de CADA commit de frontend (rodar em `frontend/`): `pnpm exec tsc -b --noEmit` nao existe como script — usar `pnpm build` (roda `tsc -b` e o build) e `pnpm lint`.
- Gerenciador de pacotes do front e **pnpm** (nunca npm/yarn).
- Textos de UI e mensagens de erro em portugues sem acentos (padrao do codebase: "solucoes", "midias").
- Identificadores de codigo em ingles (padrao do codebase); rotas da API em portugues (`/relatorios`, `/midias`).

---

### Task 1: Permissao VER_VISIBILIDADE

**Files:**
- Modify: `backend/src/sac/domain/permissions.py`
- Test: `backend/tests/unit/domain/test_permissions_visibilidade.py`

**Interfaces:**
- Produces: `Permission.VER_VISIBILIDADE` (valor `"ver_visibilidade"`), concedida a todos os papeis de tenant. Tasks 6 e 7 usam nas dependencies dos routers.

- [ ] **Step 1: Write the failing test**

```python
from sac.domain.permissions import Permission, Role, has_permission


def test_todos_os_papeis_tem_ver_visibilidade() -> None:
    for role in Role:
        assert has_permission(role, Permission.VER_VISIBILIDADE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_permissions_visibilidade.py -v`
Expected: FAIL com `AttributeError: VER_VISIBILIDADE`

- [ ] **Step 3: Write minimal implementation**

Em `permissions.py`, adicionar ao enum `Permission`:

```python
    VER_VISIBILIDADE = "ver_visibilidade"
```

`ADMIN` e `SUPERVISOR` ja recebem via `frozenset(Permission)`. Adicionar `Permission.VER_VISIBILIDADE` aos frozensets de `ATENDENTE` e `VISUALIZADOR` em `ROLE_PERMISSIONS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_permissions_visibilidade.py -v`
Expected: PASS. Rodar tambem `pytest tests/unit -q` para garantir que nada quebrou.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy .
git add src/sac/domain/permissions.py tests/unit/domain/test_permissions_visibilidade.py
git commit -m "Adiciona permissao ver_visibilidade a todos os papeis de tenant"
```

---

### Task 2: Ports de reporting e query de dashboard

**Files:**
- Create: `backend/src/sac/application/ports_reporting.py`
- Create: `backend/src/sac/infrastructure/repositories_reporting.py`
- Test: `backend/tests/integration/test_repositories_reporting.py`

**Interfaces:**
- Consumes: `TicketListRow`, `TicketFilters` de `sac.application.ports_tickets`; `SqlTicketRepository` de `sac.infrastructure.repositories_tickets`; models de `sac.infrastructure.models_tenant`.
- Produces (usado pelas Tasks 3-7):

```python
# ports_reporting.py
@dataclass(frozen=True)
class RankingEntry:
    id: UUID
    name: str
    count: int

@dataclass(frozen=True)
class DashboardKpi:
    key: str          # "total", "abertos", "aguardando_analise", "atrasados",
                      # "aprovados_no_mes", "declinados_no_mes", "finalizados_no_mes"
    count: int
    filters: dict[str, str]   # query params para o card clicavel na lista

@dataclass(frozen=True)
class DashboardData:
    kpis: list[DashboardKpi]
    status_counts: dict[TicketStatus, int]
    products: list[RankingEntry]
    defects: list[RankingEntry]
    solutions: list[RankingEntry]
    avg_resolution_hours: float | None
    recent: list[TicketListRow]

class ReportingRepository(Protocol):
    async def dashboard(
        self, brand_id: UUID | None, unread_for: UUID, now: datetime
    ) -> DashboardData: ...
```

- `SqlReportingRepository(session)` em `repositories_reporting.py` implementa o protocol.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_repositories_reporting.py`. Segue o padrao dos testes de repositorio existentes: provisiona um tenant e abre sessao com `schema_translate_map`. Helpers de seed no proprio arquivo (as Tasks 3 e 4 os reutilizam):

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_reporting import DashboardData
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

pytestmark = pytest.mark.anyio


@pytest.fixture
async def tenant_session(
    session: AsyncSession, engine: AsyncEngine
) -> AsyncSession:
    await seed_provisioned_tenant(session, engine, slug="rep")
    scoped = engine.execution_options(schema_translate_map={"tenant": "t_rep"})
    factory = async_sessionmaker(scoped, expire_on_commit=False)
    async with factory() as ts:
        yield ts


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


async def seed_catalog(ts: AsyncSession) -> dict[str, UUID]:
    brand_a = BrandModel(id=uuid4(), name="KODI")
    brand_b = BrandModel(id=uuid4(), name="STALEKS")
    product = ProductModel(id=uuid4(), name="Alicate", sku="PLN-10-7")
    product2 = ProductModel(id=uuid4(), name="Esmalte", sku="ESM-1")
    defect = DefectTypeModel(id=uuid4(), name="Oxidacao")
    solution = SolutionTypeModel(id=uuid4(), name="Troca pelo mesmo item")
    customer = CustomerModel(id=uuid4(), name="Cliente Rep", document="52998224725")
    ts.add_all([brand_a, brand_b, product, product2, defect, solution, customer])
    await ts.flush()
    return {
        "brand_a": brand_a.id, "brand_b": brand_b.id,
        "product": product.id, "product2": product2.id,
        "defect": defect.id, "solution": solution.id, "customer": customer.id,
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
        id=uuid4(), ticket_id=ticket_id,
        product_id=product_id, defect_type_id=defect_id, quantity=quantity,
    )


async def test_dashboard_kpis_distribuicao_rankings_e_tempo_medio(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep@t.dev")
    ids = await seed_catalog(tenant_session)
    aberto = make_ticket(ids, user.id)
    atrasado = make_ticket(
        ids, user.id, status=TicketStatus.AGUARDANDO_ANALISE,
        opened_at=NOW - timedelta(days=10),
    )
    finalizado = make_ticket(
        ids, user.id, status=TicketStatus.FINALIZADO,
        opened_at=NOW - timedelta(days=2), approved_at=NOW - timedelta(days=1),
        closed_at=NOW - timedelta(hours=24), solution=True,
    )
    declinado_mes_passado = make_ticket(
        ids, user.id, status=TicketStatus.DECLINADO,
        opened_at=datetime(2026, 6, 10, tzinfo=UTC),
        declined_at=datetime(2026, 6, 11, tzinfo=UTC),
        closed_at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    excluido = make_ticket(ids, user.id, deleted_at=NOW)
    tenant_session.add_all([aberto, atrasado, finalizado, declinado_mes_passado, excluido])
    await tenant_session.flush()
    tenant_session.add_all([
        make_item(aberto.id, ids["product"], ids["defect"], quantity=2),
        make_item(finalizado.id, ids["product"], ids["defect"], quantity=1),
        make_item(finalizado.id, ids["product2"], ids["defect"], quantity=1),
    ])
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_repositories_reporting.py -v`
Expected: FAIL com `ModuleNotFoundError: sac.application.ports_reporting`

- [ ] **Step 3: Write minimal implementation**

`ports_reporting.py` com os dataclasses e o protocol do bloco Interfaces (imports: `dataclass`, `datetime`, `Protocol`, `UUID`, `TicketListRow` de `ports_tickets`, `TicketStatus` de `domain.tickets`).

`repositories_reporting.py`:

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_reporting import DashboardData, DashboardKpi, RankingEntry
from sac.application.ports_tickets import TicketFilters
from sac.domain.tickets import CLOSED_STATUSES, TicketStatus
from sac.infrastructure.models_tenant import (
    DefectTypeModel,
    ProductModel,
    SolutionTypeModel,
    TicketItemModel,
    TicketModel,
)
from sac.infrastructure.repositories_tickets import SqlTicketRepository

_CLOSED = [str(s) for s in CLOSED_STATUSES]


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_start = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, next_start


class SqlReportingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _tickets(self, brand_id: UUID | None):  # noqa: ANN202
        stmt = select(TicketModel).where(TicketModel.deleted_at.is_(None))
        if brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == brand_id)
        return stmt

    async def _count(self, stmt) -> int:  # noqa: ANN001
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return int(total or 0)

    async def dashboard(
        self, brand_id: UUID | None, unread_for: UUID, now: datetime
    ) -> DashboardData:
        base = self._tickets(brand_id)
        month_start, month_end = _month_bounds(now)
        kpis = [
            DashboardKpi("total", await self._count(base), {}),
            DashboardKpi(
                "abertos",
                await self._count(base.where(TicketModel.status == str(TicketStatus.ABERTO))),
                {"status": "aberto"},
            ),
            DashboardKpi(
                "aguardando_analise",
                await self._count(
                    base.where(TicketModel.status == str(TicketStatus.AGUARDANDO_ANALISE))
                ),
                {"status": "aguardando_analise"},
            ),
            DashboardKpi(
                "atrasados",
                await self._count(
                    base.where(TicketModel.due_at < now, TicketModel.status.not_in(_CLOSED))
                ),
                {"overdue": "1"},
            ),
            DashboardKpi(
                "aprovados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.approved_at >= month_start,
                        TicketModel.approved_at < month_end,
                    )
                ),
                {"status": "aprovado"},
            ),
            DashboardKpi(
                "declinados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.declined_at >= month_start,
                        TicketModel.declined_at < month_end,
                    )
                ),
                {"status": "declinado"},
            ),
            DashboardKpi(
                "finalizados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.status == str(TicketStatus.FINALIZADO),
                        TicketModel.closed_at >= month_start,
                        TicketModel.closed_at < month_end,
                    )
                ),
                {"status": "finalizado"},
            ),
        ]
        status_rows = await self._session.execute(
            base.with_only_columns(TicketModel.status, func.count())
            .group_by(TicketModel.status)
        )
        status_counts = {s: 0 for s in TicketStatus}
        for status, count in status_rows.all():
            status_counts[TicketStatus(status)] = int(count)

        products = await self._ranking_items(brand_id, ProductModel, TicketItemModel.product_id)
        defects = await self._ranking_items(
            brand_id, DefectTypeModel, TicketItemModel.defect_type_id
        )
        solutions = await self._ranking_solutions(brand_id)

        avg_seconds = await self._session.scalar(
            base.with_only_columns(
                func.avg(
                    func.extract("epoch", TicketModel.closed_at - TicketModel.opened_at)
                )
            ).where(
                TicketModel.status == str(TicketStatus.FINALIZADO),
                TicketModel.closed_at.is_not(None),
            )
        )
        recent, _ = await SqlTicketRepository(self._session).list(
            TicketFilters(brand_id=brand_id),
            page=1, per_page=10, sort="last_activity_at", order="desc",
            unread_for=unread_for,
        )
        return DashboardData(
            kpis=kpis,
            status_counts=status_counts,
            products=products,
            defects=defects,
            solutions=solutions,
            avg_resolution_hours=float(avg_seconds) / 3600 if avg_seconds is not None else None,
            recent=recent,
        )

    async def _ranking_items(
        self, brand_id: UUID | None, model, fk  # noqa: ANN001
    ) -> list[RankingEntry]:
        stmt = (
            select(model.id, model.name, func.sum(TicketItemModel.quantity))
            .join(TicketItemModel, fk == model.id)
            .join(TicketModel, TicketItemModel.ticket_id == TicketModel.id)
            .where(TicketModel.deleted_at.is_(None))
            .group_by(model.id, model.name)
            .order_by(func.sum(TicketItemModel.quantity).desc(), model.name.asc())
            .limit(5)
        )
        if brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == brand_id)
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]

    async def _ranking_solutions(self, brand_id: UUID | None) -> list[RankingEntry]:
        stmt = (
            select(SolutionTypeModel.id, SolutionTypeModel.name, func.count())
            .join(TicketModel, TicketModel.solution_type_id == SolutionTypeModel.id)
            .where(TicketModel.deleted_at.is_(None))
            .group_by(SolutionTypeModel.id, SolutionTypeModel.name)
            .order_by(func.count().desc(), SolutionTypeModel.name.asc())
            .limit(5)
        )
        if brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == brand_id)
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]
```

Ajustar tipagem ate `mypy` passar (usar `Select[Any]` nos helpers se preciso).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_repositories_reporting.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add src/sac/application/ports_reporting.py src/sac/infrastructure/repositories_reporting.py tests/integration/test_repositories_reporting.py
git commit -m "Adiciona read model de dashboard com agregacoes por SQL"
```

---

### Task 3: Query de relatorio e linhas de export

**Files:**
- Modify: `backend/src/sac/application/ports_reporting.py`
- Modify: `backend/src/sac/infrastructure/repositories_reporting.py`
- Test: `backend/tests/integration/test_repositories_reporting.py` (acrescentar)

**Interfaces:**
- Consumes: helpers de seed da Task 2 no mesmo arquivo de teste.
- Produces (Tasks 5-7 dependem):

```python
@dataclass(frozen=True)
class ReportFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    brand_id: UUID | None = None
    product_id: UUID | None = None
    defect_type_id: UUID | None = None
    solution_type_id: UUID | None = None
    status: TicketStatus | None = None
    attendant_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None

@dataclass(frozen=True)
class ReportKpis:
    total: int
    finalized: int
    declined: int
    avg_resolution_hours: float | None

@dataclass(frozen=True)
class ReportData:
    kpis: ReportKpis
    products: list[RankingEntry]
    defects: list[RankingEntry]
    solutions: list[RankingEntry]
    tickets: list[TicketListRow]
    total: int

@dataclass(frozen=True)
class ReportExportRow:
    number: int
    brand: str | None
    status: str
    priority: str
    customer_name: str | None
    customer_document: str | None
    customer_phone: str | None
    customer_email: str | None
    products: str        # "Alicate x2; Esmalte x1"
    defects: str
    solution: str | None
    channel: str | None
    attendant: str | None
    order_code: str | None
    opened_at: datetime
    closed_at: datetime | None

# no ReportingRepository (Protocol):
    async def report(
        self, filters: ReportFilters, page: int, per_page: int, unread_for: UUID
    ) -> ReportData: ...
    async def export_rows(
        self, filters: ReportFilters, page: int, per_page: int
    ) -> list[ReportExportRow]: ...
```

- [ ] **Step 1: Write the failing tests** (acrescentar ao arquivo da Task 2)

```python
from sac.application.ports_reporting import ReportFilters


async def test_report_aplica_mesmo_recorte_em_kpis_rankings_e_tabela(
    session: AsyncSession, tenant_session: AsyncSession
) -> None:
    user = await seed_user(session, email="rep3@t.dev")
    ids = await seed_catalog(tenant_session)
    dentro = make_ticket(
        ids, user.id, status=TicketStatus.FINALIZADO,
        opened_at=datetime(2026, 7, 10, tzinfo=UTC),
        closed_at=datetime(2026, 7, 12, tzinfo=UTC), solution=True,
    )
    fora_do_periodo = make_ticket(
        ids, user.id, opened_at=datetime(2026, 5, 1, tzinfo=UTC)
    )
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
    t = make_ticket(ids, user.id, status=TicketStatus.FINALIZADO,
                    closed_at=NOW, solution=True)
    tenant_session.add(t)
    await tenant_session.flush()
    tenant_session.add_all([
        make_item(t.id, ids["product"], ids["defect"], quantity=2),
        make_item(t.id, ids["product2"], ids["defect"], quantity=1),
    ])
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_repositories_reporting.py -v -k "report or export"`
Expected: FAIL com `ImportError: ReportFilters`

- [ ] **Step 3: Write minimal implementation**

Em `ports_reporting.py`, adicionar os dataclasses e os dois metodos ao protocol (bloco Interfaces acima).

Em `repositories_reporting.py`, adicionar a `SqlReportingRepository`:

```python
    def _report_stmt(self, filters: ReportFilters):  # noqa: ANN202
        stmt = select(TicketModel).where(TicketModel.deleted_at.is_(None))
        if filters.date_from is not None:
            stmt = stmt.where(TicketModel.opened_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(TicketModel.opened_at < filters.date_to)
        if filters.brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == filters.brand_id)
        if filters.status is not None:
            stmt = stmt.where(TicketModel.status == str(filters.status))
        if filters.solution_type_id is not None:
            stmt = stmt.where(TicketModel.solution_type_id == filters.solution_type_id)
        if filters.attendant_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == filters.attendant_user_id)
        if filters.purchase_channel_id is not None:
            stmt = stmt.where(TicketModel.purchase_channel_id == filters.purchase_channel_id)
        if filters.product_id is not None:
            stmt = stmt.where(
                exists(
                    select(TicketItemModel.id).where(
                        TicketItemModel.ticket_id == TicketModel.id,
                        TicketItemModel.product_id == filters.product_id,
                    )
                )
            )
        if filters.defect_type_id is not None:
            stmt = stmt.where(
                exists(
                    select(TicketItemModel.id).where(
                        TicketItemModel.ticket_id == TicketModel.id,
                        TicketItemModel.defect_type_id == filters.defect_type_id,
                    )
                )
            )
        return stmt
```

`report()`: conta `total` sobre `_report_stmt`; `finalized`/`declined` com `where status == ...`; tempo medio igual ao dashboard mas sobre o recorte; rankings iguais aos do dashboard porem com um `where TicketModel.id.in_(select(_report_stmt.subquery().c.id))` (extrair um helper `_ranking_items(base_ids_select, model, fk)` compartilhado entre dashboard e report para nao duplicar — refatorar a versao da Task 2 para receber a subquery de ids em vez de `brand_id`); a tabela paginada reusa `SqlTicketRepository.list` NAO — ela nao conhece os filtros novos; em vez disso paginar `_report_stmt` ordenado por `opened_at desc` e montar `TicketListRow` com a mesma tecnica de `SqlTicketRepository.list` (joins de customer/read, contagem de itens e primeiro produto). Para os nomes de atendente, `report()` nao resolve nomes (isso ja e papel do `SqlUserDirectory` no use case, igual `ListTicketsUseCase`).

`export_rows()`: pagina `_report_stmt` ordenado por `opened_at desc` com `offset/limit`; junta `BrandModel.name`, `CustomerModel` (name/document/phone/email), `SolutionTypeModel.name`, `PurchaseChannelModel.name` por outerjoin; agrega itens dos tickets da pagina em uma query separada (`select(TicketItemModel.ticket_id, ProductModel.name, DefectTypeModel.name, TicketItemModel.quantity)` com joins) e monta as strings `"Nome xQ; ..."` ordenadas por criacao; nomes de atendente via `select(UserModel.id, UserModel.name)` (import de `sac.infrastructure.models`), padrao ja usado em `SqlUserDirectory`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_repositories_reporting.py -v`
Expected: PASS (incluindo os da Task 2, que nao podem regredir com a refatoracao do ranking)

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add src/sac/application/ports_reporting.py src/sac/infrastructure/repositories_reporting.py tests/integration/test_repositories_reporting.py
git commit -m "Adiciona queries de relatorio com filtros e linhas de export"
```

---

### Task 4: Query da galeria de midias

**Files:**
- Modify: `backend/src/sac/application/ports_reporting.py`
- Modify: `backend/src/sac/infrastructure/repositories_reporting.py`
- Test: `backend/tests/integration/test_repositories_reporting.py` (acrescentar)

**Interfaces:**
- Consumes: `TicketAttachment` de `sac.domain.attachments`; `TicketAttachmentModel` de models_tenant; helpers de seed das Tasks 2-3.
- Produces (Tasks 5-6 dependem):

```python
@dataclass(frozen=True)
class MediaFilters:
    kind: AttachmentKind | None = None      # de sac.domain.attachments
    brand_id: UUID | None = None
    product_id: UUID | None = None
    defect_type_id: UUID | None = None
    solution_type_id: UUID | None = None
    status: TicketStatus | None = None
    date_from: datetime | None = None       # created_at do anexo
    date_to: datetime | None = None

@dataclass(frozen=True)
class MediaItemRow:
    attachment: TicketAttachment
    ticket_number: int

# no ReportingRepository (Protocol):
    async def list_media(
        self, filters: MediaFilters, page: int, per_page: int
    ) -> tuple[list[MediaItemRow], int]: ...
```

- [ ] **Step 1: Write the failing test** (acrescentar; usar o `_attachment_entity`/campos do model como em `repositories_attachments.py`)

```python
from sac.application.ports_reporting import MediaFilters
from sac.domain.attachments import AttachmentKind
from sac.infrastructure.models_tenant import TicketAttachmentModel


def make_attachment(
    ticket_id: UUID, author: UUID, *,
    kind: str = "imagem", status: str = "disponivel",
    deleted_at: datetime | None = None,
) -> TicketAttachmentModel:
    return TicketAttachmentModel(
        id=uuid4(), ticket_id=ticket_id, filename="foto.jpg",
        content_type="image/jpeg", size_bytes=1000,
        object_key=f"rep/{ticket_id}/{uuid4()}.jpg", kind=kind, status=status,
        preview_status="pronto" if kind == "imagem" else "sem_preview",
        preview_key="k.webp" if kind == "imagem" else None,
        author_user_id=author, deleted_at=deleted_at,
    )


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
```

Conferir o nome do enum em `sac/domain/attachments.py` (`AttachmentKind.IMAGEM` etc.) e o valor de status confirmado (`"disponivel"`) antes de rodar; ajustar o teste se os literais divergirem.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_repositories_reporting.py -v -k media`
Expected: FAIL com `ImportError: MediaFilters`

- [ ] **Step 3: Write minimal implementation**

`list_media`: base `select(TicketAttachmentModel, TicketModel.number).join(TicketModel, TicketAttachmentModel.ticket_id == TicketModel.id).where(TicketAttachmentModel.deleted_at.is_(None), TicketAttachmentModel.status == "disponivel", TicketModel.deleted_at.is_(None))`; filtros de `kind` e `created_at` no anexo; `brand_id`/`status`/`solution_type_id` no ticket; `product_id`/`defect_type_id` via `exists` em `TicketItemModel` (mesmo padrao da Task 3); count por subquery; ordenacao `TicketAttachmentModel.created_at.desc()`; offset/limit; converter para entidade `TicketAttachment` reaproveitando o construtor de entidade de `repositories_attachments.py` (se la for funcao privada `_entity`, promover para funcao de modulo `attachment_entity(m)` reutilizavel e importar — ajustar o call site existente).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_repositories_reporting.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add -A src/sac tests/integration/test_repositories_reporting.py
git commit -m "Adiciona query da galeria de midias sobre anexos confirmados"
```

---

### Task 5: Use cases de reporting e render de CSV

**Files:**
- Create: `backend/src/sac/application/use_cases/reporting.py`
- Create: `backend/src/sac/infrastructure/csv_export.py`
- Test: `backend/tests/unit/application/test_reporting_use_cases.py`
- Test: `backend/tests/unit/infrastructure/test_csv_export.py`

**Interfaces:**
- Consumes: protocol `ReportingRepository` e dataclasses das Tasks 2-4; `StoragePort` de `ports_attachments`; `UserDirectoryPort` de `ports_tickets`.
- Produces (Task 6-7 usam):

```python
# use_cases/reporting.py
class GetDashboardUseCase:
    def __init__(self, repo: ReportingRepository, users: UserDirectoryPort) -> None: ...
    async def execute(
        self, actor: TicketActor, brand_id: UUID | None, now: datetime
    ) -> tuple[DashboardData, dict[UUID, str]]: ...
    # devolve tambem nomes de atendentes dos recentes (padrao ListTicketsUseCase)

class GetReportUseCase:
    def __init__(self, repo: ReportingRepository, users: UserDirectoryPort) -> None: ...
    async def execute(
        self, actor: TicketActor, filters: ReportFilters, page: int, per_page: int
    ) -> tuple[ReportData, dict[UUID, str]]: ...

class ExportReportUseCase:
    def __init__(self, repo: ReportingRepository, chunk_size: int = 500) -> None: ...
    def stream(self, filters: ReportFilters) -> AsyncIterator[list[ReportExportRow]]: ...
    # async generator: pagina o repositorio ate vir pagina vazia

class ListMediaUseCase:
    def __init__(
        self, repo: ReportingRepository, storage: StoragePort, ttl_seconds: int = 300
    ) -> None: ...
    async def execute(
        self, filters: MediaFilters, page: int, per_page: int
    ) -> tuple[list[MediaView], int]: ...

@dataclass(frozen=True)
class MediaView:
    attachment: TicketAttachment
    ticket_number: int
    preview_url: str | None   # presigned da thumb quando preview_status == PRONTO

# infrastructure/csv_export.py
CSV_HEADER: tuple[str, ...] = (
    "numero", "marca", "status", "prioridade", "cliente", "documento", "telefone",
    "email", "produtos", "defeitos", "solucao", "canal", "atendente", "pedido",
    "aberto_em", "fechado_em",
)
def csv_line(values: Sequence[str | int | None]) -> str: ...  # quoting RFC4180, \r\n
def export_row_values(row: ReportExportRow) -> list[str | int | None]: ...
```

- [ ] **Step 1: Write the failing tests**

`tests/unit/infrastructure/test_csv_export.py`:

```python
from datetime import UTC, datetime

from sac.application.ports_reporting import ReportExportRow
from sac.infrastructure.csv_export import CSV_HEADER, csv_line, export_row_values


def _row() -> ReportExportRow:
    return ReportExportRow(
        number=7, brand="KODI", status="finalizado", priority="media",
        customer_name='Cliente "Especial"', customer_document="52998224725",
        customer_phone=None, customer_email=None,
        products="Alicate x2", defects="Oxidacao x2",
        solution="Troca, pelo mesmo item", channel=None, attendant="Ana",
        order_code=None,
        opened_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        closed_at=None,
    )


def test_csv_line_escapa_aspas_e_virgulas() -> None:
    line = csv_line(export_row_values(_row()))
    assert '"Cliente ""Especial"""' in line
    assert '"Troca, pelo mesmo item"' in line
    assert line.endswith("\r\n")
    assert line.startswith("7,KODI,finalizado")


def test_header_e_valores_tem_mesmo_tamanho() -> None:
    assert len(CSV_HEADER) == len(export_row_values(_row()))
```

`tests/unit/application/test_reporting_use_cases.py` (fakes locais no proprio teste):

```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sac.application.ports_reporting import MediaFilters, MediaItemRow, ReportFilters
from sac.application.use_cases.reporting import ExportReportUseCase, ListMediaUseCase
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewStatus,
    TicketAttachment,
)

pytestmark = pytest.mark.anyio


def _attachment(preview: PreviewStatus, preview_key: str | None) -> TicketAttachment:
    return TicketAttachment(
        id=uuid4(), ticket_id=uuid4(), filename="a.jpg", content_type="image/jpeg",
        size_bytes=10, object_key="k.jpg", kind=AttachmentKind.IMAGEM,
        status=AttachmentStatus.DISPONIVEL, preview_status=preview,
        preview_key=preview_key, author_user_id=uuid4(),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    # conferir a assinatura real do dataclass em domain/attachments.py e ajustar


class FakeReportingRepo:
    def __init__(self, media=(), export_pages=()):  # noqa: ANN001
        self._media = list(media)
        self._pages = list(export_pages)

    async def list_media(self, filters, page, per_page):  # noqa: ANN001
        return self._media, len(self._media)

    async def export_rows(self, filters, page, per_page):  # noqa: ANN001
        return self._pages[page - 1] if page <= len(self._pages) else []


class FakeStorage:
    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        return f"https://signed/{key}"


async def test_list_media_assina_preview_pronto_e_deixa_none_sem_preview() -> None:
    rows = [
        MediaItemRow(_attachment(PreviewStatus.PRONTO, "thumb.webp"), ticket_number=1),
        MediaItemRow(_attachment(PreviewStatus.PENDENTE, None), ticket_number=2),
    ]
    views, total = await ListMediaUseCase(FakeReportingRepo(media=rows), FakeStorage()).execute(
        MediaFilters(), page=1, per_page=10
    )
    assert total == 2
    assert views[0].preview_url == "https://signed/thumb.webp"
    assert views[1].preview_url is None


async def test_export_stream_pagina_ate_esgotar() -> None:
    pages = [["r1", "r2"], ["r3"]]  # o use case nao inspeciona as linhas
    use_case = ExportReportUseCase(FakeReportingRepo(export_pages=pages), chunk_size=2)
    got = [chunk async for chunk in use_case.stream(ReportFilters())]
    assert got == [["r1", "r2"], ["r3"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/infrastructure/test_csv_export.py tests/unit/application/test_reporting_use_cases.py -v`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`csv_export.py`: `csv_line` usa `io.StringIO` + `csv.writer(sio, lineterminator="\r\n")`; `export_row_values` formata datetimes com `.strftime("%Y-%m-%d %H:%M")` e `None` vira `""`.

`use_cases/reporting.py`: implementar as quatro classes do bloco Interfaces. `GetDashboardUseCase.execute` chama `repo.dashboard(brand_id, actor.user_id, now)` e resolve nomes dos atendentes dos `recent` via `users.names_by_ids({r.ticket.attendant_user_id for r in data.recent})`. `GetReportUseCase` analogo sobre `data.tickets`. `ExportReportUseCase.stream` e um async generator (`while True: rows = await repo.export_rows(filters, page, chunk); if not rows: return; yield rows; page += 1`). `ListMediaUseCase` monta `MediaView` assinando `preview_key` apenas quando `preview_status == PreviewStatus.PRONTO and preview_key`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit -q`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add src/sac/application/use_cases/reporting.py src/sac/infrastructure/csv_export.py tests/unit/application/test_reporting_use_cases.py tests/unit/infrastructure/test_csv_export.py
git commit -m "Adiciona use cases de visibilidade e render de CSV"
```

---

### Task 6: Schemas, routers e API de dashboard, relatorios e midias

**Files:**
- Create: `backend/src/sac/interface/schemas_reporting.py`
- Create: `backend/src/sac/interface/routers/reporting.py`
- Modify: `backend/src/sac/interface/deps.py` (adicionar `get_reporting_repository`)
- Modify: `backend/src/sac/interface/app.py` (incluir os tres routers)
- Test: `backend/tests/integration/test_reporting_api.py`

**Interfaces:**
- Consumes: use cases da Task 5; `require_permission(Permission.VER_VISIBILIDADE)`; `ticket_list_item_out`/`TicketListItemOut` de `interface/schemas.py`; `get_tenant_session`, `get_storage`, `get_ticket_repos` de deps.
- Produces:
  - `GET /api/dashboard?brand_id=` -> `DashboardOut`
  - `GET /api/relatorios?de=&ate=&brand_id=&product_id=&defect_type_id=&solution_type_id=&status=&atendente_id=&channel_id=&page=&per_page=` -> `ReportOut`
  - `GET /api/midias?kind=&brand_id=&product_id=&defect_type_id=&solution_type_id=&status=&de=&ate=&page=&per_page=` -> `MediaPageOut`

Schemas (`schemas_reporting.py`):

```python
class RankingOut(BaseModel):
    id: UUID
    name: str
    count: int

class DashboardKpiOut(BaseModel):
    key: str
    count: int
    filters: dict[str, str]

class DashboardOut(BaseModel):
    kpis: list[DashboardKpiOut]
    status_counts: dict[TicketStatus, int]
    products: list[RankingOut]
    defects: list[RankingOut]
    solutions: list[RankingOut]
    avg_resolution_hours: float | None
    recent: list[TicketListItemOut]

class ReportKpisOut(BaseModel):
    total: int
    finalized: int
    declined: int
    avg_resolution_hours: float | None

class ReportOut(BaseModel):
    kpis: ReportKpisOut
    products: list[RankingOut]
    defects: list[RankingOut]
    solutions: list[RankingOut]
    items: list[TicketListItemOut]
    total: int
    page: int
    per_page: int

class MediaItemOut(BaseModel):
    id: UUID
    ticket_id: UUID
    ticket_number: int
    filename: str
    kind: AttachmentKind
    content_type: str
    size_bytes: int
    created_at: datetime
    preview_url: str | None

class MediaPageOut(BaseModel):
    items: list[MediaItemOut]
    total: int
    page: int
    per_page: int
```

Nota: `ticket_list_item_out(row)` preenche `attendant_name=row.attendant_name`; os endpoints novos devem montar `TicketListRow` com `attendant_name` vindo do dict de nomes (`dataclasses.replace(row, attendant_name=names.get(row.ticket.attendant_user_id))`) antes de chamar o helper — mesmo padrao do endpoint de lista em `routers/tickets.py` (conferir como `list_tickets` faz e copiar).

- [ ] **Step 1: Write the failing test**

`tests/integration/test_reporting_api.py` — seed via API (padrao de `test_tickets_api.py`): criar tenant provisionado + admin + visualizador com `seed_provisioned_tenant`/`seed_user`/`seed_link`/`token_for` de `tests/integration/helpers.py`; criar marca/produto/defeito/solucao via `POST /api/marcas` etc.; criar tickets via `POST /api/tickets` e transicionar via rotas de workflow.

```python
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

pytestmark = pytest.mark.anyio


async def _setup(client: AsyncClient, session: AsyncSession, engine: AsyncEngine):
    tenant = await seed_provisioned_tenant(session, engine, slug="vis")
    admin = await seed_user(session, email="admin@vis.dev", name="Admin Vis")
    viewer = await seed_user(session, email="view@vis.dev")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    h_admin = token_for(admin, tenant_slug="vis", role=Role.ADMIN)
    h_view = token_for(viewer, tenant_slug="vis", role=Role.VISUALIZADOR)

    async def post(path: str, body: dict) -> dict:
        res = await client.post(f"/api{path}", json=body, headers=h_admin)
        assert res.status_code == 201, res.text
        return res.json()

    brand = await post("/marcas", {"name": "KODI"})
    product = await post("/produtos", {"name": "Alicate", "sku": f"SKU-{uuid4().hex[:6]}"})
    defect = await post("/defeitos", {"name": "Oxidacao"})
    solution = await post("/solucoes", {"name": "Troca"})
    ticket = await post(
        "/tickets",
        {
            "brand_id": brand["id"],
            "priority": "media",
            "customer": {"name": "Cliente Vis", "document": "52998224725"},
            "description": "produto oxidado",
            "items": [
                {"product_id": product["id"], "defect_type_id": defect["id"], "quantity": 2}
            ],
        },
    )
    return h_admin, h_view, brand, product, defect, solution, ticket


async def test_dashboard_conta_e_exige_permissao(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, *_ = await _setup(client, session, engine)

    res = await client.get("/api/dashboard", headers=h_view)
    assert res.status_code == 200
    body = res.json()
    kpis = {k["key"]: k["count"] for k in body["kpis"]}
    assert kpis["total"] == 1
    assert kpis["abertos"] == 1
    assert body["status_counts"]["aberto"] == 1
    assert body["products"][0]["count"] == 2
    assert body["recent"][0]["customer_name"] == "Cliente Vis"
    assert body["kpis"][1]["filters"] == {"status": "aberto"}

    outro_brand = await client.get(
        f"/api/dashboard?brand_id={uuid4()}", headers=h_view
    )
    assert outro_brand.status_code == 200
    assert {k["key"]: k["count"] for k in outro_brand.json()["kpis"]}["total"] == 0

    sem_token = await client.get("/api/dashboard")
    assert sem_token.status_code == 401


async def test_relatorio_filtra_e_pagina(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, product, defect, solution, ticket = await _setup(
        client, session, engine
    )
    res = await client.get(
        f"/api/relatorios?product_id={product['id']}", headers=h_view
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kpis"]["total"] == 1
    assert body["total"] == 1
    assert body["items"][0]["number"] == ticket["number"]

    vazio = await client.get(f"/api/relatorios?product_id={uuid4()}", headers=h_view)
    assert vazio.json()["kpis"]["total"] == 0

    invalido = await client.get("/api/relatorios?de=nao-e-data", headers=h_view)
    assert invalido.status_code == 422


async def test_midias_lista_vazia_sem_anexos(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, h_view, *_ = await _setup(client, session, engine)
    res = await client.get("/api/midias", headers=h_view)
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0, "page": 1, "per_page": 20}
```

Conferir os campos exigidos por `POST /api/tickets` e pelos CRUDs de cadastro em `test_tickets_api.py`/`test_cadastros_catalog_api.py` e ajustar os bodies do `_setup` para o shape real.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_reporting_api.py -v`
Expected: FAIL com 404 (rotas inexistentes)

- [ ] **Step 3: Write minimal implementation**

`deps.py`:

```python
def get_reporting_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlReportingRepository:
    return SqlReportingRepository(session)
```

`routers/reporting.py`:

```python
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
relatorios_router = APIRouter(prefix="/relatorios", tags=["relatorios"])
midias_router = APIRouter(prefix="/midias", tags=["midias"])

_view = require_permission(Permission.VER_VISIBILIDADE)


@dashboard_router.get("", response_model=DashboardOut)
async def get_dashboard(
    brand_id: UUID | None = None,
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
    ticket_repos: TicketRepos = Depends(get_ticket_repos),
) -> DashboardOut:
    data, names = await GetDashboardUseCase(repo, ticket_repos.users).execute(
        _actor(identity), brand_id, datetime.now(UTC)
    )
    ...  # montar DashboardOut; recent via replace(row, attendant_name=...) + ticket_list_item_out
```

`GET /api/relatorios`: query params `de: datetime | None`, `ate: datetime | None`, demais UUIDs/status; montar `ReportFilters(date_from=de, date_to=ate, ...)`; clamp de paginacao igual `list_tickets` (`page=max(page,1)`, `per_page=min(max(per_page,1),100)`). `GET /api/midias`: params -> `MediaFilters`; use case com `get_storage`. Copiar `_actor` local (funcao de 3 linhas) em vez de importar do router de tickets. Registrar os tres routers em `app.py` apos `members.router`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_reporting_api.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add -A src/sac tests/integration/test_reporting_api.py
git commit -m "Adiciona rotas de dashboard, relatorios e midias"
```

---

### Task 7: Endpoint de export CSV

**Files:**
- Modify: `backend/src/sac/interface/routers/reporting.py`
- Test: `backend/tests/integration/test_reporting_api.py` (acrescentar)

**Interfaces:**
- Consumes: `ExportReportUseCase`, `csv_line`, `export_row_values`, `CSV_HEADER` da Task 5; `_setup` da Task 6.
- Produces: `GET /api/relatorios/export` com os mesmos query params de filtro de `/api/relatorios` (sem paginacao), resposta `text/csv; charset=utf-8`, BOM UTF-8, `Content-Disposition: attachment; filename="relatorio-tickets.csv"`.

- [ ] **Step 1: Write the failing test**

```python
async def test_export_csv_com_bom_e_mesmos_filtros_da_tela(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, product, *_ = await _setup(client, session, engine)

    res = await client.get("/api/relatorios/export", headers=h_view)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    text = res.text
    assert text.startswith("\ufeffnumero,")
    linhas = [l for l in text.splitlines() if l.strip()]
    assert len(linhas) == 2  # header + 1 ticket
    assert "Cliente Vis" in linhas[1]
    assert "Alicate x2" in linhas[1]

    # paridade: filtro que zera a tela zera o CSV
    produto_inexistente = uuid4()
    tela = await client.get(
        f"/api/relatorios?product_id={produto_inexistente}", headers=h_view
    )
    vazio = await client.get(
        f"/api/relatorios/export?product_id={produto_inexistente}", headers=h_view
    )
    assert tela.json()["kpis"]["total"] == 0
    assert len([l for l in vazio.text.splitlines() if l.strip()]) == 1  # so o header
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_reporting_api.py -v -k export`
Expected: FAIL com 404

- [ ] **Step 3: Write minimal implementation**

No `relatorios_router` (declarar ANTES de qualquer rota `/{...}` se existir; aqui nao ha, mas manter `/export` acima de futuras rotas dinamicas):

```python
@relatorios_router.get("/export")
async def export_relatorio(
    de: datetime | None = None,
    ate: datetime | None = None,
    # ... mesmos params de filtro do GET /relatorios ...
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
) -> StreamingResponse:
    filters = ReportFilters(date_from=de, date_to=ate, ...)
    use_case = ExportReportUseCase(repo)

    async def stream() -> AsyncIterator[str]:
        yield "\ufeff" + csv_line(list(CSV_HEADER))
        async for chunk in use_case.stream(filters):
            for row in chunk:
                yield csv_line(export_row_values(row))

    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="relatorio-tickets.csv"'},
    )
```

A sessao do tenant (dependency com yield) permanece aberta durante o streaming: no FastAPI atual o teardown de dependencies roda depois da resposta ser enviada. Se um teste flakar com sessao fechada, materializar as linhas no handler (volume atual e pequeno) e manter o generator so para a serializacao.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_reporting_api.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy . && pytest -q
git add src/sac/interface/routers/reporting.py tests/integration/test_reporting_api.py
git commit -m "Adiciona export CSV do relatorio com os mesmos filtros da tela"
```

---

### Task 8: Front — Recharts e client de reporting

**Files:**
- Modify: `frontend/package.json` (via pnpm)
- Create: `frontend/src/lib/reporting.ts`

**Interfaces:**
- Consumes: `api` de `@/lib/api`; tipos `TicketListItem`, `TicketStatus` de `@/lib/tickets`; `loadSession` de `@/lib/api` para o download autenticado.
- Produces (Tasks 10-12 usam):

```typescript
export type RankingEntry = { id: string; name: string; count: number }
export type DashboardKpi = { key: string; count: number; filters: Record<string, string> }
export type Dashboard = {
  kpis: DashboardKpi[]
  status_counts: Record<TicketStatus, number>
  products: RankingEntry[]
  defects: RankingEntry[]
  solutions: RankingEntry[]
  avg_resolution_hours: number | null
  recent: TicketListItem[]
}
export type ReportParams = {
  de?: string; ate?: string; brandId?: string; productId?: string
  defectTypeId?: string; solutionTypeId?: string; status?: TicketStatus
  atendenteId?: string; channelId?: string; page?: number; perPage?: number
}
export type Report = {
  kpis: { total: number; finalized: number; declined: number; avg_resolution_hours: number | null }
  products: RankingEntry[]; defects: RankingEntry[]; solutions: RankingEntry[]
  items: TicketListItem[]; total: number; page: number; per_page: number
}
export type MediaKindFilter = "imagem" | "pdf" | "video"
export type MediaItem = {
  id: string; ticket_id: string; ticket_number: number; filename: string
  kind: MediaKindFilter; content_type: string; size_bytes: number
  created_at: string; preview_url: string | null
}
export type MediaParams = {
  kind?: MediaKindFilter; brandId?: string; productId?: string; defectTypeId?: string
  solutionTypeId?: string; status?: TicketStatus; de?: string; ate?: string
  page?: number; perPage?: number
}
export const getDashboard: (brandId?: string) => Promise<Dashboard>
export const getReport: (params: ReportParams) => Promise<Report>
export const listMedia: (params: MediaParams) => Promise<{ items: MediaItem[]; total: number; page: number; per_page: number }>
export const downloadReportCsv: (params: ReportParams) => Promise<void>
```

- [ ] **Step 1: Instalar Recharts**

Run (em `frontend/`): `pnpm add recharts`
Expected: dependencia adicionada sem erro.

- [ ] **Step 2: Criar lib/reporting.ts**

Fetchers com o mesmo helper de query string de `lib/tickets.ts` (copiar a funcao `query` local — e um helper de 8 linhas; nao exportar de `tickets.ts` para nao criar acoplamento). Params mapeiam camelCase -> snake_case/nomes da API (`de`, `ate`, `brand_id`, `product_id`, `defect_type_id`, `solution_type_id`, `status`, `atendente_id`, `channel_id`, `kind`, `page`, `per_page`).

`downloadReportCsv`: `fetch` direto (a resposta nao e JSON):

```typescript
export async function downloadReportCsv(params: ReportParams): Promise<void> {
  const session = loadSession()
  const res = await fetch(`/api/relatorios/export${queryOf(params)}`, {
    headers: session ? { Authorization: `Bearer ${session.accessToken}` } : {},
  })
  if (!res.ok) throw new Error("falha ao exportar relatorio")
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "relatorio-tickets.csv"
  a.click()
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 3: Verify build**

Run (em `frontend/`): `pnpm build && pnpm lint`
Expected: sem erros.

- [ ] **Step 4: Commit**

```bash
git add package.json pnpm-lock.yaml src/lib/reporting.ts
git commit -m "Adiciona recharts e client de reporting no front"
```

---

### Task 9: Front — filtros da lista de tickets na URL

**Files:**
- Modify: `frontend/src/pages/tickets/TicketsListPage.tsx`

**Interfaces:**
- Consumes: `useSearchParams` (ja importado na pagina).
- Produces: a lista le TODOS os filtros da URL e os escreve nela — chaves: `status`, `brand_id`, `customer`, `product_id`, `order_code`, `priority`, `overdue` (`"1"`), `page`, `sort`, `order`. Task 10 navega para `/tickets?...` a partir dos KPI cards.

- [ ] **Step 1: Refatorar estado dos filtros para a URL**

Hoje a pagina tem `useState` por filtro e le da URL so `status`, `customer` e `overdue` na inicializacao (linhas 56-69). Trocar por derivacao direta de `searchParams` + um setter unico:

```tsx
const [searchParams, setSearchParams] = useSearchParams()
const status = (searchParams.get("status") as TicketStatus | null) ?? ""
const brandId = searchParams.get("brand_id") ?? ""
const customer = searchParams.get("customer") ?? ""
const productId = searchParams.get("product_id") ?? ""
const orderCode = searchParams.get("order_code") ?? ""
const priority = (searchParams.get("priority") as TicketPriority | null) ?? ""
const overdue = searchParams.get("overdue") === "1"
const page = Math.max(Number(searchParams.get("page") ?? "1"), 1)
const sort = (searchParams.get("sort") as SortField | null) ?? "last_activity_at"
const order = (searchParams.get("order") as "asc" | "desc" | null) ?? "desc"

function setParam(key: string, value: string) {
  const next = new URLSearchParams(searchParams)
  if (value) next.set(key, value)
  else next.delete(key)
  if (key !== "page") next.delete("page")
  setSearchParams(next, { replace: true })
}
```

Substituir cada `setStatus(x)` por `setParam("status", x)` e assim por diante; `setOverdue(v)` vira `setParam("overdue", v ? "1" : "")`; paginacao usa `setParam("page", String(n))`. Estados que sao so de UI (ex.: `productQuery` do autocomplete) continuam `useState`. O botao "Limpar" vira `setSearchParams(new URLSearchParams(), { replace: true })`.

- [ ] **Step 2: Verificar manualmente e por build**

Run: `pnpm build && pnpm lint`
Expected: sem erros. Sanidade manual (com `docker compose up -d` e `pnpm dev` + backend rodando): filtrar por status na tela e conferir que a URL reflete `?status=...` e que o refresh preserva o filtro.

- [ ] **Step 3: Rodar e2e existentes (a lista e coberta pelos specs 01-04)**

Run (backend rodando): `pnpm e2e --grep-invert anexos`
Expected: specs de lista/fluxo continuam verdes; se algum quebrar por causa da URL, ajustar a pagina (nao o teste) — o comportamento visivel deve permanecer o mesmo.

- [ ] **Step 4: Commit**

```bash
git add src/pages/tickets/TicketsListPage.tsx
git commit -m "Move filtros da lista de tickets para a URL"
```

---

### Task 10: Front — Dashboard

**Files:**
- Create: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/main.tsx` (rota `/dashboard`; `/` redireciona)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (item Dashboard no grupo Operacao)

**Interfaces:**
- Consumes: `getDashboard`, tipos da Task 8; `STATUS_LABELS`, badges de `@/components/tickets/badges`; componentes ui (`Card`, `Select`, `Table`); Recharts (`BarChart`, `Bar`, `XAxis`, `YAxis`, `ResponsiveContainer`, `Cell`); `useQuery` de `@tanstack/react-query`; `listCatalog`/client de marcas de `@/lib/cadastros` para o filtro de marca (conferir o nome exato do fetcher usado em `CatalogPage`).
- Produces: rota `/dashboard`; sidebar com "Dashboard" (icone `LayoutDashboard` de lucide) acima de "Tickets".

**IMPORTANTE:** antes de escrever qualquer JSX, invocar os skills `frontend-design` (obrigatorio no projeto para trabalho de UI, com `docs/identidade-visual.md`) e `dataviz` (para o grafico de barras e os rankings).

- [ ] **Step 1: Rota e redirect**

Em `main.tsx`: adicionar `{ path: "/dashboard", element: <DashboardPage /> }` dentro do grupo `RequireTenant`; trocar `{ path: "/", element: <p>Bem-vindo ao SAC-B2PRO</p> }` por um componente inline `HomeRedirect` que devolve `<Navigate to="/dashboard" replace />` quando `session?.tenantSlug` existe, senao mantem a mensagem (super admin sem tenant continua com a home atual). Importar `Navigate` de react-router-dom e `useAuth` de `@/lib/auth`.

- [ ] **Step 2: Sidebar**

No grupo "Operacao" da `Sidebar.tsx`: `{ to: "/dashboard", label: "Dashboard", icon: LayoutDashboard }` antes de Tickets.

- [ ] **Step 3: DashboardPage**

Estrutura (dados via `useQuery({ queryKey: ["dashboard", brandId], queryFn: () => getDashboard(brandId || undefined) })`):

- Header da pagina com titulo "Dashboard" e um `Select` de marca (opcao "Todas as marcas" + marcas ativas).
- Linha de 7 KPI cards (`grid` responsivo). Cada card e um `Link` para `/tickets?` + `new URLSearchParams({ ...kpi.filters, ...(brandId ? { brand_id: brandId } : {}) })`. Labels por chave: total "Total", abertos "Abertos", aguardando_analise "Aguardando analise", atrasados "Atrasados (SLA)", aprovados_no_mes "Aprovados no mes", declinados_no_mes "Declinados no mes", finalizados_no_mes "Finalizados no mes".
- Grid 2/3 + 1/3: a esquerda card "Distribuicao por status" com `BarChart` horizontal (Recharts, `layout="vertical"`, uma barra por status com as cores semanticas dos tokens — seguir o skill dataviz) e card "Tickets recentes" (tabela compacta: numero, cliente, status badge, atualizado em; linha e `Link` para o detalhe); a direita card-stat "Tempo medio de resolucao" (horas formatadas "1d 4h" ou travessao quando `null`) e tres cards de ranking (produto/defeito/solucao) como listas com barra de proporcao (div com width percentual, sem lib).
- Empty state padrao (borda tracejada) quando `total === 0`.
- Estados de loading com skeleton igual as outras paginas.

- [ ] **Step 4: Verify**

Run: `pnpm build && pnpm lint`
Expected: sem erros. Sanidade manual com backend rodando: abrir `/`, cair no `/dashboard`, clicar num KPI e conferir a lista pre-filtrada.

- [ ] **Step 5: Commit**

```bash
git add src/pages/dashboard/DashboardPage.tsx src/main.tsx src/components/layout/Sidebar.tsx
git commit -m "Adiciona dashboard com KPIs clicaveis, grafico de status e rankings"
```

---

### Task 11: Front — Relatorios

**Files:**
- Create: `frontend/src/pages/relatorios/RelatoriosPage.tsx`
- Modify: `frontend/src/main.tsx` (rota `/relatorios`)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (item Relatorios, icone `FileBarChart`)

**Interfaces:**
- Consumes: `getReport`, `downloadReportCsv`, tipos da Task 8; `AutocompleteField` de `@/components/tickets/AutocompleteField` (produto/defeito/solucao/canal — conferir a prop API no uso em `TicketCreatePage`); membros do tenant via `@/lib/members` para o select de atendente; `toast` de sonner.
- Produces: rota `/relatorios`.

**IMPORTANTE:** skill `frontend-design` ja invocado na Task 10 — manter a mesma direcao; se a sessao for nova, invocar de novo.

- [ ] **Step 1: Rota e sidebar** (mesmo padrao da Task 10; item "Relatorios" depois de Tickets)

- [ ] **Step 2: RelatoriosPage**

- Filtros na URL (mesmo padrao `setParam` da Task 9): `de`, `ate` (inputs `type="date"`; enviar como ISO — `de` vira `T00:00:00Z` e `ate` vira o dia seguinte `T00:00:00Z`, ja que a API filtra `opened_at < ate`), `brand_id`, `product_id`, `defect_type_id`, `solution_type_id`, `status`, `atendente_id`, `channel_id`, `page`.
- Chips de filtros ativos (badge com nome do filtro + botao de remover que chama `setParam(chave, "")`).
- 4 KPI cards: Total, Finalizados, Declinados, Tempo medio.
- Tres rankings (mesmo componente visual do dashboard — extrair `RankingList` para `frontend/src/components/reporting/RankingList.tsx` na task 10 ou aqui, o que vier primeiro, e reusar).
- Tabela paginada com o mesmo shape/colunas da lista de tickets; cada linha e `Link` real para `/tickets/{id}`.
- Botao "Exportar CSV" no header do card de resultados: chama `downloadReportCsv(params)` com os MESMOS params da tela; `catch` mostra `toast.error("Falha ao exportar o relatorio")`; estado de loading no botao enquanto baixa.

- [ ] **Step 3: Verify**

Run: `pnpm build && pnpm lint`
Expected: sem erros. Sanidade manual: filtrar, conferir KPIs e tabela coerentes, exportar CSV e abrir o arquivo.

- [ ] **Step 4: Commit**

```bash
git add src/pages/relatorios/RelatoriosPage.tsx src/components/reporting src/main.tsx src/components/layout/Sidebar.tsx
git commit -m "Adiciona tela de relatorios com filtros, rankings e export CSV"
```

---

### Task 12: Front — Galeria de midias com lightbox compartilhado

**Files:**
- Create: `frontend/src/components/media/MediaLightbox.tsx`
- Create: `frontend/src/pages/midias/MidiasPage.tsx`
- Modify: `frontend/src/components/tickets/AttachmentsCard.tsx` (usar o MediaLightbox extraido)
- Modify: `frontend/src/main.tsx` (rota `/midias`)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (item Midias, icone `Images`)

**Interfaces:**
- Consumes: `listMedia`, `MediaItem` da Task 8; `attachmentUrl` de `@/lib/attachments` (para abrir original/medio no lightbox); dialog ui existente.
- Produces:

```tsx
// MediaLightbox.tsx — extraido do visualizador atual do AttachmentsCard
export type LightboxItem = {
  kind: "imagem" | "pdf" | "video"
  filename: string
  url: string | null          // presigned do conteudo a exibir
  ticketId?: string
  ticketNumber?: number
}
export function MediaLightbox(props: {
  item: LightboxItem | null
  onClose: () => void
}): JSX.Element
```

- [ ] **Step 1: Extrair o lightbox**

Localizar no `AttachmentsCard.tsx` o dialog/overlay de visualizacao de anexo (imagem ampliada / player / link de PDF) e mover o markup para `MediaLightbox`, parametrizado por `LightboxItem`. Quando `ticketId` presente, o rodape mostra link "Ver ticket #N" (`Link to={/tickets/${ticketId}}`). `AttachmentsCard` passa a montar `LightboxItem` a partir do anexo selecionado (sem `ticketId` — ja esta no ticket). Comportamento visivel do detalhe do ticket NAO muda.

- [ ] **Step 2: MidiasPage**

- Filtros na URL (padrao `setParam`): `kind`, `brand_id`, `product_id`, `defect_type_id`, `solution_type_id`, `status`, `de`, `ate`.
- Grid responsivo de cards de thumb (aspecto quadrado, `object-cover`); placeholder por tipo quando `preview_url === null` (mesmos icones/estilo do card de anexos da 2B); legenda com `#numero` e data.
- Lazy loading: paginacao acumulativa com `IntersectionObserver` numa sentinela no fim do grid — `useInfiniteQuery` do react-query com `getNextPageParam: (last) => last.items.length === last.per_page ? last.page + 1 : undefined`.
- Clique abre `MediaLightbox`: para imagem, buscar a URL de exibicao via `attachmentUrl(ticket_id, id, "medio")` (fallback `original` — conferir a assinatura em `lib/attachments.ts`); PDF e video abrem pela variante `original`.
- Empty state padrao quando nao ha resultados.

- [ ] **Step 3: Rota e sidebar** ("Midias" depois de Relatorios)

- [ ] **Step 4: Verify**

Run: `pnpm build && pnpm lint`
Expected: sem erros. Rodar tambem os e2e de anexos (`pnpm e2e --grep anexos`) para garantir que a extracao do lightbox nao quebrou o detalhe do ticket.

- [ ] **Step 5: Commit**

```bash
git add src/components/media src/pages/midias src/components/tickets/AttachmentsCard.tsx src/main.tsx src/components/layout/Sidebar.tsx
git commit -m "Adiciona galeria de midias com lightbox compartilhado"
```

---

### Task 13: Passeio e2e da visibilidade e README

**Files:**
- Create: `frontend/e2e/06-visibilidade.spec.ts`
- Modify: `README.md` (secao "Fases entregues": adicionar Fase 3)

**Interfaces:**
- Consumes: helpers de `frontend/e2e/helpers.ts` (`login`, `apiFullTicket`, `apiUploadAttachment`, `USERS`); backend + MinIO rodando (`docker compose up -d`, `uvicorn` e worker como nos e2e existentes — ver `frontend/e2e/README.md`).

- [ ] **Step 1: Escrever o spec**

```typescript
import { expect, test } from "@playwright/test"

import { apiFullTicket, login } from "./helpers"

test.describe("Visibilidade: dashboard, relatorios e midias", () => {
  test("dashboard mostra KPIs e card clicavel pre-filtra a lista", async ({ page, request }) => {
    await apiFullTicket(request, "admin")
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Dashboard" }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByText("Total", { exact: true })).toBeVisible()
    await expect(page.getByText("Tempo medio de resolucao")).toBeVisible()

    await page.getByRole("link", { name: /Abertos/ }).click()
    await expect(page).toHaveURL(/\/tickets\?.*status=aberto/)
  })

  test("relatorio filtra, tem linhas com link e exporta CSV", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Relatorios" }).click()
    await expect(page).toHaveURL(/\/relatorios$/)
    await expect(page.getByRole("row").filter({ hasText: `#${ticket.number}` })).toBeVisible()

    const download = page.waitForEvent("download")
    await page.getByRole("button", { name: "Exportar CSV" }).click()
    expect((await download).suggestedFilename()).toBe("relatorio-tickets.csv")
  })

  test("galeria mostra anexo e lightbox leva ao ticket", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await apiUploadAttachment(request, "admin", ticket.id)
    await login(page, request, "admin")

    await page.getByRole("link", { name: "Midias" }).click()
    await expect(page).toHaveURL(/\/midias$/)

    // o card do anexo aparece (thumb pronta ou placeholder, conforme o worker)
    const card = page.getByText(`#${ticket.number}`).first()
    await expect(card).toBeVisible()

    await card.click()
    await page.getByRole("link", { name: `Ver ticket #${ticket.number}` }).click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })
})
```

Antes de rodar, conferir a assinatura real de `apiUploadAttachment` em `helpers.ts` (e como `05-anexos.spec.ts` o chama) e ajustar os argumentos; adicionar o import no topo do spec. O teste nao depende do preview pronto: com o worker parado o card mostra placeholder e o fluxo do lightbox continua validavel.

- [ ] **Step 2: Rodar o spec**

Run (com backend, worker e MinIO de pe): `pnpm e2e --grep Visibilidade`
Expected: PASS

- [ ] **Step 3: README**

Na secao "Fases entregues", adicionar:

```markdown
- **Fase 3 — Visibilidade**: dashboard com KPI cards clicaveis que pre-filtram a lista, grafico de distribuicao por status, rankings e tempo medio de resolucao (filtro por marca); relatorios com filtros completos, KPIs, rankings, tabela paginada com links e export CSV com exatamente os mesmos filtros da tela; galeria de midias do tenant com filtros, lazy loading e lightbox com link para o ticket. O importador das planilhas KODI/STALEKS foi retirado do escopo por decisao de produto (2026-07-30).
```

E na lista de documentacao, os dois arquivos novos de spec/plano da Fase 3.

- [ ] **Step 4: Commit**

```bash
git add e2e/06-visibilidade.spec.ts ../README.md
git commit -m "Adiciona passeio e2e da visibilidade e documenta a Fase 3"
```

---

### Task 14: Verificacao final da fase

- [ ] **Step 1: Backend completo**

Run (em `backend/`): `ruff check . && ruff format --check . && mypy . && pytest`
Expected: tudo verde.

- [ ] **Step 2: Frontend completo**

Run (em `frontend/`): `pnpm build && pnpm lint && pnpm e2e`
Expected: tudo verde (e2e com backend, worker e MinIO rodando).

- [ ] **Step 3: Passeio manual rapido**

Subir tudo (`docker compose up -d`, backend, worker, `pnpm dev`) e percorrer: login -> dashboard -> KPI card -> lista filtrada -> relatorios (filtro + export) -> midias (lightbox -> ticket). Conferir empty states com tenant limpo se possivel.

- [ ] **Step 4: Commit final (se houver ajustes) e encerrar**

Sem commit vazio; se os passos anteriores geraram correcoes, commitar com mensagem descritiva do ajuste.
