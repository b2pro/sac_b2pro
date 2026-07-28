from uuid import uuid4

import pytest

from sac.application.use_cases.catalog import (
    CatalogItemInput,
    CreateCatalogItemUseCase,
    ListCatalogUseCase,
    SetCatalogItemActiveUseCase,
    UpdateCatalogItemUseCase,
)
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from tests.unit.fakes import InMemoryCatalogRepository


async def test_criar_normaliza_nome_e_lista() -> None:
    repo = InMemoryCatalogRepository()
    item = await CreateCatalogItemUseCase(repo).execute(
        CatalogItemInput(name="  Oxidacao  ", description="Produto oxidado")
    )
    assert item.name == "Oxidacao"
    assert item.active is True

    listados = await ListCatalogUseCase(repo).execute()
    assert [i.name for i in listados] == ["Oxidacao"]


async def test_nome_vazio_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCatalogItemUseCase(InMemoryCatalogRepository()).execute(
            CatalogItemInput(name="   ")
        )


async def test_nome_duplicado_gera_conflito() -> None:
    repo = InMemoryCatalogRepository()
    use_case = CreateCatalogItemUseCase(repo)
    await use_case.execute(CatalogItemInput(name="Danificado"))
    with pytest.raises(ConflictError):
        await use_case.execute(CatalogItemInput(name="Danificado"))


async def test_atualizar_renomeia_e_detecta_conflito() -> None:
    repo = InMemoryCatalogRepository()
    create = CreateCatalogItemUseCase(repo)
    a = await create.execute(CatalogItemInput(name="A"))
    b = await create.execute(CatalogItemInput(name="B"))

    atualizado = await UpdateCatalogItemUseCase(repo).execute(
        a.id, CatalogItemInput(name="A2", description="desc")
    )
    assert atualizado.name == "A2" and atualizado.description == "desc"

    with pytest.raises(ConflictError):
        await UpdateCatalogItemUseCase(repo).execute(b.id, CatalogItemInput(name="A2"))


async def test_atualizar_mantendo_o_proprio_nome_nao_conflita() -> None:
    repo = InMemoryCatalogRepository()
    a = await CreateCatalogItemUseCase(repo).execute(CatalogItemInput(name="Mesmo"))
    atualizado = await UpdateCatalogItemUseCase(repo).execute(
        a.id, CatalogItemInput(name="Mesmo", description="nova desc")
    )
    assert atualizado.description == "nova desc"


async def test_ativar_inativar_e_filtrar() -> None:
    repo = InMemoryCatalogRepository()
    item = await CreateCatalogItemUseCase(repo).execute(CatalogItemInput(name="Voucher"))

    inativado = await SetCatalogItemActiveUseCase(repo).execute(item.id, False)
    assert inativado.active is False

    ativos = await ListCatalogUseCase(repo).execute(active=True)
    assert all(i.id != item.id for i in ativos)

    with pytest.raises(NotFoundError):
        await SetCatalogItemActiveUseCase(repo).execute(uuid4(), True)
