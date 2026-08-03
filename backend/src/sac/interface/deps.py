from collections.abc import AsyncIterator, Callable, Coroutine
from functools import lru_cache
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sac.application.ports import TokenPayload
from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.application.use_cases.notifications_fanout import NotificationFanout
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
from sac.domain.catalog import CatalogKind
from sac.domain.errors import AuthError, PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
from sac.infrastructure.cep import ViaCepGateway
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserPreferencesRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.repositories_attachments import (
    AttachmentRepos,
    SqlTenantMemberDirectory,
    build_attachment_repos,
)
from sac.infrastructure.repositories_cadastros import (
    SqlCatalogRepository,
    SqlCustomerRepository,
    SqlProductRepository,
)
from sac.infrastructure.repositories_notifications import (
    PgNotifyPublisher,
    SqlNotificationRepository,
)
from sac.infrastructure.repositories_reporting import SqlReportingRepository
from sac.infrastructure.repositories_search import SqlGlobalSearchRepository
from sac.infrastructure.repositories_tickets import TicketRepos, build_ticket_repos
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage


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


async def get_tenant_session(
    request: Request,
    identity: TokenPayload = Depends(get_current_identity),
) -> AsyncIterator[AsyncSession]:
    if identity.tenant_slug is None:
        raise AuthError("token sem tenant")
    schema = f"t_{identity.tenant_slug}"
    engine = request.app.state.engine.execution_options(schema_translate_map={"tenant": schema})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_catalog_repository(
    kind: CatalogKind,
) -> Callable[..., SqlCatalogRepository]:
    def factory(session: AsyncSession = Depends(get_tenant_session)) -> SqlCatalogRepository:
        return SqlCatalogRepository(session, kind)

    return factory


def get_customer_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlCustomerRepository:
    return SqlCustomerRepository(session)


def get_product_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlProductRepository:
    return SqlProductRepository(session)


def get_ticket_repos(session: AsyncSession = Depends(get_tenant_session)) -> TicketRepos:
    return build_ticket_repos(session)


def get_reporting_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlReportingRepository:
    return SqlReportingRepository(session)


def get_global_search_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlGlobalSearchRepository:
    return SqlGlobalSearchRepository(session)


def get_storage(request: Request) -> S3Storage:
    storage: S3Storage = request.app.state.storage
    return storage


def get_attachment_repos(
    session: AsyncSession = Depends(get_tenant_session),
) -> AttachmentRepos:
    return build_attachment_repos(session)


def get_member_directory(
    session: AsyncSession = Depends(get_session),
) -> SqlTenantMemberDirectory:
    return SqlTenantMemberDirectory(session)


async def get_tenant_slug(identity: TokenPayload = Depends(get_current_identity)) -> str:
    if identity.tenant_slug is None:
        raise AuthError("token sem tenant")
    return identity.tenant_slug


def get_notification_fanout(
    session: AsyncSession = Depends(get_tenant_session),
    slug: str = Depends(get_tenant_slug),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> NotificationFanout:
    # repos vem de get_ticket_repos (cacheada por request pelo FastAPI) em
    # vez de build_ticket_repos(session) direto: rotas que ja pedem
    # get_ticket_repos (create_ticket, comentarios etc.) reusam a mesma
    # instancia, sem montar os outros sete repositorios de TicketRepos de novo
    # so para pegar .comments.
    return NotificationFanout(
        SqlNotificationRepository(session),
        repos.comments,
        PgNotifyPublisher(session),
        slug,
    )


def get_notification_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlNotificationRepository:
    return SqlNotificationRepository(session)


def get_cep_gateway() -> ViaCepGateway:
    return ViaCepGateway()


def get_user_preferences_repository(
    session: AsyncSession = Depends(get_session),
) -> SqlUserPreferencesRepository:
    # get_session (schema public), nao get_tenant_session: preferencia e
    # global do usuario, sem tenant ativo exigido no token (super_admin
    # tambem tem preferencias).
    return SqlUserPreferencesRepository(session)


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


def require_any_permission(*permissions: Permission) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
    ) -> TokenPayload:
        if identity.role is None or not any(has_permission(identity.role, p) for p in permissions):
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
