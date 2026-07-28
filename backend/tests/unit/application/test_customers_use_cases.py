import pytest

from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    ListCustomersUseCase,
    SetCustomerActiveUseCase,
    UpdateCustomerUseCase,
)
from sac.domain.errors import ConflictError, ValidationError
from tests.unit.fakes import InMemoryCustomerRepository


def _input(document: str = "529.982.247-25", **kwargs: str | None) -> CustomerInput:
    base: dict[str, str | None] = {
        "name": "Ana Silva",
        "document": document,
        "phone": "(54) 99982-3566",
        "cep": "95010-000",
        "state": "rs",
    }
    base.update(kwargs)
    return CustomerInput(**base)  # type: ignore[arg-type]


async def test_criar_normaliza_documento_telefone_cep_e_uf() -> None:
    repo = InMemoryCustomerRepository()
    customer = await CreateCustomerUseCase(repo).execute(_input())
    assert customer.document == "52998224725"
    assert customer.phone == "54999823566"
    assert customer.cep == "95010000"
    assert customer.state == "RS"


async def test_documento_invalido_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCustomerUseCase(InMemoryCustomerRepository()).execute(
            _input(document="123.456.789-00")
        )


async def test_cep_invalido_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCustomerUseCase(InMemoryCustomerRepository()).execute(_input(cep="1234"))


async def test_documento_duplicado_gera_conflito() -> None:
    repo = InMemoryCustomerRepository()
    await CreateCustomerUseCase(repo).execute(_input())
    with pytest.raises(ConflictError):
        await CreateCustomerUseCase(repo).execute(_input(name="Outra"))


async def test_atualizar_preserva_id_e_detecta_conflito() -> None:
    repo = InMemoryCustomerRepository()
    create = CreateCustomerUseCase(repo)
    ana = await create.execute(_input())
    bia = await create.execute(_input(document="153.509.460-56", name="Bia"))

    atualizado = await UpdateCustomerUseCase(repo).execute(ana.id, _input(name="Ana Maria"))
    assert atualizado.id == ana.id and atualizado.name == "Ana Maria"

    with pytest.raises(ConflictError):
        await UpdateCustomerUseCase(repo).execute(bia.id, _input(document="529.982.247-25"))


async def test_listagem_paginada_e_clamp() -> None:
    repo = InMemoryCustomerRepository()
    create = CreateCustomerUseCase(repo)
    await create.execute(_input())
    await create.execute(_input(document="153.509.460-56", name="Bia"))
    await create.execute(_input(document="11.222.333/0001-81", name="Cia Ltda"))

    itens, total = await ListCustomersUseCase(repo).execute(page=1, per_page=2)
    assert total == 3 and len(itens) == 2

    itens, total = await ListCustomersUseCase(repo).execute(page=0, per_page=1000)
    assert total == 3 and len(itens) == 3


async def test_inativar_cliente() -> None:
    repo = InMemoryCustomerRepository()
    customer = await CreateCustomerUseCase(repo).execute(_input())
    inativado = await SetCustomerActiveUseCase(repo).execute(customer.id, False)
    assert inativado.active is False
