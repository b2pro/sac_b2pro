from collections.abc import AsyncIterator, Callable, Coroutine
from functools import lru_cache
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports import TokenPayload
from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.application.use_cases.platform_tenants import (
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.application.use_cases.platform_users import (
    CreateUserUseCase,
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
    UnlinkUserFromTenantUseCase,
)
from sac.domain.errors import AuthError, PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def get_token_service(settings: Settings = Depends(get_settings)) -> JwtTokenService:
    return JwtTokenService.from_settings(settings)


def get_login_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
    tokens: JwtTokenService = Depends(get_token_service),
) -> LoginUseCase:
    return LoginUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        hasher,
        tokens,
    )


def get_refresh_use_case(
    session: AsyncSession = Depends(get_session),
    tokens: JwtTokenService = Depends(get_token_service),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        tokens,
    )


def get_tenant_provisioner(request: Request) -> AlembicTenantProvisioner:
    return AlembicTenantProvisioner(request.app.state.engine)


def get_create_tenant_use_case(
    session: AsyncSession = Depends(get_session),
    provisioner: AlembicTenantProvisioner = Depends(get_tenant_provisioner),
) -> CreateTenantUseCase:
    return CreateTenantUseCase(SqlTenantRepository(session), provisioner)


def get_list_tenants_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListTenantsUseCase:
    return ListTenantsUseCase(SqlTenantRepository(session))


def get_set_tenant_status_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetTenantStatusUseCase:
    return SetTenantStatusUseCase(SqlTenantRepository(session))


def get_set_tenant_modules_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetTenantModulesUseCase:
    return SetTenantModulesUseCase(SqlTenantRepository(session))


def get_create_user_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
) -> CreateUserUseCase:
    return CreateUserUseCase(SqlUserRepository(session), hasher)


def get_list_users_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListUsersUseCase:
    return ListUsersUseCase(SqlUserRepository(session))


def get_set_user_active_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetUserActiveUseCase:
    return SetUserActiveUseCase(SqlUserRepository(session))


def get_reset_password_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
) -> ResetPasswordUseCase:
    return ResetPasswordUseCase(SqlUserRepository(session), hasher)


def get_link_use_case(
    session: AsyncSession = Depends(get_session),
) -> LinkUserToTenantUseCase:
    return LinkUserToTenantUseCase(
        SqlUserRepository(session), SqlTenantRepository(session), SqlUserTenantRepository(session)
    )


def get_unlink_use_case(
    session: AsyncSession = Depends(get_session),
) -> UnlinkUserFromTenantUseCase:
    return UnlinkUserFromTenantUseCase(SqlUserTenantRepository(session))


def get_list_links_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListTenantLinksUseCase:
    return ListTenantLinksUseCase(SqlUserTenantRepository(session))


_bearer = HTTPBearer(auto_error=False)

IdentityDependency = Callable[..., Coroutine[Any, Any, TokenPayload]]


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    tokens: JwtTokenService = Depends(get_token_service),
) -> TokenPayload:
    if credentials is None:
        raise AuthError("credenciais ausentes")
    return tokens.decode(credentials.credentials, expected_type="access")


async def require_super_admin(
    identity: TokenPayload = Depends(get_current_identity),
) -> TokenPayload:
    if not identity.is_super_admin:
        raise PermissionDeniedError("acesso restrito ao painel da plataforma")
    return identity


def require_permission(permission: Permission) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
    ) -> TokenPayload:
        if identity.role is None or not has_permission(identity.role, permission):
            raise PermissionDeniedError("permissao insuficiente")
        return identity

    return dependency


def require_module(module: str) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
        session: AsyncSession = Depends(get_session),
    ) -> TokenPayload:
        if identity.tenant_slug is None:
            raise PermissionDeniedError("modulo indisponivel fora de um tenant")
        tenant = await SqlTenantRepository(session).get_by_slug(identity.tenant_slug)
        if tenant is None or not tenant.modules.get(module, False):
            raise PermissionDeniedError(f"modulo nao habilitado: {module}")
        return identity

    return dependency
