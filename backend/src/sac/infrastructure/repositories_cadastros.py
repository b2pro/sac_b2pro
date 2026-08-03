from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem, CatalogKind
from sac.domain.documents import normalize_digits
from sac.domain.errors import ConflictError, NotFoundError
from sac.infrastructure.models_tenant import (
    BrandModel,
    CatalogModelBase,
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    PurchaseChannelModel,
    SolutionTypeModel,
)
from sac.infrastructure.sql_search import LIKE_ESCAPE_CHAR, escape_like

CATALOG_MODELS: dict[CatalogKind, type[CatalogModelBase]] = {
    CatalogKind.BRAND: BrandModel,
    CatalogKind.DEFECT_TYPE: DefectTypeModel,
    CatalogKind.SOLUTION_TYPE: SolutionTypeModel,
    CatalogKind.PURCHASE_CHANNEL: PurchaseChannelModel,
}


def _catalog_entity(m: CatalogModelBase) -> CatalogItem:
    return CatalogItem(
        id=m.id, name=m.name, description=m.description, active=m.active, deleted_at=m.deleted_at
    )


class SqlCatalogRepository:
    def __init__(self, session: AsyncSession, kind: CatalogKind) -> None:
        self._session = session
        self._model = CATALOG_MODELS[kind]

    async def list(self, search: str | None, active: bool | None) -> list[CatalogItem]:
        stmt = (
            select(self._model).where(self._model.deleted_at.is_(None)).order_by(self._model.name)
        )
        if search:
            stmt = stmt.where(
                self._model.name.ilike(f"%{escape_like(search)}%", escape=LIKE_ESCAPE_CHAR)
            )
        if active is not None:
            stmt = stmt.where(self._model.active == active)
        return [_catalog_entity(m) for m in await self._session.scalars(stmt)]

    async def get(self, item_id: UUID) -> CatalogItem | None:
        m = await self._session.get(self._model, item_id)
        return _catalog_entity(m) if m and m.deleted_at is None else None

    async def get_by_name(self, name: str) -> CatalogItem | None:
        m = await self._session.scalar(
            select(self._model).where(self._model.name == name, self._model.deleted_at.is_(None))
        )
        return _catalog_entity(m) if m else None

    async def add(self, item: CatalogItem) -> None:
        self._session.add(
            self._model(
                id=item.id,
                name=item.name,
                description=item.description,
                active=item.active,
                deleted_at=item.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "nome ja cadastrado")

    async def update(self, item: CatalogItem) -> None:
        m = await self._session.get(self._model, item.id)
        if m is None:
            raise NotFoundError("registro nao encontrado")
        m.name = item.name
        m.description = item.description
        m.active = item.active
        m.deleted_at = item.deleted_at
        await _flush_or_conflict(self._session, "nome ja cadastrado")


async def _flush_or_conflict(session: AsyncSession, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(message) from exc


def _customer_entity(m: CustomerModel) -> Customer:
    return Customer(
        id=m.id,
        name=m.name,
        document=m.document,
        phone=m.phone,
        email=m.email,
        cep=m.cep,
        street=m.street,
        number=m.number,
        complement=m.complement,
        neighborhood=m.neighborhood,
        city=m.city,
        state=m.state,
        active=m.active,
        deleted_at=m.deleted_at,
    )


class SqlCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_stmt(self, search: str | None, active: bool | None) -> Select[tuple[CustomerModel]]:
        stmt = select(CustomerModel).where(CustomerModel.deleted_at.is_(None))
        if search:
            digits = normalize_digits(search)
            escaped_search = escape_like(search)
            if digits:
                stmt = stmt.where(
                    or_(
                        CustomerModel.name.ilike(f"%{escaped_search}%", escape=LIKE_ESCAPE_CHAR),
                        CustomerModel.document.like(
                            f"%{escape_like(digits)}%", escape=LIKE_ESCAPE_CHAR
                        ),
                    )
                )
            else:
                stmt = stmt.where(
                    CustomerModel.name.ilike(f"%{escaped_search}%", escape=LIKE_ESCAPE_CHAR)
                )
        if active is not None:
            stmt = stmt.where(CustomerModel.active == active)
        return stmt

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Customer], int]:
        stmt = self._base_stmt(search, active)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(CustomerModel.name).offset((page - 1) * per_page).limit(per_page)
        )
        return [_customer_entity(m) for m in rows], int(total or 0)

    async def get(self, customer_id: UUID) -> Customer | None:
        m = await self._session.get(CustomerModel, customer_id)
        return _customer_entity(m) if m and m.deleted_at is None else None

    async def get_by_document(self, document: str) -> Customer | None:
        m = await self._session.scalar(
            select(CustomerModel).where(
                CustomerModel.document == document, CustomerModel.deleted_at.is_(None)
            )
        )
        return _customer_entity(m) if m else None

    async def add(self, customer: Customer) -> None:
        self._session.add(
            CustomerModel(
                id=customer.id,
                name=customer.name,
                document=customer.document,
                phone=customer.phone,
                email=customer.email,
                cep=customer.cep,
                street=customer.street,
                number=customer.number,
                complement=customer.complement,
                neighborhood=customer.neighborhood,
                city=customer.city,
                state=customer.state,
                active=customer.active,
                deleted_at=customer.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "documento ja cadastrado")

    async def update(self, customer: Customer) -> None:
        m = await self._session.get(CustomerModel, customer.id)
        if m is None:
            raise NotFoundError("cliente nao encontrado")
        m.name = customer.name
        m.document = customer.document
        m.phone = customer.phone
        m.email = customer.email
        m.cep = customer.cep
        m.street = customer.street
        m.number = customer.number
        m.complement = customer.complement
        m.neighborhood = customer.neighborhood
        m.city = customer.city
        m.state = customer.state
        m.active = customer.active
        m.deleted_at = customer.deleted_at
        await _flush_or_conflict(self._session, "documento ja cadastrado")


def _product_entity(m: ProductModel) -> Product:
    return Product(
        id=m.id,
        name=m.name,
        sku=m.sku,
        segment=m.segment,
        description=m.description,
        photo_key=m.photo_key,
        photo_preview_key=m.photo_preview_key,
        active=m.active,
        deleted_at=m.deleted_at,
    )


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_stmt(self, search: str | None, active: bool | None) -> Select[tuple[ProductModel]]:
        stmt = select(ProductModel).where(ProductModel.deleted_at.is_(None))
        if search:
            escaped_search = escape_like(search)
            stmt = stmt.where(
                or_(
                    ProductModel.name.ilike(f"%{escaped_search}%", escape=LIKE_ESCAPE_CHAR),
                    ProductModel.sku.ilike(f"%{escaped_search}%", escape=LIKE_ESCAPE_CHAR),
                )
            )
        if active is not None:
            stmt = stmt.where(ProductModel.active == active)
        return stmt

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Product], int]:
        stmt = self._base_stmt(search, active)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(ProductModel.name).offset((page - 1) * per_page).limit(per_page)
        )
        return [_product_entity(m) for m in rows], int(total or 0)

    async def get(self, product_id: UUID) -> Product | None:
        m = await self._session.get(ProductModel, product_id)
        return _product_entity(m) if m and m.deleted_at is None else None

    async def get_by_sku(self, sku: str) -> Product | None:
        m = await self._session.scalar(
            select(ProductModel).where(ProductModel.sku == sku, ProductModel.deleted_at.is_(None))
        )
        return _product_entity(m) if m else None

    async def add(self, product: Product) -> None:
        self._session.add(
            ProductModel(
                id=product.id,
                name=product.name,
                sku=product.sku,
                segment=product.segment,
                description=product.description,
                photo_key=product.photo_key,
                photo_preview_key=product.photo_preview_key,
                active=product.active,
                deleted_at=product.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "SKU ja cadastrado")

    async def update(self, product: Product) -> None:
        m = await self._session.get(ProductModel, product.id)
        if m is None:
            raise NotFoundError("produto nao encontrado")
        m.name = product.name
        m.sku = product.sku
        m.segment = product.segment
        m.description = product.description
        m.photo_key = product.photo_key
        m.photo_preview_key = product.photo_preview_key
        m.active = product.active
        m.deleted_at = product.deleted_at
        await _flush_or_conflict(self._session, "SKU ja cadastrado")
