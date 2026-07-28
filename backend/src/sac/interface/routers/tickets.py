from uuid import UUID

from fastapi import APIRouter, Depends, Response

from sac.application.ports import TokenPayload
from sac.application.ports_tickets import TicketActor, TicketFilters
from sac.application.use_cases.customers import CustomerInput
from sac.application.use_cases.tickets_crud import (
    AddTicketItemUseCase,
    CreateTicketInput,
    CreateTicketUseCase,
    RemoveTicketItemUseCase,
    TicketItemInput,
    UpdateTicketInput,
    UpdateTicketItemUseCase,
    UpdateTicketUseCase,
)
from sac.application.use_cases.tickets_queries import GetTicketDetailUseCase, ListTicketsUseCase
from sac.domain.permissions import Permission
from sac.domain.tickets import TicketPriority, TicketStatus
from sac.infrastructure.repositories_tickets import TicketRepos
from sac.interface.deps import (
    get_ticket_repos,
    require_any_permission,
    require_permission,
)
from sac.interface.schemas import (
    TicketDetailOut,
    TicketIn,
    TicketItemIn,
    TicketItemOut,
    TicketOut,
    TicketsPageOut,
    TicketUpdateIn,
    ticket_detail_out,
    ticket_item_out,
    ticket_list_item_out,
    ticket_out,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

_create = require_permission(Permission.CRIAR_TICKET)
_read = require_any_permission(Permission.VER_TODOS_TICKETS, Permission.VER_PROPRIOS_TICKETS)
_edit = require_any_permission(Permission.EDITAR_QUALQUER_TICKET, Permission.EDITAR_PROPRIO_TICKET)


def _actor(identity: TokenPayload) -> TicketActor:
    assert identity.role is not None  # garantido pelas dependencies de permissao
    return TicketActor(user_id=identity.user_id, role=identity.role)


def _item_input(body: TicketItemIn) -> TicketItemInput:
    return TicketItemInput(
        product_id=body.product_id,
        defect_type_id=body.defect_type_id,
        quantity=body.quantity,
    )


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketIn,
    identity: TokenPayload = Depends(_create),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    customer_input = (
        CustomerInput(
            name=body.customer.name,
            document=body.customer.document,
            phone=body.customer.phone,
            email=body.customer.email,
            cep=body.customer.cep,
            street=body.customer.street,
            number=body.customer.number,
            complement=body.customer.complement,
            neighborhood=body.customer.neighborhood,
            city=body.customer.city,
            state=body.customer.state,
        )
        if body.customer is not None
        else None
    )
    data = CreateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer=customer_input,
        customer_id=body.customer_id,
        attendant_user_id=body.attendant_user_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
        items=tuple(_item_input(i) for i in body.items),
    )
    use_case = CreateTicketUseCase(
        repos.tickets, repos.items, repos.customers, repos.sla, repos.timeline, repos.reads
    )
    return ticket_out(await use_case.execute(_actor(identity), data))


@router.get("", response_model=TicketsPageOut)
async def list_tickets(
    status: TicketStatus | None = None,
    brand_id: UUID | None = None,
    customer: str | None = None,
    customer_id: UUID | None = None,
    product_id: UUID | None = None,
    order_code: str | None = None,
    priority: TicketPriority | None = None,
    overdue: bool = False,
    page: int = 1,
    per_page: int = 20,
    sort: str = "last_activity_at",
    order: str = "desc",
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketsPageOut:
    filters = TicketFilters(
        status=status,
        brand_id=brand_id,
        customer=customer,
        customer_id=customer_id,
        product_id=product_id,
        order_code=order_code,
        priority=priority,
        overdue=overdue,
    )
    rows, total = await ListTicketsUseCase(repos.tickets, repos.users).execute(
        _actor(identity), filters, page, per_page, sort, order
    )
    return TicketsPageOut(
        items=[ticket_list_item_out(r) for r in rows],
        total=total,
        page=max(page, 1),
        per_page=min(max(per_page, 1), 100),
    )


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket_detail(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketDetailOut:
    use_case = GetTicketDetailUseCase(
        repos.tickets,
        repos.items,
        repos.comments,
        repos.timeline,
        repos.reverses,
        repos.reads,
        repos.customers,
        repos.users,
    )
    return ticket_detail_out(await use_case.execute(_actor(identity), ticket_id))


@router.put("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    body: TicketUpdateIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    data = UpdateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer_id=body.customer_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
    )
    use_case = UpdateTicketUseCase(repos.tickets, repos.customers, repos.sla, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, data))


@router.post("/{ticket_id}/itens", response_model=TicketItemOut, status_code=201)
async def add_ticket_item(
    ticket_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await AddTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, _item_input(body)
    )
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.put("/{ticket_id}/itens/{item_id}", response_model=TicketItemOut)
async def update_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await UpdateTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, item_id, _item_input(body)
    )
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.delete("/{ticket_id}/itens/{item_id}", status_code=204)
async def remove_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    await RemoveTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, item_id
    )
    return Response(status_code=204)
