from datetime import datetime
from uuid import UUID

from sac.application.ports_tickets import TicketFilters, TicketItemView, TicketListRow
from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    ReverseCode,
    SlaPolicy,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketTimelineEvent,
)


class InMemoryTicketRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Ticket] = {}
        self._seq = 0

    async def add(self, ticket: Ticket) -> Ticket:
        self._seq += 1
        ticket.number = self._seq
        self.items[ticket.id] = ticket
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        return self.items.get(ticket_id)

    async def update(self, ticket: Ticket) -> None:
        self.items[ticket.id] = ticket

    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]:
        rows = [
            TicketListRow(
                ticket=t,
                customer_name=None,
                first_product_name=None,
                items_count=0,
                unread=False,
            )
            for t in self.items.values()
            if filters.attendant_user_id is None or t.attendant_user_id == filters.attendant_user_id
        ]
        return rows, len(rows)


class InMemoryTicketItemRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, TicketItem] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]:
        return [
            TicketItemView(item=i, product_name="Produto", defect_type_name="Defeito")
            for i in self.items.values()
            if i.ticket_id == ticket_id
        ]

    async def count(self, ticket_id: UUID) -> int:
        return sum(1 for i in self.items.values() if i.ticket_id == ticket_id)

    async def get(self, item_id: UUID) -> TicketItem | None:
        return self.items.get(item_id)

    async def add(self, item: TicketItem) -> None:
        self.items[item.id] = item

    async def update(self, item: TicketItem) -> None:
        self.items[item.id] = item

    async def remove(self, item_id: UUID) -> None:
        self.items.pop(item_id, None)


class InMemoryTicketCommentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, TicketComment] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]:
        return [c for c in self.items.values() if c.ticket_id == ticket_id]

    async def get(self, comment_id: UUID) -> TicketComment | None:
        return self.items.get(comment_id)

    async def add(self, comment: TicketComment) -> None:
        self.items[comment.id] = comment


class InMemoryTimelineRepository:
    def __init__(self) -> None:
        self.events: list[TicketTimelineEvent] = []

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]:
        return [e for e in self.events if e.ticket_id == ticket_id]

    async def add(self, event: TicketTimelineEvent) -> None:
        self.events.append(event)


class InMemoryReverseCodeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ReverseCode] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]:
        return [r for r in self.items.values() if r.ticket_id == ticket_id]

    async def count(self, ticket_id: UUID) -> int:
        return sum(1 for r in self.items.values() if r.ticket_id == ticket_id)

    async def get(self, reverse_id: UUID) -> ReverseCode | None:
        return self.items.get(reverse_id)

    async def add(self, reverse: ReverseCode) -> None:
        self.items[reverse.id] = reverse

    async def remove(self, reverse_id: UUID) -> None:
        self.items.pop(reverse_id, None)


class InMemoryTicketReadRepository:
    def __init__(self) -> None:
        self.reads: dict[tuple[UUID, UUID], datetime] = {}

    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None:
        self.reads[(ticket_id, user_id)] = at

    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None:
        self.reads.pop((ticket_id, user_id), None)

    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None:
        return self.reads.get((ticket_id, user_id))


class InMemorySlaPolicyRepository:
    def __init__(self, overrides: dict[TicketPriority, SlaPolicy] | None = None) -> None:
        self.policies = dict(DEFAULT_SLA_POLICIES)
        if overrides:
            self.policies.update(overrides)

    async def get(self, priority: TicketPriority) -> SlaPolicy | None:
        return self.policies.get(priority)


class InMemoryUserDirectory:
    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]:
        return {i: n for i, n in self.names.items() if i in ids}
