from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.errors import ConflictError
from sac.domain.permissions import Role
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)


def _user(email: str = "a@b.com") -> User:
    return User(id=uuid4(), name="Ana", email=email, password_hash="h")


def _tenant(slug: str = "b2pro") -> Tenant:
    return Tenant(id=uuid4(), slug=slug, name="B2PRO", modules={"tickets": True})


async def test_user_roundtrip(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    user = _user()
    await repo.add(user)
    await session.commit()

    found = await repo.get_by_email("a@b.com")
    assert found is not None
    assert found.id == user.id
    assert await repo.get_by_id(user.id) is not None
    assert [u.email for u in await repo.list_all()] == ["a@b.com"]


async def test_email_duplicado_gera_conflito(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    await repo.add(_user())
    with pytest.raises(ConflictError):
        await repo.add(_user())


async def test_update_de_usuario(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    user = _user()
    await repo.add(user)
    await session.commit()

    user.active = False
    user.name = "Ana Maria"
    await repo.update(user)
    await session.commit()

    found = await repo.get_by_id(user.id)
    assert found is not None and found.active is False and found.name == "Ana Maria"


async def test_tenant_roundtrip_preserva_status_e_modulos(session: AsyncSession) -> None:
    repo = SqlTenantRepository(session)
    tenant = _tenant()
    tenant.status = TenantStatus.TESTE
    await repo.add(tenant)
    await session.commit()

    found = await repo.get_by_slug("b2pro")
    assert found is not None
    assert found.status is TenantStatus.TESTE
    assert found.modules == {"tickets": True}
    with pytest.raises(ConflictError):
        await repo.add(_tenant())


async def test_vinculo_roundtrip(session: AsyncSession) -> None:
    users = SqlUserRepository(session)
    tenants = SqlTenantRepository(session)
    links = SqlUserTenantRepository(session)
    user, tenant = _user(), _tenant()
    await users.add(user)
    await tenants.add(tenant)
    link = UserTenant(user_id=user.id, tenant_id=tenant.id, role=Role.SUPERVISOR)
    await links.add(link)
    await session.commit()

    found = await links.get(user.id, tenant.id)
    assert found is not None and found.role is Role.SUPERVISOR
    assert len(await links.list_for_tenant(tenant.id)) == 1

    await links.remove(user.id, tenant.id)
    await session.commit()
    assert await links.get(user.id, tenant.id) is None
