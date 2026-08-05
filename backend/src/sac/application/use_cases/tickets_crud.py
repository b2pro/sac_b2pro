from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CustomerRepository
from sac.application.ports_tickets import (
    SlaPolicyRepository,
    TicketActor,
    TicketCommentRepository,
    TicketItemRepository,
    TicketReadRepository,
    TicketRepository,
    TimelineRepository,
)
from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    UpdateCustomerUseCase,
)
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    get_ticket_or_404,
    touch,
)
from sac.domain.documents import validate_document
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.notifications import NotificationType
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    SlaPolicy,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
    compute_due_at,
    is_closed,
)


@dataclass(frozen=True)
class TicketItemInput:
    product_id: UUID
    defect_type_id: UUID
    quantity: int = 1


@dataclass(frozen=True)
class CreateTicketInput:
    brand_id: UUID
    priority: TicketPriority
    customer: CustomerInput | None = None
    customer_id: UUID | None = None
    attendant_user_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = None
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None
    items: tuple[TicketItemInput, ...] = ()


@dataclass(frozen=True)
class UpdateTicketInput:
    brand_id: UUID
    priority: TicketPriority
    # PUT e substituicao pura: obrigatorio, sem excecao de "omitido". Igual
    # ao atendente atual e no-op; diferente dispara a checagem de permissao
    # de reatribuicao (EDITAR_QUALQUER_TICKET).
    attendant_user_id: UUID
    customer_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = None
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None


def _validate_quantity(quantity: int) -> None:
    if quantity < 1:
        raise ValidationError("quantidade minima e 1", details={"field": "quantity"})


async def _resolve_customer_id(
    customers: CustomerRepository,
    inline: CustomerInput | None,
    customer_id: UUID | None,
) -> UUID | None:
    if inline is not None and customer_id is not None:
        raise ValidationError("informe cliente inline ou customer_id, nao ambos")
    if inline is not None:
        document = validate_document(inline.document)
        existing = await customers.get_by_document(document)
        if existing is not None:
            updated = await UpdateCustomerUseCase(customers).execute(existing.id, inline)
            return updated.id
        created = await CreateCustomerUseCase(customers).execute(inline)
        return created.id
    if customer_id is not None:
        if await customers.get(customer_id) is None:
            raise ValidationError("cliente nao encontrado", details={"field": "customer_id"})
        return customer_id
    return None


async def _resolve_sla(policies: SlaPolicyRepository, priority: TicketPriority) -> SlaPolicy:
    return await policies.get(priority) or DEFAULT_SLA_POLICIES[priority]


async def _record_item_event(
    tickets: TicketRepository,
    timeline: TimelineRepository,
    ticket: Ticket,
    actor: TicketActor,
    type_: TimelineEventType,
    title: str,
) -> None:
    await timeline.add(
        TicketTimelineEvent(
            id=uuid4(),
            ticket_id=ticket.id,
            type=type_,
            title=title,
            author_user_id=actor.user_id,
        )
    )
    touch(ticket, datetime.now(UTC))
    await tickets.update(ticket)


class CreateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
        reads: TicketReadRepository,
        fanout: NotificationFanout,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline
        self._reads = reads
        self._fanout = fanout

    async def execute(self, actor: TicketActor, data: CreateTicketInput) -> Ticket:
        for item in data.items:
            _validate_quantity(item.quantity)
        customer_id = await _resolve_customer_id(self._customers, data.customer, data.customer_id)
        attendant = actor.user_id
        if data.attendant_user_id is not None and has_permission(
            actor.role, Permission.VER_TODOS_TICKETS
        ):
            attendant = data.attendant_user_id
        now = datetime.now(UTC)
        policy = await _resolve_sla(self._sla, data.priority)
        ticket = Ticket(
            id=uuid4(),
            number=0,
            brand_id=data.brand_id,
            status=TicketStatus.ABERTO,
            priority=data.priority,
            attendant_user_id=attendant,
            opened_at=now,
            due_at=compute_due_at(now, policy),
            last_activity_at=now,
            customer_id=customer_id,
            supervisor_user_id=data.supervisor_user_id,
            purchase_channel_id=data.purchase_channel_id,
            order_code=data.order_code,
            purchase_date=data.purchase_date,
            delivery_date=data.delivery_date,
            description=data.description,
        )
        ticket = await self._tickets.add(ticket)
        for item in data.items:
            await self._items.add(
                TicketItem(
                    id=uuid4(),
                    ticket_id=ticket.id,
                    product_id=item.product_id,
                    defect_type_id=item.defect_type_id,
                    quantity=item.quantity,
                )
            )
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.CRIACAO,
                title="Ticket criado",
                new_value=str(ticket.number),
                author_user_id=actor.user_id,
            )
        )
        if ticket.attendant_user_id != actor.user_id:
            await self._timeline.add(
                TicketTimelineEvent(
                    id=uuid4(),
                    ticket_id=ticket.id,
                    type=TimelineEventType.ATRIBUICAO,
                    title="Ticket atribuido",
                    new_value=str(ticket.attendant_user_id),
                    author_user_id=actor.user_id,
                )
            )
            await self._fanout.notify(
                actor,
                ticket,
                NotificationType.ATRIBUICAO,
                f"Ticket #{ticket.number} atribuido a voce",
                only_recipient=ticket.attendant_user_id,
            )
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return ticket


class UpdateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
        fanout: NotificationFanout,
    ) -> None:
        self._tickets = tickets
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline
        self._fanout = fanout

    async def execute(self, actor: TicketActor, ticket_id: UUID, data: UpdateTicketInput) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        if data.customer_id is not None and await self._customers.get(data.customer_id) is None:
            raise ValidationError("cliente nao encontrado", details={"field": "customer_id"})
        old_attendant = ticket.attendant_user_id
        new_attendant = data.attendant_user_id
        reassigned = False
        if new_attendant != old_attendant:
            if not has_permission(actor.role, Permission.EDITAR_QUALQUER_TICKET):
                raise PermissionDeniedError("sem permissao para reatribuir o ticket")
            ticket.attendant_user_id = new_attendant
            reassigned = True
        old_priority = ticket.priority
        ticket.brand_id = data.brand_id
        ticket.priority = data.priority
        ticket.customer_id = data.customer_id
        ticket.supervisor_user_id = data.supervisor_user_id
        ticket.purchase_channel_id = data.purchase_channel_id
        ticket.order_code = data.order_code
        ticket.purchase_date = data.purchase_date
        ticket.delivery_date = data.delivery_date
        ticket.description = data.description
        now = datetime.now(UTC)
        if data.priority != old_priority:
            policy = await _resolve_sla(self._sla, data.priority)
            ticket.due_at = compute_due_at(ticket.opened_at, policy)
            event = TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.PRIORIDADE_ALTERADA,
                title="Prioridade alterada",
                old_value=str(old_priority),
                new_value=str(data.priority),
                author_user_id=actor.user_id,
            )
        else:
            event = TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.EDICAO,
                title="Dados do ticket editados",
                author_user_id=actor.user_id,
            )
        await self._timeline.add(event)
        if reassigned:
            await self._timeline.add(
                TicketTimelineEvent(
                    id=uuid4(),
                    ticket_id=ticket.id,
                    type=TimelineEventType.ATRIBUICAO,
                    title="Atendente alterado",
                    old_value=str(old_attendant),
                    new_value=str(ticket.attendant_user_id),
                    author_user_id=actor.user_id,
                )
            )
        touch(ticket, now)
        await self._tickets.update(ticket)
        if reassigned:
            await self._fanout.notify(
                actor,
                ticket,
                NotificationType.ATRIBUICAO,
                f"Ticket #{ticket.number} atribuido a voce",
                only_recipient=ticket.attendant_user_id,
            )
        return ticket


class AddTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, data: TicketItemInput
    ) -> TicketItem:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        _validate_quantity(data.quantity)
        item = TicketItem(
            id=uuid4(),
            ticket_id=ticket.id,
            product_id=data.product_id,
            defect_type_id=data.defect_type_id,
            quantity=data.quantity,
        )
        await self._items.add(item)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_ADICIONADO,
            "Item adicionado",
        )
        return item


class UpdateTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, item_id: UUID, data: TicketItemInput
    ) -> TicketItem:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        _validate_quantity(data.quantity)
        item = await self._items.get(item_id)
        if item is None or item.ticket_id != ticket.id:
            raise NotFoundError("item nao encontrado")
        item.product_id = data.product_id
        item.defect_type_id = data.defect_type_id
        item.quantity = data.quantity
        await self._items.update(item)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_ALTERADO,
            "Item alterado",
        )
        return item


class RemoveTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(self, actor: TicketActor, ticket_id: UUID, item_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        item = await self._items.get(item_id)
        if item is None or item.ticket_id != ticket.id:
            raise NotFoundError("item nao encontrado")
        await self._items.remove(item.id)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_REMOVIDO,
            "Item removido",
        )


class AddCommentUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        comments: TicketCommentRepository,
        reads: TicketReadRepository,
        fanout: NotificationFanout,
    ) -> None:
        self._tickets = tickets
        self._comments = comments
        self._reads = reads
        self._fanout = fanout

    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        body: str,
        reply_to_id: UUID | None = None,
    ) -> TicketComment:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita comentarios")
        text = body.strip()
        if not text:
            raise ValidationError("comentario vazio")
        if reply_to_id is not None:
            parent = await self._comments.get(reply_to_id)
            if parent is None or parent.ticket_id != ticket.id:
                raise ValidationError("comentario respondido nao pertence a este ticket")
        comment = TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=actor.user_id,
            body=text,
            reply_to_id=reply_to_id,
        )
        await self._comments.add(comment)
        now = datetime.now(UTC)
        touch(ticket, now)
        await self._tickets.update(ticket)
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        await self._fanout.notify(
            actor,
            ticket,
            NotificationType.COMENTARIO,
            f"Novo comentario no ticket #{ticket.number}",
            snippet=text[:200],
        )
        return comment
