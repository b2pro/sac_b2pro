import pytest

from sac.application.use_cases.products import (
    CreateProductUseCase,
    ListProductsUseCase,
    ProductInput,
    SetProductActiveUseCase,
    UpdateProductUseCase,
)
from sac.domain.errors import ConflictError, ValidationError
from tests.unit.fakes import InMemoryProductRepository
from tests.unit.fakes_attachments import FakeStorage


async def test_criar_produto_normaliza_sku() -> None:
    repo = InMemoryProductRepository()
    product = await CreateProductUseCase(repo).execute(
        ProductInput(name="Alicate", sku="  PLN-10-7  ", segment="Manicure")
    )
    assert product.sku == "PLN-10-7"
    assert product.photo_key is None


async def test_sku_vazio_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateProductUseCase(InMemoryProductRepository()).execute(
            ProductInput(name="Alicate", sku="  ")
        )


async def test_sku_duplicado_gera_conflito() -> None:
    repo = InMemoryProductRepository()
    await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    with pytest.raises(ConflictError):
        await CreateProductUseCase(repo).execute(ProductInput(name="B", sku="X-1"))


async def test_atualizar_produto_preserva_photo_key() -> None:
    repo = InMemoryProductRepository()
    product = await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    guardado = await repo.get(product.id)
    assert guardado is not None
    guardado.photo_key = "tenant/produto/foto.webp"
    await repo.update(guardado)

    atualizado = await UpdateProductUseCase(repo).execute(
        product.id, ProductInput(name="A2", sku="X-1")
    )
    assert atualizado.photo_key == "tenant/produto/foto.webp"
    assert atualizado.name == "A2"


async def test_listar_e_inativar() -> None:
    repo = InMemoryProductRepository()
    storage = FakeStorage()
    product = await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    itens, total = await ListProductsUseCase(repo, storage).execute(search="x-1")
    assert total == 1 and itens[0].product.id == product.id
    assert itens[0].photo_url is None

    inativado = await SetProductActiveUseCase(repo).execute(product.id, False)
    assert inativado.active is False


async def test_listagem_traz_photo_url_apenas_quando_ha_preview() -> None:
    repo = InMemoryProductRepository()
    storage = FakeStorage()
    sem_foto = await CreateProductUseCase(repo).execute(ProductInput(name="Sem foto", sku="X-2"))
    com_foto = await CreateProductUseCase(repo).execute(ProductInput(name="Com foto", sku="X-3"))
    guardado = await repo.get(com_foto.id)
    assert guardado is not None
    guardado.photo_key = "acme/catalogo/produtos/x/foto.png"
    guardado.photo_preview_key = "acme/catalogo/produtos/x/previews/foto.webp"
    await repo.update(guardado)

    itens, _ = await ListProductsUseCase(repo, storage, ttl_seconds=120).execute()
    por_id = {v.product.id: v for v in itens}
    assert por_id[sem_foto.id].photo_url is None
    assert (
        por_id[com_foto.id].photo_url
        == "https://fake/get/acme/catalogo/produtos/x/previews/foto.webp"
    )


async def test_listagem_nao_expoe_photo_url_de_linha_meio_gravada() -> None:
    """photo_preview_key sem photo_key e uma linha inconsistente (foto removida
    ou substituida com um job de preview ainda em voo). Expor a URL nesse estado
    faz a thumb de uma foto que nao existe mais reaparecer na tabela e no dialog
    de edicao, e sem o botao "Remover foto" (que depende de photo_key)."""
    repo = InMemoryProductRepository()
    storage = FakeStorage()
    produto = await CreateProductUseCase(repo).execute(ProductInput(name="Meio", sku="X-4"))
    guardado = await repo.get(produto.id)
    assert guardado is not None
    guardado.photo_key = None
    guardado.photo_preview_key = "acme/catalogo/produtos/x/previews/orfa.webp"
    await repo.update(guardado)

    itens, _ = await ListProductsUseCase(repo, storage).execute()
    assert itens[0].photo_url is None
