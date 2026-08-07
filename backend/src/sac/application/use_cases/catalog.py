from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CatalogRepository
from sac.domain.catalog import CatalogItem
from sac.domain.errors import ConflictError, NotFoundError, ValidationError


@dataclass(frozen=True)
class CatalogItemInput:
    name: str
    description: str | None = None


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValidationError("nome obrigatório")
    return name


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    description = value.strip()
    return description or None


class ListCatalogUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(
        self, search: str | None = None, active: bool | None = None
    ) -> list[CatalogItem]:
        return await self._repo.list(search, active)


class CreateCatalogItemUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, data: CatalogItemInput) -> CatalogItem:
        name = _clean_name(data.name)
        if await self._repo.get_by_name(name) is not None:
            raise ConflictError("nome já cadastrado")
        item = CatalogItem(id=uuid4(), name=name, description=_clean_description(data.description))
        await self._repo.add(item)
        return item


class UpdateCatalogItemUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, item_id: UUID, data: CatalogItemInput) -> CatalogItem:
        item = await self._repo.get(item_id)
        if item is None:
            raise NotFoundError("registro não encontrado")
        name = _clean_name(data.name)
        existing = await self._repo.get_by_name(name)
        if existing is not None and existing.id != item_id:
            raise ConflictError("nome já cadastrado")
        item.name = name
        item.description = _clean_description(data.description)
        await self._repo.update(item)
        return item


class SetCatalogItemActiveUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, item_id: UUID, active: bool) -> CatalogItem:
        item = await self._repo.get(item_id)
        if item is None:
            raise NotFoundError("registro não encontrado")
        item.active = active
        await self._repo.update(item)
        return item
