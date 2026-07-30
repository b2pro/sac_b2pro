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


class ReportingRepository(Protocol):
    async def dashboard(
        self, brand_id: UUID | None, unread_for: UUID, now: datetime
    ) -> DashboardData: ...
