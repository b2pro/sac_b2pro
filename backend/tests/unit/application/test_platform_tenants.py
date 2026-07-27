from uuid import uuid4

import pytest

from sac.application.use_cases.platform_tenants import (
    CreateTenantInput,
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.domain.entities import Tenant, TenantStatus
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from tests.unit.fakes import InMemoryTenantRepository


class FakeProvisioner:
    def __init__(self) -> None:
        self.provisioned: list[str] = []

    async def provision(self, schema_name: str) -> None:
        self.provisioned.append(schema_name)


async def test_criar_tenant_provisiona_schema() -> None:
    tenants = InMemoryTenantRepository()
    provisioner = FakeProvisioner()
    use_case = CreateTenantUseCase(tenants, provisioner)

    tenant = await use_case.execute(
        CreateTenantInput(slug="b2pro", name="B2PRO", modules={"tickets": True})
    )

    assert tenant.status is TenantStatus.ATIVA
    assert provisioner.provisioned == ["t_b2pro"]
    assert await tenants.get_by_slug("b2pro") is not None


async def test_slug_invalido_e_rejeitado_sem_provisionar() -> None:
    provisioner = FakeProvisioner()
    use_case = CreateTenantUseCase(InMemoryTenantRepository(), provisioner)
    with pytest.raises(ValidationError):
        await use_case.execute(CreateTenantInput(slug="Com-Hifen", name="X", modules={}))
    assert provisioner.provisioned == []


async def test_modulo_com_nome_invalido_e_rejeitado() -> None:
    use_case = CreateTenantUseCase(InMemoryTenantRepository(), FakeProvisioner())
    with pytest.raises(ValidationError):
        await use_case.execute(
            CreateTenantInput(slug="b2pro", name="X", modules={"Tickets!": True})
        )


async def test_slug_duplicado_gera_conflito() -> None:
    tenants = InMemoryTenantRepository()
    use_case = CreateTenantUseCase(tenants, FakeProvisioner())
    await use_case.execute(CreateTenantInput(slug="b2pro", name="X", modules={}))
    with pytest.raises(ConflictError):
        await use_case.execute(CreateTenantInput(slug="b2pro", name="Y", modules={}))


async def test_alterar_status_e_modulos() -> None:
    tenants = InMemoryTenantRepository()
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    await tenants.add(tenant)

    alterado = await SetTenantStatusUseCase(tenants).execute(tenant.id, TenantStatus.SUSPENSA)
    assert alterado.status is TenantStatus.SUSPENSA

    alterado = await SetTenantModulesUseCase(tenants).execute(tenant.id, {"tickets": False})
    assert alterado.modules == {"tickets": False}

    assert len(await ListTenantsUseCase(tenants).execute()) == 1


async def test_status_de_tenant_inexistente_gera_not_found() -> None:
    with pytest.raises(NotFoundError):
        await SetTenantStatusUseCase(InMemoryTenantRepository()).execute(
            uuid4(), TenantStatus.ATIVA
        )
