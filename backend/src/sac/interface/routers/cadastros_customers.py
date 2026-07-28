from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    ListCustomersUseCase,
    SetCustomerActiveUseCase,
    UpdateCustomerUseCase,
    clamp_page,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlCustomerRepository
from sac.interface.deps import get_customer_repository, require_permission
from sac.interface.schemas import (
    ActiveIn,
    CustomerIn,
    CustomerOut,
    CustomersPageOut,
    customer_out,
)

router = APIRouter(prefix="/cadastros/clientes", tags=["cadastros"])


def _input(body: CustomerIn) -> CustomerInput:
    return CustomerInput(
        name=body.name,
        document=body.document,
        phone=body.phone,
        email=body.email,
        cep=body.cep,
        street=body.street,
        number=body.number,
        complement=body.complement,
        neighborhood=body.neighborhood,
        city=body.city,
        state=body.state,
    )


@router.get(
    "",
    response_model=CustomersPageOut,
    dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
)
async def list_customers(
    search: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 20,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomersPageOut:
    page, per_page = clamp_page(page, per_page)
    items, total = await ListCustomersUseCase(repo).execute(search, active, page, per_page)
    return CustomersPageOut(
        items=[customer_out(c) for c in items], total=total, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=CustomerOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
)
async def create_customer(
    body: CustomerIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await CreateCustomerUseCase(repo).execute(_input(body)))


@router.put(
    "/{customer_id}",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def update_customer(
    customer_id: UUID,
    body: CustomerIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await UpdateCustomerUseCase(repo).execute(customer_id, _input(body)))


@router.patch(
    "/{customer_id}/active",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def set_customer_active(
    customer_id: UUID,
    body: ActiveIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await SetCustomerActiveUseCase(repo).execute(customer_id, body.active))
