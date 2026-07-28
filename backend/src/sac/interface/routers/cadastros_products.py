from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.customers import clamp_page
from sac.application.use_cases.products import (
    CreateProductUseCase,
    ListProductsUseCase,
    ProductInput,
    SetProductActiveUseCase,
    UpdateProductUseCase,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlProductRepository
from sac.interface.deps import get_product_repository, require_permission
from sac.interface.schemas import (
    ActiveIn,
    ProductIn,
    ProductOut,
    ProductsPageOut,
    product_out,
)

router = APIRouter(prefix="/cadastros/produtos", tags=["cadastros"])


@router.get(
    "",
    response_model=ProductsPageOut,
    dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
)
async def list_products(
    search: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 20,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductsPageOut:
    page, per_page = clamp_page(page, per_page)
    items, total = await ListProductsUseCase(repo).execute(search, active, page, per_page)
    return ProductsPageOut(
        items=[product_out(p) for p in items], total=total, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=ProductOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
)
async def create_product(
    body: ProductIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(
        await CreateProductUseCase(repo).execute(
            ProductInput(
                name=body.name, sku=body.sku, segment=body.segment, description=body.description
            )
        )
    )


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def update_product(
    product_id: UUID,
    body: ProductIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(
        await UpdateProductUseCase(repo).execute(
            product_id,
            ProductInput(
                name=body.name, sku=body.sku, segment=body.segment, description=body.description
            ),
        )
    )


@router.patch(
    "/{product_id}/active",
    response_model=ProductOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def set_product_active(
    product_id: UUID,
    body: ActiveIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(await SetProductActiveUseCase(repo).execute(product_id, body.active))
