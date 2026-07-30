from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sac.application.ports_tickets import TicketListRow
from sac.domain.tickets import TicketStatus


@dataclass(frozen=True)
class RankingEntry:
    id: UUID
    name: str
    count: int


@dataclass(frozen=True)
class DashboardKpi:
    key: str  # total, abertos, aguardando_analise, atrasados,
    # aprovados_no_mes, declinados_no_mes, finalizados_no_mes
    count: int
    filters: dict[str, str]  # query params para o card clicavel na lista


@dataclass(frozen=True)
class DashboardData:
    kpis: list[DashboardKpi]
    status_counts: dict[TicketStatus, int]
    products: list[RankingEntry]
    defects: list[RankingEntry]
    solutions: list[RankingEntry]
    avg_resolution_hours: float | None
    recent: list[TicketListRow]


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
    products: str  # "Alicate x2; Esmalte x1"
    defects: str
    solution: str | None
    channel: str | None
    attendant: str | None
    order_code: str | None
    opened_at: datetime
    closed_at: datetime | None


class ReportingRepository(Protocol):
    async def dashboard(
        self, brand_id: UUID | None, unread_for: UUID, now: datetime
    ) -> DashboardData: ...
    async def report(
        self, filters: ReportFilters, page: int, per_page: int, unread_for: UUID
    ) -> ReportData: ...
    async def export_rows(
        self, filters: ReportFilters, page: int, per_page: int
    ) -> list[ReportExportRow]: ...
