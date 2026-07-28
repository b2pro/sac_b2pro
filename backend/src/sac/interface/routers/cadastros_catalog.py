from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.catalog import (
    CatalogItemInput,
    CreateCatalogItemUseCase,
    ListCatalogUseCase,
    SetCatalogItemActiveUseCase,
    UpdateCatalogItemUseCase,
)
from sac.domain.catalog import CatalogKind
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository
from sac.interface.deps import get_catalog_repository, require_permission
from sac.interface.schemas import ActiveIn, CatalogItemIn, CatalogItemOut, catalog_out


def build_catalog_router(kind: CatalogKind, path: str) -> APIRouter:
    router = APIRouter(prefix=f"/cadastros/{path}", tags=["cadastros"])
    repo_dep = get_catalog_repository(kind)

    @router.get(
        "",
        response_model=list[CatalogItemOut],
        dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
    )
    async def list_items(
        search: str | None = None,
        active: bool | None = None,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> list[CatalogItemOut]:
        items = await ListCatalogUseCase(repo).execute(search, active)
        return [catalog_out(i) for i in items]

    @router.post(
        "",
        response_model=CatalogItemOut,
        status_code=201,
        dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
    )
    async def create_item(
        body: CatalogItemIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        item = await CreateCatalogItemUseCase(repo).execute(
            CatalogItemInput(name=body.name, description=body.description)
        )
        return catalog_out(item)

    @router.put(
        "/{item_id}",
        response_model=CatalogItemOut,
        dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
    )
    async def update_item(
        item_id: UUID,
        body: CatalogItemIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        item = await UpdateCatalogItemUseCase(repo).execute(
            item_id, CatalogItemInput(name=body.name, description=body.description)
        )
        return catalog_out(item)

    @router.patch(
        "/{item_id}/active",
        response_model=CatalogItemOut,
        dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
    )
    async def set_active(
        item_id: UUID,
        body: ActiveIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        return catalog_out(await SetCatalogItemActiveUseCase(repo).execute(item_id, body.active))

    return router


marcas_router = build_catalog_router(CatalogKind.BRAND, "marcas")
defeitos_router = build_catalog_router(CatalogKind.DEFECT_TYPE, "defeitos")
solucoes_router = build_catalog_router(CatalogKind.SOLUTION_TYPE, "solucoes")
canais_router = build_catalog_router(CatalogKind.PURCHASE_CHANNEL, "canais")
