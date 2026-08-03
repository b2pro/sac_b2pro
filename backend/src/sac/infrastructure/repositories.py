from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserPreferences, UserTenant
from sac.domain.errors import ConflictError, NotFoundError
from sac.domain.permissions import Role
from sac.infrastructure.models import (
    TenantModel,
    UserModel,
    UserPreferencesModel,
    UserTenantModel,
)


def _user_entity(m: UserModel) -> User:
    return User(
        id=m.id,
        name=m.name,
        email=m.email,
        password_hash=m.password_hash,
        is_super_admin=m.is_super_admin,
        active=m.active,
        deleted_at=m.deleted_at,
    )


def _tenant_entity(m: TenantModel) -> Tenant:
    return Tenant(
        id=m.id,
        slug=m.slug,
        name=m.name,
        status=TenantStatus(m.status),
        modules=dict(m.modules),
        deleted_at=m.deleted_at,
    )


def _link_entity(m: UserTenantModel) -> UserTenant:
    return UserTenant(user_id=m.user_id, tenant_id=m.tenant_id, role=Role(m.role), active=m.active)


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        m = await self._session.scalar(
            select(UserModel).where(UserModel.email == email, UserModel.deleted_at.is_(None))
        )
        return _user_entity(m) if m else None

    async def get_by_id(self, user_id: UUID) -> User | None:
        m = await self._session.get(UserModel, user_id)
        return _user_entity(m) if m and m.deleted_at is None else None

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                name=user.name,
                email=user.email,
                password_hash=user.password_hash,
                is_super_admin=user.is_super_admin,
                active=user.active,
                deleted_at=user.deleted_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("email ja cadastrado") from exc

    async def list_all(self) -> list[User]:
        result = await self._session.scalars(
            select(UserModel).where(UserModel.deleted_at.is_(None)).order_by(UserModel.name)
        )
        return [_user_entity(m) for m in result]

    async def update(self, user: User) -> None:
        m = await self._session.get(UserModel, user.id)
        if m is None:
            raise NotFoundError("usuario nao encontrado")
        m.name = user.name
        m.email = user.email
        m.password_hash = user.password_hash
        m.is_super_admin = user.is_super_admin
        m.active = user.active
        m.deleted_at = user.deleted_at
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("email ja cadastrado") from exc


class SqlTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slug(self, slug: str) -> Tenant | None:
        m = await self._session.scalar(
            select(TenantModel).where(TenantModel.slug == slug, TenantModel.deleted_at.is_(None))
        )
        return _tenant_entity(m) if m else None

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        m = await self._session.get(TenantModel, tenant_id)
        return _tenant_entity(m) if m and m.deleted_at is None else None

    async def add(self, tenant: Tenant) -> None:
        self._session.add(
            TenantModel(
                id=tenant.id,
                slug=tenant.slug,
                name=tenant.name,
                status=tenant.status.value,
                modules=dict(tenant.modules),
                deleted_at=tenant.deleted_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("slug ja cadastrado") from exc

    async def list_all(self) -> list[Tenant]:
        result = await self._session.scalars(
            select(TenantModel).where(TenantModel.deleted_at.is_(None)).order_by(TenantModel.slug)
        )
        return [_tenant_entity(m) for m in result]

    async def update(self, tenant: Tenant) -> None:
        m = await self._session.get(TenantModel, tenant.id)
        if m is None:
            raise NotFoundError("tenant nao encontrado")
        m.name = tenant.name
        m.status = tenant.status.value
        m.modules = dict(tenant.modules)
        m.deleted_at = tenant.deleted_at
        await self._session.flush()


class SqlUserTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID, tenant_id: UUID) -> UserTenant | None:
        m = await self._session.get(UserTenantModel, (user_id, tenant_id))
        return _link_entity(m) if m else None

    async def add(self, link: UserTenant) -> None:
        self._session.add(
            UserTenantModel(
                user_id=link.user_id,
                tenant_id=link.tenant_id,
                role=link.role.value,
                active=link.active,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("vinculo ja existe") from exc

    async def update(self, link: UserTenant) -> None:
        m = await self._session.get(UserTenantModel, (link.user_id, link.tenant_id))
        if m is None:
            raise NotFoundError("vinculo nao encontrado")
        m.role = link.role.value
        m.active = link.active
        await self._session.flush()

    async def remove(self, user_id: UUID, tenant_id: UUID) -> None:
        m = await self._session.get(UserTenantModel, (user_id, tenant_id))
        if m is None:
            raise NotFoundError("vinculo nao encontrado")
        await self._session.delete(m)
        await self._session.flush()

    async def list_for_tenant(self, tenant_id: UUID) -> list[UserTenant]:
        result = await self._session.scalars(
            select(UserTenantModel).where(UserTenantModel.tenant_id == tenant_id)
        )
        return [_link_entity(m) for m in result]


def _preferences_entity(m: UserPreferencesModel) -> UserPreferences:
    return UserPreferences(
        user_id=m.user_id,
        theme=m.theme,
        notify_toast=m.notify_toast,
        notify_sound=m.notify_sound,
    )


class SqlUserPreferencesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> UserPreferences | None:
        m = await self._session.get(UserPreferencesModel, user_id)
        return _preferences_entity(m) if m else None

    async def upsert(self, prefs: UserPreferences) -> None:
        stmt = (
            pg_insert(UserPreferencesModel)
            .values(
                user_id=prefs.user_id,
                theme=prefs.theme,
                notify_toast=prefs.notify_toast,
                notify_sound=prefs.notify_sound,
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "theme": prefs.theme,
                    "notify_toast": prefs.notify_toast,
                    "notify_sound": prefs.notify_sound,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.execute(stmt)
