from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
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

SEGREDO = "segredo-de-teste-com-32-bytes-ou-mais"
TOKENS = JwtTokenService(SEGREDO, "HS256", timedelta(minutes=15), timedelta(days=7))


def _refresh_sem_claim_de_versao(user_id: UUID) -> str:
    """Um refresh token no formato de antes do versionamento de credencial."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "sa": False,
            "tenant": "b2pro",
            "role": Role.ADMIN.value,
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        SEGREDO,
        algorithm="HS256",
    )


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
        "tenant_inexistente",
        "tenant_inativo",
        "comum_sem_slug",
    ],
)
async def test_falhas_de_login_sao_indistinguiveis(caso: str) -> None:
    c = Cenario()
    user = await c.com_usuario(active=caso != "usuario_inativo")
    tenant_status = TenantStatus.ATIVA
    if caso == "tenant_suspenso":
        tenant_status = TenantStatus.SUSPENSA
    elif caso == "tenant_inativo":
        tenant_status = TenantStatus.INATIVA
    tenant = await c.com_tenant(status=tenant_status)
    if caso not in ("sem_vinculo", "tenant_inexistente"):
        await c.com_vinculo(user, tenant, active=caso != "vinculo_inativo")

    email = "nao@existe.com" if caso == "usuario_inexistente" else "ana@b2.com"
    password = "errada" if caso == "senha_errada" else "senha123"
    slug = (
        None
        if caso == "comum_sem_slug"
        else ("nao-existe" if caso == "tenant_inexistente" else "b2pro")
    )

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


async def test_refresh_falha_se_tenant_suspenso_apos_login() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant)
    login = await c.login.execute("ana@b2.com", "senha123", "b2pro")

    tenant.status = TenantStatus.SUSPENSA
    await c.tenants.update(tenant)

    with pytest.raises(AuthError) as exc:
        await c.refresh.execute(login.refresh_token)
    assert str(exc.value) == "sessao invalida"


async def test_refresh_falha_depois_que_a_senha_e_trocada() -> None:
    """Resetar a senha e a resposta padrao a um token roubado. Sem versionamento
    de credencial o refresh so olha `user.active` e o vinculo, entao o refresh
    token roubado continuaria valendo por todo o TTL (7 dias) mesmo depois do
    reset - a acao de contencao nao conteria nada."""
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant)
    roubado = (await c.login.execute("ana@b2.com", "senha123", "b2pro")).refresh_token

    user.change_password("h:senha-nova")
    await c.users.update(user)

    with pytest.raises(AuthError) as exc:
        await c.refresh.execute(roubado)
    assert str(exc.value) == "sessao invalida"


async def test_login_depois_da_troca_de_senha_emite_sessao_valida() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant)
    user.change_password("h:senha-nova")
    await c.users.update(user)

    login = await c.login.execute("ana@b2.com", "senha-nova", "b2pro")

    result = await c.refresh.execute(login.refresh_token)
    assert result.role is Role.ADMIN


async def test_token_emitido_antes_do_versionamento_nao_serve_para_refresh() -> None:
    """Token antigo nao tem o claim `cv`. Ele nao pode ser aceito por omissao: a
    ausencia do claim vale zero, que nunca bate com a versao do banco (comeca em
    1). O efeito e um logout forcado no deploy, que e o comportamento correto."""
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant)
    antigo = _refresh_sem_claim_de_versao(user.id)

    with pytest.raises(AuthError):
        await c.refresh.execute(antigo)


async def test_refresh_falha_se_vinculo_desativado_apos_login() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant)
    login = await c.login.execute("ana@b2.com", "senha123", "b2pro")

    link = await c.links.get(user.id, tenant.id)
    assert link is not None
    await c.links.remove(user.id, tenant.id)
    link.active = False
    await c.links.add(link)

    with pytest.raises(AuthError) as exc:
        await c.refresh.execute(login.refresh_token)
    assert str(exc.value) == "sessao invalida"
