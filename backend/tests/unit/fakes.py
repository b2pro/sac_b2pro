from uuid import UUID

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem
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

    async def update(self, link: UserTenant) -> None:
        key = (link.user_id, link.tenant_id)
        if key not in self.items:
            raise NotFoundError("vinculo nao encontrado")
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


class InMemoryCatalogRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, CatalogItem] = {}

    async def list(self, search: str | None, active: bool | None) -> list[CatalogItem]:
        result = [i for i in self.items.values() if i.deleted_at is None]
        if search:
            result = [i for i in result if search.lower() in i.name.lower()]
        if active is not None:
            result = [i for i in result if i.active == active]
        return sorted(result, key=lambda i: i.name)

    async def get(self, item_id: UUID) -> CatalogItem | None:
        item = self.items.get(item_id)
        return item if item and item.deleted_at is None else None

    async def get_by_name(self, name: str) -> CatalogItem | None:
        return next(
            (i for i in self.items.values() if i.name == name and i.deleted_at is None), None
        )

    async def add(self, item: CatalogItem) -> None:
        if await self.get_by_name(item.name):
            raise ConflictError("nome ja cadastrado")
        self.items[item.id] = item

    async def update(self, item: CatalogItem) -> None:
        if item.id not in self.items:
            raise NotFoundError("registro nao encontrado")
        self.items[item.id] = item


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Customer] = {}

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Customer], int]:
        result = [c for c in self.items.values() if c.deleted_at is None]
        if search:
            lowered = search.lower()
            result = [c for c in result if lowered in c.name.lower() or lowered in c.document]
        if active is not None:
            result = [c for c in result if c.active == active]
        result.sort(key=lambda c: c.name)
        start = (page - 1) * per_page
        return result[start : start + per_page], len(result)

    async def get(self, customer_id: UUID) -> Customer | None:
        customer = self.items.get(customer_id)
        return customer if customer and customer.deleted_at is None else None

    async def get_by_document(self, document: str) -> Customer | None:
        return next(
            (c for c in self.items.values() if c.document == document and c.deleted_at is None),
            None,
        )

    async def add(self, customer: Customer) -> None:
        if await self.get_by_document(customer.document):
            raise ConflictError("documento ja cadastrado")
        self.items[customer.id] = customer

    async def update(self, customer: Customer) -> None:
        if customer.id not in self.items:
            raise NotFoundError("cliente nao encontrado")
        self.items[customer.id] = customer


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Product] = {}

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Product], int]:
        result = [p for p in self.items.values() if p.deleted_at is None]
        if search:
            lowered = search.lower()
            result = [p for p in result if lowered in p.name.lower() or lowered in p.sku.lower()]
        if active is not None:
            result = [p for p in result if p.active == active]
        result.sort(key=lambda p: p.name)
        start = (page - 1) * per_page
        return result[start : start + per_page], len(result)

    async def get(self, product_id: UUID) -> Product | None:
        product = self.items.get(product_id)
        return product if product and product.deleted_at is None else None

    async def get_by_sku(self, sku: str) -> Product | None:
        return next((p for p in self.items.values() if p.sku == sku and p.deleted_at is None), None)

    async def add(self, product: Product) -> None:
        if await self.get_by_sku(product.sku):
            raise ConflictError("SKU ja cadastrado")
        self.items[product.id] = product

    async def update(self, product: Product) -> None:
        if product.id not in self.items:
            raise NotFoundError("produto nao encontrado")
        self.items[product.id] = product
