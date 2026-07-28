from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_tickets import (
    TicketActor,
    TicketItemRepository,
    TicketRepository,
    TimelineRepository,
)
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    get_ticket_or_404,
    touch,
    transition_event,
)
from sac.domain.errors import ValidationError
from sac.domain.tickets import (
    Ticket,
    TicketStatus,
    ensure_transition,
    missing_for_analysis,
)


class _TransitionUseCase:
    def __init__(self, tickets: TicketRepository, timeline: TimelineRepository) -> None:
        self._tickets = tickets
        self._timeline = timeline

    async def _apply(
        self,
        actor: TicketActor,
        ticket: Ticket,
        target: TicketStatus,
        title: str,
        now: datetime,
    ) -> None:
        old = ticket.status
        ensure_transition(old, target)
        ticket.status = target
        await self._timeline.add(transition_event(ticket, old, title, actor))
        touch(ticket, now)
        await self._tickets.update(ticket)


class SubmitTicketUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        super().__init__(tickets, timeline)
        self._items = items

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_transition(ticket.status, TicketStatus.AGUARDANDO_ANALISE)
        missing = missing_for_analysis(ticket, await self._items.count(ticket.id))
        if missing:
            raise ValidationError("ticket incompleto para analise", details={"faltando": missing})
        now = datetime.now(UTC)
        ticket.submitted_at = now
        await self._apply(
            actor, ticket, TicketStatus.AGUARDANDO_ANALISE, "Ticket enviado para analise", now
        )
        return ticket


class ApproveTicketUseCase(_TransitionUseCase):
    async def execute(
        self, actor: TicketActor, ticket_id: UUID, notes: str | None = None
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.approved_at = now
        if notes and notes.strip():
            ticket.decision_notes = notes.strip()
        await self._apply(actor, ticket, TicketStatus.APROVADO, "Ticket aprovado", now)
        return ticket


class DeclineTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID, reason: str) -> Ticket:
        if not reason.strip():
            raise ValidationError("motivo do declinio e obrigatorio")
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.declined_at = now
        ticket.closed_at = now
        ticket.decision_notes = reason.strip()
        await self._apply(actor, ticket, TicketStatus.DECLINADO, "Ticket declinado", now)
        return ticket


class CancelTicketUseCase(_TransitionUseCase):
    async def execute(
        self, actor: TicketActor, ticket_id: UUID, reason: str | None = None
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.closed_at = now
        if reason and reason.strip():
            ticket.decision_notes = reason.strip()
        await self._apply(actor, ticket, TicketStatus.CANCELADO, "Ticket cancelado", now)
        return ticket


class HoldForCustomerUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(
            actor, ticket, TicketStatus.AGUARDANDO_CLIENTE, "Aguardando retorno do cliente", now
        )
        return ticket


class ResumeTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(actor, ticket, TicketStatus.ABERTO, "Atendimento retomado", now)
        return ticket


class ReopenTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        target = TicketStatus.APROVADO if ticket.approved_at else TicketStatus.ABERTO
        now = datetime.now(UTC)
        ticket.closed_at = None
        await self._apply(actor, ticket, target, "Ticket reaberto", now)
        return ticket
