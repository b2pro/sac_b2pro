from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from sac.application.use_cases.auth import AuthResult
from sac.domain.entities import Tenant, TenantStatus


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
