from fastapi import APIRouter, Depends

from sac.application.use_cases.members import ListTenantMembersUseCase
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_attachments import SqlTenantMemberDirectory
from sac.interface.deps import get_member_directory, get_tenant_slug, require_any_permission
from sac.interface.schemas import MemberOut

router = APIRouter(prefix="/membros", tags=["membros"])

_read = require_any_permission(
    Permission.CRIAR_TICKET,
    Permission.EDITAR_PROPRIO_TICKET,
    Permission.EDITAR_QUALQUER_TICKET,
)


@router.get(
    "",
    response_model=list[MemberOut],
    dependencies=[Depends(get_tenant_slug), Depends(_read)],
)
async def list_members(
    tenant_slug: str = Depends(get_tenant_slug),
    directory: SqlTenantMemberDirectory = Depends(get_member_directory),
) -> list[MemberOut]:
    membros = await ListTenantMembersUseCase(directory).execute(tenant_slug)
    return [MemberOut(id=m.id, name=m.name, role=m.role, active=m.active) for m in membros]
