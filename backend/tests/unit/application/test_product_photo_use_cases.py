from uuid import uuid4

import pytest

from sac.application.use_cases.product_photo import (
    ConfirmProductPhotoUseCase,
    DeleteProductPhotoUseCase,
    PhotoIntentInput,
    RequestProductPhotoUploadUseCase,
)
from sac.domain.attachments import preview_keys_for
from sac.domain.cadastros import Product
from sac.domain.errors import NotFoundError, ValidationError
from tests.unit.fakes import InMemoryProductRepository
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryPreviewJobRepository,
    InMemoryProductPhotoRepository,
)

SLUG = "acme"


class Env:
    def __init__(self) -> None:
        self.products = InMemoryProductRepository()
        self.photos = InMemoryProductPhotoRepository()
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()

    async def produto(self) -> Product:
        produto = Product(id=uuid4(), name="Alicate", sku=f"SKU-{uuid4().hex[:6]}")
        await self.products.add(produto)
        return produto

    def request_uc(self) -> RequestProductPhotoUploadUseCase:
        return RequestProductPhotoUploadUseCase(self.products, self.storage, tenant_slug=SLUG)

    def confirm_uc(self) -> ConfirmProductPhotoUseCase:
        return ConfirmProductPhotoUseCase(
            self.products, self.photos, self.jobs, self.storage, tenant_slug=SLUG
        )


async def test_intencao_gera_chave_no_prefixo_do_produto() -> None:
    env = Env()
    produto = await env.produto()
    intent = await env.request_uc().execute(
        produto.id, PhotoIntentInput(content_type="image/png", size_bytes=5000)
    )
    assert intent.object_key.startswith(f"{SLUG}/catalogo/produtos/{produto.id}/")
    assert intent.object_key.endswith(".png")
    assert intent.upload_url == f"https://fake/put/{intent.object_key}"


async def test_intencao_recusa_nao_imagem_e_produto_inexistente() -> None:
    env = Env()
    produto = await env.produto()
    uc = env.request_uc()
    for mime in ("application/pdf", "video/mp4"):
        with pytest.raises(ValidationError):
            await uc.execute(produto.id, PhotoIntentInput(mime, 1000))
    with pytest.raises(NotFoundError):
        await uc.execute(uuid4(), PhotoIntentInput("image/png", 1000))


async def test_confirmacao_grava_chave_e_enfileira_preview() -> None:
    env = Env()
    produto = await env.produto()
    intent = await env.request_uc().execute(produto.id, PhotoIntentInput("image/png", 100))
    env.storage.simulate_upload(intent.object_key, b"x" * 100, "image/png")

    await env.confirm_uc().execute(produto.id, intent.object_key)
    assert await env.photos.get_photo(produto.id) == (intent.object_key, None)
    assert len(env.jobs.items) == 1
    job = next(iter(env.jobs.items.values()))
    assert job.product_id == produto.id
    assert job.attachment_id is None
    assert job.object_key == intent.object_key


async def test_confirmacao_recusa_chave_de_outro_produto_ou_sem_objeto() -> None:
    env = Env()
    produto = await env.produto()
    outro = await env.produto()
    intent = await env.request_uc().execute(outro.id, PhotoIntentInput("image/png", 100))
    env.storage.simulate_upload(intent.object_key, b"x" * 100, "image/png")

    with pytest.raises(ValidationError) as exc:
        await env.confirm_uc().execute(produto.id, intent.object_key)
    assert exc.value.details == {"field": "object_key"}

    valida = await env.request_uc().execute(produto.id, PhotoIntentInput("image/png", 100))
    with pytest.raises(ValidationError):
        await env.confirm_uc().execute(produto.id, valida.object_key)


async def test_exclusao_limpa_as_duas_chaves() -> None:
    env = Env()
    produto = await env.produto()
    thumb, _ = preview_keys_for(f"{SLUG}/catalogo/produtos/{produto.id}/x.png")
    await env.photos.set_photo(produto.id, "chave.png", thumb)

    await DeleteProductPhotoUseCase(env.products, env.photos).execute(produto.id)
    assert await env.photos.get_photo(produto.id) == (None, None)

    with pytest.raises(NotFoundError):
        await DeleteProductPhotoUseCase(env.products, env.photos).execute(uuid4())
