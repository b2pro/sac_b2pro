from uuid import UUID

from fastapi import APIRouter, Depends, Response

from sac.application.use_cases.customers import clamp_page
from sac.application.use_cases.product_photo import (
    ConfirmProductPhotoUseCase,
    DeleteProductPhotoUseCase,
    PhotoIntentInput,
    RequestProductPhotoUploadUseCase,
)
from sac.application.use_cases.products import (
    CreateProductUseCase,
    GetProductUseCase,
    ListProductsUseCase,
    ProductInput,
    SetProductActiveUseCase,
    UpdateProductUseCase,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_attachments import AttachmentRepos
from sac.infrastructure.repositories_cadastros import SqlProductRepository
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.interface.deps import (
    get_attachment_repos,
    get_product_repository,
    get_settings,
    get_storage,
    get_tenant_slug,
    require_permission,
)
from sac.interface.schemas import (
    ActiveIn,
    PhotoConfirmIn,
    PhotoIntentIn,
    PhotoIntentOut,
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
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> ProductsPageOut:
    page, per_page = clamp_page(page, per_page)
    views, total = await ListProductsUseCase(repo, storage, settings.presigned_ttl_seconds).execute(
        search, active, page, per_page
    )
    return ProductsPageOut(
        items=[product_out(v.product, v.photo_url) for v in views],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
)
async def get_product(
    product_id: UUID,
    repo: SqlProductRepository = Depends(get_product_repository),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> ProductOut:
    view = await GetProductUseCase(repo, storage, settings.presigned_ttl_seconds).execute(
        product_id
    )
    return product_out(view.product, view.photo_url)


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


@router.post(
    "/{product_id}/foto/intencao",
    response_model=PhotoIntentOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def request_photo_upload(
    product_id: UUID,
    body: PhotoIntentIn,
    repo: SqlProductRepository = Depends(get_product_repository),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> PhotoIntentOut:
    intent = await RequestProductPhotoUploadUseCase(
        repo,
        storage,
        tenant_slug=tenant_slug,
        ttl_seconds=settings.presigned_ttl_seconds,
    ).execute(product_id, PhotoIntentInput(body.content_type, body.size_bytes))
    return PhotoIntentOut(
        object_key=intent.object_key,
        upload_url=intent.upload_url,
        expires_in=intent.expires_in,
    )


@router.post(
    "/{product_id}/foto/confirmar",
    status_code=204,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def confirm_photo(
    product_id: UUID,
    body: PhotoConfirmIn,
    repo: SqlProductRepository = Depends(get_product_repository),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> Response:
    await ConfirmProductPhotoUseCase(
        repo,
        anexos.photos,
        anexos.jobs,
        storage,
        tenant_slug=tenant_slug,
        max_bytes=settings.attachment_max_bytes,
    ).execute(product_id, body.object_key)
    return Response(status_code=204)


@router.delete(
    "/{product_id}/foto",
    status_code=204,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def delete_photo(
    product_id: UUID,
    repo: SqlProductRepository = Depends(get_product_repository),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
) -> Response:
    await DeleteProductPhotoUseCase(repo, anexos.photos).execute(product_id)
    return Response(status_code=204)
