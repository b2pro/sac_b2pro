from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sac.application.ports_attachments import (
    PreviewJobRepository,
    ProductPhotoRepository,
    StoragePort,
)
from sac.application.ports_cadastros import ProductRepository
from sac.domain.attachments import (
    AttachmentKind,
    PreviewJob,
    PreviewJobStatus,
    build_product_photo_key,
    kind_for,
    validate_size,
)
from sac.domain.errors import NotFoundError, ValidationError


@dataclass(frozen=True)
class PhotoIntentInput:
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class PhotoIntent:
    object_key: str
    upload_url: str
    expires_in: int


def _prefix_for(tenant_slug: str, product_id: UUID) -> str:
    return f"{tenant_slug}/catalogo/produtos/{product_id}/"


class RequestProductPhotoUploadUseCase:
    def __init__(
        self,
        products: ProductRepository,
        storage: StoragePort,
        tenant_slug: str,
        ttl_seconds: int = 300,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._products = products
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._ttl = ttl_seconds
        self._max_bytes = max_bytes

    async def execute(self, product_id: UUID, data: PhotoIntentInput) -> PhotoIntent:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        if kind_for(data.content_type) is not AttachmentKind.IMAGEM:
            raise ValidationError(
                "foto de catalogo aceita apenas imagem", details={"field": "content_type"}
            )
        validate_size(data.size_bytes)
        object_key = build_product_photo_key(
            self._tenant_slug, product_id, data.content_type, uuid4()
        )
        return PhotoIntent(
            object_key=object_key,
            upload_url=self._storage.presigned_put(
                object_key, data.content_type, self._max_bytes, self._ttl
            ),
            expires_in=self._ttl,
        )


class ConfirmProductPhotoUseCase:
    def __init__(
        self,
        products: ProductRepository,
        photos: ProductPhotoRepository,
        jobs: PreviewJobRepository,
        storage: StoragePort,
        tenant_slug: str,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._products = products
        self._photos = photos
        self._jobs = jobs
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._max_bytes = max_bytes

    async def execute(self, product_id: UUID, object_key: str) -> None:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        # a chave vem do client, entao precisa pertencer ao prefixo deste produto
        if not object_key.startswith(_prefix_for(self._tenant_slug, product_id)):
            raise ValidationError(
                "chave de objeto nao pertence a este produto",
                details={"field": "object_key"},
            )
        head = self._storage.head(object_key)
        if head is None:
            raise ValidationError(
                "objeto nao encontrado no storage", details={"field": "object_key"}
            )
        if kind_for(head.content_type) is not AttachmentKind.IMAGEM:
            raise ValidationError("objeto nao e imagem", details={"field": "content_type"})
        if head.size_bytes < 1 or head.size_bytes > self._max_bytes:
            raise ValidationError(
                "tamanho real do objeto invalido", details={"field": "size_bytes"}
            )
        await self._photos.set_photo(product_id, object_key, None)
        await self._jobs.add(
            PreviewJob(
                id=uuid4(),
                tenant_slug=self._tenant_slug,
                object_key=object_key,
                kind=AttachmentKind.IMAGEM,
                status=PreviewJobStatus.PENDENTE,
                attempts=0,
                next_attempt_at=datetime.now(UTC),
                product_id=product_id,
            )
        )


class DeleteProductPhotoUseCase:
    def __init__(self, products: ProductRepository, photos: ProductPhotoRepository) -> None:
        self._products = products
        self._photos = photos

    async def execute(self, product_id: UUID) -> None:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        await self._photos.set_photo(product_id, None, None)
