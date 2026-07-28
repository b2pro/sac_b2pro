from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import ProductRepository
from sac.application.use_cases.customers import clamp_page
from sac.domain.cadastros import Product
from sac.domain.errors import ConflictError, NotFoundError, ValidationError


@dataclass(frozen=True)
class ProductInput:
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize(data: ProductInput) -> tuple[str, str, str | None, str | None]:
    name = data.name.strip()
    if not name:
        raise ValidationError("nome obrigatorio")
    sku = data.sku.strip()
    if not sku:
        raise ValidationError("SKU obrigatorio")
    return name, sku, _clean(data.segment), _clean(data.description)


class ListProductsUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        search: str | None = None,
        active: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Product], int]:
        page, per_page = clamp_page(page, per_page)
        return await self._repo.list(search, active, page, per_page)


class CreateProductUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, data: ProductInput) -> Product:
        name, sku, segment, description = _normalize(data)
        if await self._repo.get_by_sku(sku) is not None:
            raise ConflictError("SKU ja cadastrado")
        product = Product(id=uuid4(), name=name, sku=sku, segment=segment, description=description)
        await self._repo.add(product)
        return product


class UpdateProductUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, product_id: UUID, data: ProductInput) -> Product:
        product = await self._repo.get(product_id)
        if product is None:
            raise NotFoundError("produto nao encontrado")
        name, sku, segment, description = _normalize(data)
        existing = await self._repo.get_by_sku(sku)
        if existing is not None and existing.id != product_id:
            raise ConflictError("SKU ja cadastrado")
        product.name = name
        product.sku = sku
        product.segment = segment
        product.description = description
        await self._repo.update(product)
        return product


class SetProductActiveUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, product_id: UUID, active: bool) -> Product:
        product = await self._repo.get(product_id)
        if product is None:
            raise NotFoundError("produto nao encontrado")
        product.active = active
        await self._repo.update(product)
        return product
