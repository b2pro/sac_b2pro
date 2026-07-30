from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from sac.domain.attachments import AttachmentKind
from sac.domain.tickets import TicketStatus
from sac.interface.schemas import TicketListItemOut


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
