from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CustomerRepository
from sac.domain.cadastros import Customer
from sac.domain.documents import normalize_digits, validate_document, validate_state
from sac.domain.errors import ConflictError, NotFoundError, ValidationError

MAX_PER_PAGE = 100


def clamp_page(page: int, per_page: int) -> tuple[int, int]:
    return max(page, 1), min(max(per_page, 1), MAX_PER_PAGE)


@dataclass(frozen=True)
class CustomerInput:
    name: str
    document: str
    phone: str | None = None
    email: str | None = None
    cep: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class _NormalizedCustomer:
    name: str
    document: str
    phone: str | None
    email: str | None
    cep: str | None
    street: str | None
    number: str | None
    complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize(data: CustomerInput) -> _NormalizedCustomer:
    name = data.name.strip()
    if not name:
        raise ValidationError("nome obrigatório")
    document = validate_document(data.document)
    phone = normalize_digits(data.phone) or None if data.phone else None
    cep = None
    if _clean(data.cep):
        cep = normalize_digits(data.cep or "")
        if len(cep) != 8:
            raise ValidationError("CEP inválido: use 8 dígitos")
    cleaned_state = _clean(data.state)
    state = validate_state(cleaned_state) if cleaned_state else None
    return _NormalizedCustomer(
        name=name,
        document=document,
        phone=phone,
        email=_clean(data.email),
        cep=cep,
        street=_clean(data.street),
        number=_clean(data.number),
        complement=_clean(data.complement),
        neighborhood=_clean(data.neighborhood),
        city=_clean(data.city),
        state=state,
    )


class ListCustomersUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        search: str | None = None,
        active: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Customer], int]:
        page, per_page = clamp_page(page, per_page)
        return await self._repo.list(search, active, page, per_page)


class CreateCustomerUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, data: CustomerInput) -> Customer:
        normalized = _normalize(data)
        if await self._repo.get_by_document(normalized.document) is not None:
            raise ConflictError("documento já cadastrado")
        customer = Customer(
            id=uuid4(),
            name=normalized.name,
            document=normalized.document,
            phone=normalized.phone,
            email=normalized.email,
            cep=normalized.cep,
            street=normalized.street,
            number=normalized.number,
            complement=normalized.complement,
            neighborhood=normalized.neighborhood,
            city=normalized.city,
            state=normalized.state,
        )
        await self._repo.add(customer)
        return customer


class UpdateCustomerUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, customer_id: UUID, data: CustomerInput) -> Customer:
        customer = await self._repo.get(customer_id)
        if customer is None:
            raise NotFoundError("cliente não encontrado")
        normalized = _normalize(data)
        existing = await self._repo.get_by_document(normalized.document)
        if existing is not None and existing.id != customer_id:
            raise ConflictError("documento já cadastrado")
        customer.name = normalized.name
        customer.document = normalized.document
        customer.phone = normalized.phone
        customer.email = normalized.email
        customer.cep = normalized.cep
        customer.street = normalized.street
        customer.number = normalized.number
        customer.complement = normalized.complement
        customer.neighborhood = normalized.neighborhood
        customer.city = normalized.city
        customer.state = normalized.state
        await self._repo.update(customer)
        return customer


class SetCustomerActiveUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, customer_id: UUID, active: bool) -> Customer:
        customer = await self._repo.get(customer_id)
        if customer is None:
            raise NotFoundError("cliente não encontrado")
        customer.active = active
        await self._repo.update(customer)
        return customer
