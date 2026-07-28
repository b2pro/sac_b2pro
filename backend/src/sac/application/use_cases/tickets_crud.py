from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CustomerRepository
from sac.application.ports_tickets import (
    SlaPolicyRepository,
    TicketActor,
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
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    get_ticket_or_404,
    touch,
)
from sac.domain.documents import validate_document
from sac.domain.errors import ValidationError
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    SlaPolicy,
    Ticket,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
    compute_due_at,
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


class CreateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
        reads: TicketReadRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline
        self._reads = reads

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
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return ticket


class UpdateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline

    async def execute(self, actor: TicketActor, ticket_id: UUID, data: UpdateTicketInput) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        if data.customer_id is not None and await self._customers.get(data.customer_id) is None:
            raise ValidationError("cliente nao encontrado", details={"field": "customer_id"})
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
        touch(ticket, now)
        await self._tickets.update(ticket)
        return ticket
