from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.platform_tenants import (
    CreateTenantInput,
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.application.use_cases.platform_users import (
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    UnlinkUserFromTenantUseCase,
)
from sac.interface.deps import (
    get_create_tenant_use_case,
    get_link_use_case,
    get_list_links_use_case,
    get_list_tenants_use_case,
    get_set_tenant_modules_use_case,
    get_set_tenant_status_use_case,
    get_unlink_use_case,
    require_super_admin,
)
from sac.interface.schemas import (
    LinkCreateIn,
    LinkOut,
    TenantCreateIn,
    TenantModulesIn,
    TenantOut,
    TenantStatusIn,
    tenant_out,
)

router = APIRouter(
    prefix="/platform/tenants",
    tags=["platform"],
    dependencies=[Depends(require_super_admin)],
)


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreateIn,
    use_case: CreateTenantUseCase = Depends(get_create_tenant_use_case),
) -> TenantOut:
    tenant = await use_case.execute(
        CreateTenantInput(slug=body.slug, name=body.name, modules=body.modules)
    )
    return tenant_out(tenant)


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    use_case: ListTenantsUseCase = Depends(get_list_tenants_use_case),
) -> list[TenantOut]:
    return [tenant_out(t) for t in await use_case.execute()]


@router.patch("/{tenant_id}/status", response_model=TenantOut)
async def set_status(
    tenant_id: UUID,
    body: TenantStatusIn,
    use_case: SetTenantStatusUseCase = Depends(get_set_tenant_status_use_case),
) -> TenantOut:
    return tenant_out(await use_case.execute(tenant_id, body.status))


@router.put("/{tenant_id}/modules", response_model=TenantOut)
async def set_modules(
    tenant_id: UUID,
    body: TenantModulesIn,
    use_case: SetTenantModulesUseCase = Depends(get_set_tenant_modules_use_case),
) -> TenantOut:
    return tenant_out(await use_case.execute(tenant_id, body.modules))


@router.post("/{tenant_id}/links", response_model=LinkOut, status_code=201)
async def create_link(
    tenant_id: UUID,
    body: LinkCreateIn,
    use_case: LinkUserToTenantUseCase = Depends(get_link_use_case),
) -> LinkOut:
    link = await use_case.execute(body.user_id, tenant_id, body.role)
    return LinkOut(
        user_id=link.user_id, tenant_id=link.tenant_id, role=link.role, active=link.active
    )


@router.get("/{tenant_id}/links", response_model=list[LinkOut])
async def list_links(
    tenant_id: UUID,
    use_case: ListTenantLinksUseCase = Depends(get_list_links_use_case),
) -> list[LinkOut]:
    return [
        LinkOut(user_id=x.user_id, tenant_id=x.tenant_id, role=x.role, active=x.active)
        for x in await use_case.execute(tenant_id)
    ]


@router.delete("/{tenant_id}/links/{user_id}", status_code=204)
async def delete_link(
    tenant_id: UUID,
    user_id: UUID,
    use_case: UnlinkUserFromTenantUseCase = Depends(get_unlink_use_case),
) -> None:
    await use_case.execute(user_id, tenant_id)
