from uuid import UUID

from pydantic import BaseModel, EmailStr

from sac.application.use_cases.auth import AuthResult


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
