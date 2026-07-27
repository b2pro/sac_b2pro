from uuid import UUID

from sac.domain.entities import Tenant, User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return next(
            (u for u in self.items.values() if u.email == email and u.deleted_at is None), None
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        user = self.items.get(user_id)
        return user if user and user.deleted_at is None else None

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email):
            raise ConflictError("email ja cadastrado")
        self.items[user.id] = user

    async def list_all(self) -> list[User]:
        return sorted(
            (u for u in self.items.values() if u.deleted_at is None), key=lambda u: u.name
        )

    async def update(self, user: User) -> None:
        if user.id not in self.items:
            raise NotFoundError("usuario nao encontrado")
        self.items[user.id] = user


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Tenant] = {}

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return next(
            (t for t in self.items.values() if t.slug == slug and t.deleted_at is None), None
        )

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        tenant = self.items.get(tenant_id)
        return tenant if tenant and tenant.deleted_at is None else None

    async def add(self, tenant: Tenant) -> None:
        if await self.get_by_slug(tenant.slug):
            raise ConflictError("slug ja cadastrado")
        self.items[tenant.id] = tenant

    async def list_all(self) -> list[Tenant]:
        return sorted(
            (t for t in self.items.values() if t.deleted_at is None), key=lambda t: t.slug
        )

    async def update(self, tenant: Tenant) -> None:
        if tenant.id not in self.items:
            raise NotFoundError("tenant nao encontrado")
        self.items[tenant.id] = tenant


class InMemoryUserTenantRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], UserTenant] = {}

    async def get(self, user_id: UUID, tenant_id: UUID) -> UserTenant | None:
        return self.items.get((user_id, tenant_id))

    async def add(self, link: UserTenant) -> None:
        key = (link.user_id, link.tenant_id)
        if key in self.items:
            raise ConflictError("vinculo ja existe")
        self.items[key] = link

    async def remove(self, user_id: UUID, tenant_id: UUID) -> None:
        if (user_id, tenant_id) not in self.items:
            raise NotFoundError("vinculo nao encontrado")
        del self.items[(user_id, tenant_id)]

    async def list_for_tenant(self, tenant_id: UUID) -> list[UserTenant]:
        return [link for link in self.items.values() if link.tenant_id == tenant_id]


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"h:{password}"
