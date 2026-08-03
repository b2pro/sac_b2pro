from datetime import UTC, datetime
from uuid import UUID, uuid4

from sac.application.ports_tickets import (
    ReverseCodeRepository,
    TicketActor,
    TicketItemRepository,
    TicketRepository,
    TimelineRepository,
)
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    ensure_can_operate,
    get_ticket_or_404,
    touch,
    transition_event,
)
from sac.domain.errors import (
    ConflictError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
)
from sac.domain.notifications import NotificationType
from sac.domain.tickets import (
    ReverseCode,
    Ticket,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
    ensure_transition,
    is_closed,
    missing_for_analysis,
)


class _TransitionUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        timeline: TimelineRepository,
        fanout: NotificationFanout,
    ) -> None:
        self._tickets = tickets
        self._timeline = timeline
        self._fanout = fanout

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
        await self._fanout.notify(actor, ticket, NotificationType.TRANSICAO, title)


class SubmitTicketUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
        fanout: NotificationFanout,
    ) -> None:
        super().__init__(tickets, timeline, fanout)
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
        if not is_closed(ticket):
            raise InvalidTransitionError(
                "apenas tickets encerrados podem ser reabertos",
                details={"status": ticket.status},
            )
        target = TicketStatus.APROVADO if ticket.approved_at else TicketStatus.ABERTO
        now = datetime.now(UTC)
        ticket.closed_at = None
        await self._apply(actor, ticket, target, "Ticket reaberto", now)
        return ticket


REVERSE_ALLOWED_STATUSES = frozenset({TicketStatus.APROVADO, TicketStatus.AGUARDANDO_ENVIO_REVERSO})
REVERSE_DELETE_ALLOWED_STATUSES = frozenset(
    {TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.PRODUTO_RECEBIDO}
)


class RegisterReverseUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        reverses: ReverseCodeRepository,
        timeline: TimelineRepository,
        fanout: NotificationFanout,
    ) -> None:
        super().__init__(tickets, timeline, fanout)
        self._reverses = reverses

    async def execute(self, actor: TicketActor, ticket_id: UUID, code: str) -> ReverseCode:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        cleaned = code.strip()
        if not cleaned:
            raise ValidationError("codigo reverso e obrigatorio")
        if ticket.status not in REVERSE_ALLOWED_STATUSES:
            raise InvalidTransitionError(
                "codigo reverso nao permitido neste estado",
                details={"status": ticket.status},
            )
        now = datetime.now(UTC)
        if ticket.status is TicketStatus.APROVADO:
            await self._apply(
                actor,
                ticket,
                TicketStatus.AGUARDANDO_ENVIO_REVERSO,
                "Aguardando envio reverso",
                now,
            )
        reverse = ReverseCode(
            id=uuid4(), ticket_id=ticket.id, code=cleaned, author_user_id=actor.user_id
        )
        await self._reverses.add(reverse)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.REVERSO_REGISTRADO,
                title="Codigo reverso registrado",
                new_value=cleaned,
                author_user_id=actor.user_id,
            )
        )
        touch(ticket, now)
        await self._tickets.update(ticket)
        return reverse


class DeleteReverseUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        reverses: ReverseCodeRepository,
        timeline: TimelineRepository,
        fanout: NotificationFanout,
    ) -> None:
        super().__init__(tickets, timeline, fanout)
        self._reverses = reverses

    async def execute(self, actor: TicketActor, ticket_id: UUID, reverse_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        if ticket.status not in REVERSE_DELETE_ALLOWED_STATUSES:
            raise InvalidTransitionError(
                "exclusao de reverso nao permitida neste estado",
                details={"status": ticket.status},
            )
        reverse = await self._reverses.get(reverse_id)
        if reverse is None or reverse.ticket_id != ticket.id:
            raise NotFoundError("codigo reverso nao encontrado")
        await self._reverses.remove(reverse.id)
        now = datetime.now(UTC)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.REVERSO_EXCLUIDO,
                title="Codigo reverso excluido",
                old_value=reverse.code,
                author_user_id=actor.user_id,
            )
        )
        if (
            ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
            and await self._reverses.count(ticket.id) == 0
        ):
            await self._apply(
                actor, ticket, TicketStatus.APROVADO, "Reversos removidos, ticket aprovado", now
            )
        else:
            touch(ticket, now)
            await self._tickets.update(ticket)


class ReceiveProductUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(actor, ticket, TicketStatus.PRODUTO_RECEBIDO, "Produto recebido", now)
        return ticket


class FinalizeTicketUseCase(_TransitionUseCase):
    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        solution_type_id: UUID,
        notes: str | None = None,
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        now = datetime.now(UTC)
        ticket.solution_type_id = solution_type_id
        if notes and notes.strip():
            ticket.final_notes = notes.strip()
        ticket.closed_at = now
        await self._apply(actor, ticket, TicketStatus.FINALIZADO, "Ticket finalizado", now)
        return ticket


class SetWarrantyUseCase(_TransitionUseCase):
    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        order_code: str,
        tracking_code: str | None = None,
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita garantia")
        cleaned = order_code.strip()
        if not cleaned:
            raise ValidationError("codigo do pedido de garantia e obrigatorio")
        ticket.warranty_order_code = cleaned
        ticket.warranty_tracking_code = (
            tracking_code.strip() if tracking_code and tracking_code.strip() else None
        )
        now = datetime.now(UTC)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.GARANTIA_REGISTRADA,
                title="Pedido de garantia registrado",
                new_value=cleaned,
                author_user_id=actor.user_id,
            )
        )
        touch(ticket, now)
        await self._tickets.update(ticket)
        return ticket
