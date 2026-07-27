from datetime import timedelta
from uuid import uuid4

import pytest

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.security import JwtTokenService
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)

TOKENS = JwtTokenService("segredo-teste", "HS256", timedelta(minutes=15), timedelta(days=7))


class Cenario:
    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.tenants = InMemoryTenantRepository()
        self.links = InMemoryUserTenantRepository()
        self.hasher = FakeHasher()
        self.login = LoginUseCase(self.users, self.tenants, self.links, self.hasher, TOKENS)
        self.refresh = RefreshTokenUseCase(self.users, self.tenants, self.links, TOKENS)

    async def com_usuario(
        self, *, email: str = "ana@b2.com", active: bool = True, super_admin: bool = False
    ) -> User:
        user = User(
            id=uuid4(),
            name="Ana",
            email=email,
            password_hash="h:senha123",
            is_super_admin=super_admin,
            active=active,
        )
        await self.users.add(user)
        return user

    async def com_tenant(
        self, *, slug: str = "b2pro", status: TenantStatus = TenantStatus.ATIVA
    ) -> Tenant:
        tenant = Tenant(id=uuid4(), slug=slug, name="B2PRO", status=status)
        await self.tenants.add(tenant)
        return tenant

    async def com_vinculo(
        self, user: User, tenant: Tenant, *, role: Role = Role.ADMIN, active: bool = True
    ) -> None:
        await self.links.add(
            UserTenant(user_id=user.id, tenant_id=tenant.id, role=role, active=active)
        )


async def test_login_com_tenant_retorna_tokens_e_papel() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant, role=Role.SUPERVISOR)

    result = await c.login.execute("  ANA@B2.com ", "senha123", "b2pro")

    assert result.role is Role.SUPERVISOR
    assert result.tenant_slug == "b2pro"
    payload = TOKENS.decode(result.access_token, expected_type="access")
    assert payload.user_id == user.id and payload.role is Role.SUPERVISOR
    TOKENS.decode(result.refresh_token, expected_type="refresh")


async def test_login_super_admin_sem_slug() -> None:
    c = Cenario()
    await c.com_usuario(super_admin=True)
    result = await c.login.execute("ana@b2.com", "senha123", None)
    assert result.tenant_slug is None and result.role is None
    assert TOKENS.decode(result.access_token, expected_type="access").is_super_admin


@pytest.mark.parametrize(
    "caso",
    [
        "senha_errada",
        "usuario_inexistente",
        "usuario_inativo",
        "sem_vinculo",
        "vinculo_inativo",
        "tenant_suspenso",
        "comum_sem_slug",
    ],
)
async def test_falhas_de_login_sao_indistinguiveis(caso: str) -> None:
    c = Cenario()
    user = await c.com_usuario(active=caso != "usuario_inativo")
    tenant = await c.com_tenant(
        status=TenantStatus.SUSPENSA if caso == "tenant_suspenso" else TenantStatus.ATIVA
    )
    if caso not in ("sem_vinculo",):
        await c.com_vinculo(user, tenant, active=caso != "vinculo_inativo")

    email = "nao@existe.com" if caso == "usuario_inexistente" else "ana@b2.com"
    password = "errada" if caso == "senha_errada" else "senha123"
    slug = None if caso == "comum_sem_slug" else "b2pro"

    with pytest.raises(AuthError) as exc:
        await c.login.execute(email, password, slug)
    assert str(exc.value) == "credenciais invalidas"


async def test_tenant_em_teste_permite_login() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant(status=TenantStatus.TESTE)
    await c.com_vinculo(user, tenant)
    result = await c.login.execute("ana@b2.com", "senha123", "b2pro")
    assert result.tenant_slug == "b2pro"


async def test_refresh_reemite_par_de_tokens() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant, role=Role.ATENDENTE)
    login = await c.login.execute("ana@b2.com", "senha123", "b2pro")

    result = await c.refresh.execute(login.refresh_token)
    assert result.role is Role.ATENDENTE
    TOKENS.decode(result.access_token, expected_type="access")


async def test_refresh_rejeita_access_token() -> None:
    c = Cenario()
    await c.com_usuario(super_admin=True)
    login = await c.login.execute("ana@b2.com", "senha123", None)
    with pytest.raises(AuthError):
        await c.refresh.execute(login.access_token)


async def test_refresh_falha_se_usuario_desativado() -> None:
    c = Cenario()
    user = await c.com_usuario(super_admin=True)
    login = await c.login.execute("ana@b2.com", "senha123", None)
    user.active = False
    await c.users.update(user)
    with pytest.raises(AuthError):
        await c.refresh.execute(login.refresh_token)
