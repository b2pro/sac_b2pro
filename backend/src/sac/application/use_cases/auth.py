from dataclasses import dataclass

from sac.application.ports import (
    PasswordHasherPort,
    TenantRepository,
    TokenServicePort,
    UserRepository,
    UserTenantRepository,
)
from sac.domain.entities import TenantStatus, User
from sac.domain.errors import AuthError
from sac.domain.permissions import Role

_LOGIN_FAILED = "credenciais invalidas"
_SESSION_INVALID = "sessao invalida"
_LOGIN_TENANT_STATUSES = (TenantStatus.ATIVA, TenantStatus.TESTE)


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    refresh_token: str
    user: User
    tenant_slug: str | None
    role: Role | None


class LoginUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
        hasher: PasswordHasherPort,
        tokens: TokenServicePort,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links
        self._hasher = hasher
        self._tokens = tokens

    async def execute(self, email: str, password: str, tenant_slug: str | None) -> AuthResult:
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or not user.active or not self._hasher.verify(user.password_hash, password):
            raise AuthError(_LOGIN_FAILED)
        role: Role | None = None
        if tenant_slug:
            role = await _tenant_role(self._tenants, self._links, user, tenant_slug, _LOGIN_FAILED)
        elif not user.is_super_admin:
            raise AuthError(_LOGIN_FAILED)
        return _issue(self._tokens, user, tenant_slug or None, role)


class RefreshTokenUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
        tokens: TokenServicePort,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links
        self._tokens = tokens

    async def execute(self, refresh_token: str) -> AuthResult:
        payload = self._tokens.decode(refresh_token, expected_type="refresh")
        user = await self._users.get_by_id(payload.user_id)
        if user is None or not user.active:
            raise AuthError(_SESSION_INVALID)
        # Unico ponto onde uma sessao pode ser revogada: o refresh. O access token
        # nao consulta o banco (seria uma query por request) e vale ate expirar --
        # 15 minutos por default. Trocar a senha corta a renovacao aqui, entao o
        # alcance de um refresh token roubado cai de 7 dias para esses minutos.
        if payload.credentials_version != user.credentials_version:
            raise AuthError(_SESSION_INVALID)
        role: Role | None = None
        if payload.tenant_slug:
            role = await _tenant_role(
                self._tenants, self._links, user, payload.tenant_slug, _SESSION_INVALID
            )
        elif not user.is_super_admin:
            raise AuthError(_SESSION_INVALID)
        return _issue(self._tokens, user, payload.tenant_slug, role)


async def _tenant_role(
    tenants: TenantRepository,
    links: UserTenantRepository,
    user: User,
    slug: str,
    error_message: str,
) -> Role:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None or tenant.status not in _LOGIN_TENANT_STATUSES:
        raise AuthError(error_message)
    link = await links.get(user.id, tenant.id)
    if link is None or not link.active:
        raise AuthError(error_message)
    return link.role


def _issue(
    tokens: TokenServicePort, user: User, tenant_slug: str | None, role: Role | None
) -> AuthResult:
    access = tokens.create_access(
        user.id, tenant_slug, role, user.is_super_admin, user.credentials_version
    )
    refresh = tokens.create_refresh(
        user.id, tenant_slug, role, user.is_super_admin, user.credentials_version
    )
    return AuthResult(
        access_token=access,
        refresh_token=refresh,
        user=user,
        tenant_slug=tenant_slug,
        role=role,
    )
