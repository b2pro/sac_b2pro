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
    product = await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    itens, total = await ListProductsUseCase(repo).execute(search="x-1")
    assert total == 1 and itens[0].id == product.id

    inativado = await SetProductActiveUseCase(repo).execute(product.id, False)
    assert inativado.active is False
