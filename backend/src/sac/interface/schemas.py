from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from sac.application.ports_cadastros import CepAddress
from sac.application.use_cases.auth import AuthResult
from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem
from sac.domain.entities import Tenant, TenantStatus
from sac.domain.permissions import Role


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    is_super_admin: bool
    active: bool


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant_slug: str | None
    role: str | None


def login_out(result: AuthResult) -> LoginOut:
    return LoginOut(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=UserOut(
            id=result.user.id,
            name=result.user.name,
            email=result.user.email,
            is_super_admin=result.user.is_super_admin,
            active=result.user.active,
        ),
        tenant_slug=result.tenant_slug,
        role=result.role.value if result.role else None,
    )


class TenantCreateIn(BaseModel):
    slug: str
    name: str
    modules: dict[str, bool] = Field(default_factory=dict)


class TenantStatusIn(BaseModel):
    status: TenantStatus


class TenantModulesIn(BaseModel):
    modules: dict[str, bool]


class TenantOut(BaseModel):
    id: UUID
    slug: str
    name: str
    status: TenantStatus
    modules: dict[str, bool]


def tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        modules=tenant.modules,
    )


class UserCreateIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    is_super_admin: bool = False


class UserActiveIn(BaseModel):
    active: bool


class PasswordResetIn(BaseModel):
    password: str


class LinkCreateIn(BaseModel):
    user_id: UUID
    role: Role


class LinkOut(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: Role
    active: bool


class CatalogItemIn(BaseModel):
    name: str
    description: str | None = None


class CatalogItemOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    active: bool


class ActiveIn(BaseModel):
    active: bool


def catalog_out(item: CatalogItem) -> CatalogItemOut:
    return CatalogItemOut(
        id=item.id, name=item.name, description=item.description, active=item.active
    )


class CustomerIn(BaseModel):
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


class CustomerOut(BaseModel):
    id: UUID
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
    active: bool


class CustomersPageOut(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    per_page: int


class ProductIn(BaseModel):
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None


class ProductOut(BaseModel):
    id: UUID
    name: str
    sku: str
    segment: str | None
    description: str | None
    photo_key: str | None
    active: bool


class ProductsPageOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    per_page: int


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut.model_validate(customer, from_attributes=True)


def product_out(product: Product) -> ProductOut:
    return ProductOut.model_validate(product, from_attributes=True)


class CepOut(BaseModel):
    cep: str
    street: str
    neighborhood: str
    city: str
    state: str


def cep_out(address: CepAddress) -> CepOut:
    return CepOut(
        cep=address.cep,
        street=address.street,
        neighborhood=address.neighborhood,
        city=address.city,
        state=address.state,
    )
