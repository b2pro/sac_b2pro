from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_cadastros import CustomerRepository
from sac.application.ports_tickets import (
    ReverseCodeRepository,
    TicketActor,
    TicketCommentRepository,
    TicketDetail,
    TicketFilters,
    TicketItemRepository,
    TicketListRow,
    TicketReadRepository,
    TicketRepository,
    TimelineRepository,
    UserDirectoryPort,
)
from sac.application.use_cases.customers import clamp_page
from sac.application.use_cases.tickets_shared import get_ticket_or_404, restrict_to_own
from sac.domain.tickets import is_closed, sla_state

ALLOWED_SORTS = frozenset({"number", "opened_at", "due_at", "last_activity_at"})


class ListTicketsUseCase:
    def __init__(self, tickets: TicketRepository, users: UserDirectoryPort) -> None:
        self._tickets = tickets
        self._users = users

    async def execute(
        self,
        actor: TicketActor,
        filters: TicketFilters,
        page: int = 1,
        per_page: int = 20,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[list[TicketListRow], int]:
        page, per_page = clamp_page(page, per_page)
        owner = restrict_to_own(actor)
        if owner is not None:
            filters = replace(filters, attendant_user_id=owner)
        if sort not in ALLOWED_SORTS:
            sort = "last_activity_at"
        if order not in {"asc", "desc"}:
            order = "desc"
        rows, total = await self._tickets.list(
            filters, page, per_page, sort, order, unread_for=actor.user_id
        )
        names = await self._users.names_by_ids({row.ticket.attendant_user_id for row in rows})
        rows = [
            replace(row, attendant_name=names.get(row.ticket.attendant_user_id)) for row in rows
        ]
        return rows, total


class GetTicketDetailUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        comments: TicketCommentRepository,
        timeline: TimelineRepository,
        reverses: ReverseCodeRepository,
        reads: TicketReadRepository,
        customers: CustomerRepository,
        users: UserDirectoryPort,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._comments = comments
        self._timeline = timeline
        self._reverses = reverses
        self._reads = reads
        self._customers = customers
        self._users = users

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> TicketDetail:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        items = await self._items.list_by_ticket(ticket.id)
        comments = await self._comments.list_by_ticket(ticket.id)
        timeline = await self._timeline.list_by_ticket(ticket.id)
        reverses = await self._reverses.list_by_ticket(ticket.id)
        customer = (
            await self._customers.get(ticket.customer_id)
            if ticket.customer_id is not None
            else None
        )
        ids: set[UUID] = {ticket.attendant_user_id}
        if ticket.supervisor_user_id is not None:
            ids.add(ticket.supervisor_user_id)
        ids.update(c.author_user_id for c in comments)
        ids.update(e.author_user_id for e in timeline if e.author_user_id is not None)
        ids.update(r.author_user_id for r in reverses if r.author_user_id is not None)
        names = await self._users.names_by_ids(ids)
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return TicketDetail(
            ticket=ticket,
            sla=sla_state(now, ticket.due_at, is_closed(ticket)),
            customer=customer,
            items=items,
            comments=comments,
            timeline=timeline,
            reverses=reverses,
            user_names=names,
        )


class MarkTicketUnreadUseCase:
    def __init__(self, tickets: TicketRepository, reads: TicketReadRepository) -> None:
        self._tickets = tickets
        self._reads = reads

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        await self._reads.mark_unread(ticket.id, actor.user_id)
