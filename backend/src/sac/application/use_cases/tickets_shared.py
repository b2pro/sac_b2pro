from datetime import datetime
from uuid import UUID, uuid4

from sac.application.ports_tickets import TicketActor, TicketRepository
from sac.domain.errors import ConflictError, NotFoundError, PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import (
    Ticket,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
)

EDITABLE_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.ABERTO, TicketStatus.AGUARDANDO_CLIENTE}
)


async def get_ticket_or_404(
    tickets: TicketRepository, actor: TicketActor, ticket_id: UUID
) -> Ticket:
    ticket = await tickets.get(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise NotFoundError("ticket nao encontrado")
    if has_permission(actor.role, Permission.VER_TODOS_TICKETS):
        return ticket
    if (
        has_permission(actor.role, Permission.VER_PROPRIOS_TICKETS)
        and ticket.attendant_user_id == actor.user_id
    ):
        return ticket
    raise NotFoundError("ticket nao encontrado")


def ensure_can_edit(actor: TicketActor, ticket: Ticket) -> None:
    if ticket.status not in EDITABLE_STATUSES:
        raise ConflictError(
            "ticket nao pode ser editado neste estado", details={"status": ticket.status}
        )
    if has_permission(actor.role, Permission.EDITAR_QUALQUER_TICKET):
        return
    if (
        has_permission(actor.role, Permission.EDITAR_PROPRIO_TICKET)
        and ticket.attendant_user_id == actor.user_id
    ):
        return
    raise PermissionDeniedError("sem permissao para editar este ticket")


def ensure_can_operate(actor: TicketActor, ticket: Ticket) -> None:
    if has_permission(actor.role, Permission.OPERAR_LOGISTICA_TODOS):
        return
    if (
        has_permission(actor.role, Permission.OPERAR_LOGISTICA_PROPRIOS)
        and ticket.attendant_user_id == actor.user_id
    ):
        return
    raise PermissionDeniedError("sem permissao para operar este ticket")


def touch(ticket: Ticket, now: datetime) -> None:
    ticket.last_activity_at = now


def transition_event(
    ticket: Ticket,
    old_status: TicketStatus,
    title: str,
    actor: TicketActor,
    event_type: TimelineEventType = TimelineEventType.TRANSICAO,
) -> TicketTimelineEvent:
    return TicketTimelineEvent(
        id=uuid4(),
        ticket_id=ticket.id,
        type=event_type,
        title=title,
        old_value=str(old_status),
        new_value=str(ticket.status),
        author_user_id=actor.user_id,
    )
