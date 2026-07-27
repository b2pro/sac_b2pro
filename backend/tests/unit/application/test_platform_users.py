from uuid import uuid4

import pytest

from sac.application.use_cases.platform_users import (
    CreateUserInput,
    CreateUserUseCase,
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
    UnlinkUserFromTenantUseCase,
)
from sac.domain.entities import Tenant, User
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)


async def test_criar_usuario_normaliza_email_e_faz_hash() -> None:
    users = InMemoryUserRepository()
    use_case = CreateUserUseCase(users, FakeHasher())

    user = await use_case.execute(
        CreateUserInput(name="Ana", email="  ANA@B2.com ", password="senha-forte")
    )

    assert user.email == "ana@b2.com"
    assert user.password_hash == "h:senha-forte"
    assert not user.is_super_admin


async def test_senha_curta_e_rejeitada() -> None:
    use_case = CreateUserUseCase(InMemoryUserRepository(), FakeHasher())
    with pytest.raises(ValidationError):
        await use_case.execute(CreateUserInput(name="Ana", email="a@b.com", password="curta"))


async def test_email_duplicado_gera_conflito() -> None:
    users = InMemoryUserRepository()
    use_case = CreateUserUseCase(users, FakeHasher())
    await use_case.execute(CreateUserInput(name="Ana", email="a@b.com", password="senha-forte"))
    with pytest.raises(ConflictError):
        await use_case.execute(CreateUserInput(name="Bia", email="a@b.com", password="senha-forte"))


async def test_ativar_desativar_e_resetar_senha() -> None:
    users = InMemoryUserRepository()
    user = User(id=uuid4(), name="Ana", email="a@b.com", password_hash="h:antiga")
    await users.add(user)

    alterado = await SetUserActiveUseCase(users).execute(user.id, False)
    assert alterado.active is False

    await ResetPasswordUseCase(users, FakeHasher()).execute(user.id, "nova-senha-forte")
    atualizado = await users.get_by_id(user.id)
    assert atualizado is not None and atualizado.password_hash == "h:nova-senha-forte"

    assert len(await ListUsersUseCase(users).execute()) == 1

    with pytest.raises(NotFoundError):
        await SetUserActiveUseCase(users).execute(uuid4(), True)


async def test_vinculos() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    user = User(id=uuid4(), name="Ana", email="a@b.com", password_hash="h")
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    await users.add(user)
    await tenants.add(tenant)

    link_use_case = LinkUserToTenantUseCase(users, tenants, links)
    link = await link_use_case.execute(user.id, tenant.id, Role.SUPERVISOR)
    assert link.role is Role.SUPERVISOR

    with pytest.raises(ConflictError):
        await link_use_case.execute(user.id, tenant.id, Role.ADMIN)

    with pytest.raises(NotFoundError):
        await link_use_case.execute(uuid4(), tenant.id, Role.ADMIN)

    assert len(await ListTenantLinksUseCase(links).execute(tenant.id)) == 1

    await UnlinkUserFromTenantUseCase(links).execute(user.id, tenant.id)
    assert await links.get(user.id, tenant.id) is None
