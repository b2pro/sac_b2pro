import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sac.application.ports import TenantProvisionerPort, TenantRepository
from sac.domain.entities import Tenant, TenantStatus, validate_slug
from sac.domain.errors import ConflictError, NotFoundError, ValidationError

_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def _validate_modules(modules: dict[str, bool]) -> None:
    for key in modules:
        if not _MODULE_RE.fullmatch(key):
            raise ValidationError(f"nome de modulo invalido: {key}")


@dataclass(frozen=True)
class CreateTenantInput:
    slug: str
    name: str
    modules: dict[str, bool] = field(default_factory=dict)


class CreateTenantUseCase:
    def __init__(self, tenants: TenantRepository, provisioner: TenantProvisionerPort) -> None:
        self._tenants = tenants
        self._provisioner = provisioner

    async def execute(self, data: CreateTenantInput) -> Tenant:
        validate_slug(data.slug)
        _validate_modules(data.modules)
        if await self._tenants.get_by_slug(data.slug) is not None:
            raise ConflictError("slug ja cadastrado")
        tenant = Tenant(id=uuid4(), slug=data.slug, name=data.name, modules=dict(data.modules))
        await self._tenants.add(tenant)
        await self._provisioner.provision(tenant.schema_name)
        return tenant


class ListTenantsUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self) -> list[Tenant]:
        return await self._tenants.list_all()


class SetTenantStatusUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self, tenant_id: UUID, status: TenantStatus) -> Tenant:
        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant nao encontrado")
        tenant.status = status
        await self._tenants.update(tenant)
        return tenant


class SetTenantModulesUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self, tenant_id: UUID, modules: dict[str, bool]) -> Tenant:
        _validate_modules(modules)
        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant nao encontrado")
        tenant.modules = dict(modules)
        await self._tenants.update(tenant)
        return tenant
