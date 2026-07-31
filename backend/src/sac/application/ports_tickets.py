from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sac.domain.cadastros import Customer
from sac.domain.permissions import Role
from sac.domain.tickets import (
    ReverseCode,
    SlaPolicy,
    SlaState,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
)


@dataclass(frozen=True)
class TicketActor:
    user_id: UUID
    role: Role


@dataclass(frozen=True)
class TicketFilters:
    status: TicketStatus | None = None
    brand_id: UUID | None = None
    customer_id: UUID | None = None
    customer: str | None = None
    product_id: UUID | None = None
    order_code: str | None = None
    priority: TicketPriority | None = None
    overdue: bool = False
    attendant_user_id: UUID | None = None
    search: str | None = None
    unread: bool = False


@dataclass(frozen=True)
class TicketCounters:
    todos: int
    ativos: int
    abertos: int
    aguardando_analise: int
    atrasados: int
    nao_lidos: int
    meus: int


@dataclass(frozen=True)
class TicketListRow:
    ticket: Ticket
    customer_name: str | None
    first_product_name: str | None
    items_count: int
    unread: bool
    attendant_name: str | None = None


@dataclass(frozen=True)
class TicketItemView:
    item: TicketItem
    product_name: str
    defect_type_name: str


@dataclass(frozen=True)
class TicketDetail:
    ticket: Ticket
    sla: SlaState
    customer: Customer | None
    items: list[TicketItemView]
    comments: list[TicketComment]
    timeline: list[TicketTimelineEvent]
    reverses: list[ReverseCode]
    user_names: dict[UUID, str]


class TicketRepository(Protocol):
    async def add(self, ticket: Ticket) -> Ticket: ...
    async def get(self, ticket_id: UUID) -> Ticket | None: ...
    async def update(self, ticket: Ticket) -> None: ...
    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]: ...
    async def counters(
        self, base: TicketFilters, unread_for: UUID, now: datetime
    ) -> TicketCounters: ...


class TicketItemRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]: ...
    async def count(self, ticket_id: UUID) -> int: ...
    async def get(self, item_id: UUID) -> TicketItem | None: ...
    async def add(self, item: TicketItem) -> None: ...
    async def update(self, item: TicketItem) -> None: ...
    async def remove(self, item_id: UUID) -> None: ...


class TicketCommentRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]: ...
    async def get(self, comment_id: UUID) -> TicketComment | None: ...
    async def add(self, comment: TicketComment) -> None: ...


class TimelineRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]: ...
    async def add(self, event: TicketTimelineEvent) -> None: ...


class ReverseCodeRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]: ...
    async def count(self, ticket_id: UUID) -> int: ...
    async def get(self, reverse_id: UUID) -> ReverseCode | None: ...
    async def add(self, reverse: ReverseCode) -> None: ...
    async def remove(self, reverse_id: UUID) -> None: ...


class TicketReadRepository(Protocol):
    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None: ...
    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None: ...
    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None: ...


class SlaPolicyRepository(Protocol):
    async def get(self, priority: TicketPriority) -> SlaPolicy | None: ...


class UserDirectoryPort(Protocol):
    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]: ...
