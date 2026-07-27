from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.permissions import Role
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings

HASHER = Argon2PasswordHasher()
DEFAULT_PASSWORD = "senha-forte-123"
_PASSWORD_HASH = HASHER.hash(DEFAULT_PASSWORD)


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    name: str = "Usuario Teste",
    is_super_admin: bool = False,
    active: bool = True,
) -> User:
    user = User(
        id=uuid4(),
        name=name,
        email=email,
        password_hash=_PASSWORD_HASH,
        is_super_admin=is_super_admin,
        active=active,
    )
    await SqlUserRepository(session).add(user)
    await session.commit()
    return user


async def seed_tenant(
    session: AsyncSession,
    *,
    slug: str,
    status: TenantStatus = TenantStatus.ATIVA,
    modules: dict[str, bool] | None = None,
) -> Tenant:
    tenant = Tenant(id=uuid4(), slug=slug, name=slug.upper(), status=status, modules=modules or {})
    await SqlTenantRepository(session).add(tenant)
    await session.commit()
    return tenant


async def seed_link(
    session: AsyncSession,
    *,
    user: User,
    tenant: Tenant,
    role: Role = Role.ADMIN,
    active: bool = True,
) -> UserTenant:
    link = UserTenant(user_id=user.id, tenant_id=tenant.id, role=role, active=active)
    await SqlUserTenantRepository(session).add(link)
    await session.commit()
    return link


def token_for(
    user: User, *, tenant_slug: str | None = None, role: Role | None = None
) -> dict[str, str]:
    tokens = JwtTokenService.from_settings(Settings())
    access = tokens.create_access(user.id, tenant_slug, role, user.is_super_admin)
    return {"Authorization": f"Bearer {access}"}
