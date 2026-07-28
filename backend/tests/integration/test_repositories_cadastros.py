from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem, CatalogKind
from sac.domain.errors import ConflictError
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories_cadastros import (
    SqlCatalogRepository,
    SqlCustomerRepository,
    SqlProductRepository,
)


@pytest.fixture
async def tenant_session(engine: AsyncEngine):
    await AlembicTenantProvisioner(engine).provision("t_repo")
    translated = engine.execution_options(schema_translate_map={"tenant": "t_repo"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        yield session


def _item(name: str) -> CatalogItem:
    return CatalogItem(id=uuid4(), name=name)


def _customer(document: str = "52998224725", name: str = "Ana") -> Customer:
    return Customer(id=uuid4(), name=name, document=document)


def _product(sku: str = "PLN-10-7", name: str = "Alicate") -> Product:
    return Product(id=uuid4(), name=name, sku=sku)


async def test_catalogo_roundtrip_busca_e_conflito(tenant_session) -> None:
    repo = SqlCatalogRepository(tenant_session, CatalogKind.BRAND)
    await repo.add(_item("MARCA-X"))
    await tenant_session.commit()

    assert await repo.get_by_name("MARCA-X") is not None
    encontrados = await repo.list(search="marca-x", active=None)
    assert any(i.name == "MARCA-X" for i in encontrados)

    item = await repo.get_by_name("MARCA-X")
    assert item is not None
    item.name = "MARCA-Y"
    item.active = False
    await repo.update(item)
    await tenant_session.commit()
    atualizado = await repo.get(item.id)
    assert atualizado is not None and atualizado.name == "MARCA-Y" and not atualizado.active

    with pytest.raises(ConflictError):
        await repo.add(_item("MARCA-Y"))


async def test_catalogo_e_por_tabela(tenant_session) -> None:
    brands = SqlCatalogRepository(tenant_session, CatalogKind.BRAND)
    defects = SqlCatalogRepository(tenant_session, CatalogKind.DEFECT_TYPE)
    await brands.add(_item("SO-NA-MARCA"))
    await tenant_session.commit()
    assert await defects.get_by_name("SO-NA-MARCA") is None


async def test_cliente_roundtrip_busca_por_documento_e_paginacao(tenant_session) -> None:
    repo = SqlCustomerRepository(tenant_session)
    await repo.add(_customer("52998224725", "Ana Silva"))
    await repo.add(_customer("11222333000181", "Beauty Ltda"))
    await repo.add(_customer("15350946056", "Carla Souza"))
    await tenant_session.commit()

    por_documento, total = await repo.list(search="529.982", active=None, page=1, per_page=20)
    assert total == 1 and por_documento[0].name == "Ana Silva"

    pagina, total = await repo.list(search=None, active=None, page=1, per_page=2)
    assert total == 3 and len(pagina) == 2

    with pytest.raises(ConflictError):
        await repo.add(_customer("52998224725", "Duplicada"))


async def test_produto_roundtrip_busca_e_conflito(tenant_session) -> None:
    repo = SqlProductRepository(tenant_session)
    await repo.add(_product("PLN-10-7", "Alicate profissional"))
    await tenant_session.commit()

    por_sku, total = await repo.list(search="pln-10", active=None, page=1, per_page=20)
    assert total == 1

    with pytest.raises(ConflictError):
        await repo.add(_product("PLN-10-7", "Outro nome"))
