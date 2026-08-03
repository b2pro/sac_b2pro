from uuid import UUID

from fastapi import APIRouter, Depends, Response

from sac.application.ports import TokenPayload
from sac.application.use_cases.members import ListTenantMembersUseCase
from sac.application.use_cases.members_admin import (
    CreateMemberInput,
    CreateMemberUseCase,
    ListMembersAdminUseCase,
    MemberDetail,
    ResetMemberPasswordUseCase,
    UpdateMemberLinkUseCase,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_attachments import SqlTenantMemberDirectory
from sac.interface.deps import (
    get_create_member_use_case,
    get_current_identity,
    get_current_tenant_id,
    get_list_members_admin_use_case,
    get_member_directory,
    get_reset_member_password_use_case,
    get_tenant_slug,
    get_update_member_link_use_case,
    require_any_permission,
    require_permission,
)
from sac.interface.schemas import (
    MemberCreateIn,
    MemberDetailOut,
    MemberLinkUpdateIn,
    MemberOut,
    PasswordResetIn,
)

router = APIRouter(prefix="/membros", tags=["membros"])

_read = require_any_permission(
    Permission.CRIAR_TICKET,
    Permission.EDITAR_PROPRIO_TICKET,
    Permission.EDITAR_QUALQUER_TICKET,
)
_manage = require_permission(Permission.GERENCIAR_USUARIOS)


def _member_detail_out(detail: MemberDetail) -> MemberDetailOut:
    return MemberDetailOut(
        id=detail.id,
        name=detail.name,
        email=detail.email,
        role=detail.role,
        active=detail.active,
        user_active=detail.user_active,
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


@router.get(
    "/gerencia",
    response_model=list[MemberDetailOut],
    dependencies=[Depends(get_tenant_slug), Depends(_manage)],
)
async def list_members_admin(
    tenant_id: UUID = Depends(get_current_tenant_id),
    use_case: ListMembersAdminUseCase = Depends(get_list_members_admin_use_case),
) -> list[MemberDetailOut]:
    return [_member_detail_out(m) for m in await use_case.execute(tenant_id)]


@router.post(
    "",
    response_model=MemberDetailOut,
    status_code=201,
    dependencies=[Depends(get_tenant_slug), Depends(_manage)],
)
async def create_member(
    body: MemberCreateIn,
    tenant_id: UUID = Depends(get_current_tenant_id),
    use_case: CreateMemberUseCase = Depends(get_create_member_use_case),
) -> MemberDetailOut:
    detail = await use_case.execute(
        tenant_id,
        CreateMemberInput(email=body.email, role=body.role, name=body.name, password=body.password),
    )
    return _member_detail_out(detail)


@router.patch(
    "/{user_id}",
    response_model=MemberDetailOut,
    dependencies=[Depends(get_tenant_slug), Depends(_manage)],
)
async def update_member_link(
    user_id: UUID,
    body: MemberLinkUpdateIn,
    tenant_id: UUID = Depends(get_current_tenant_id),
    identity: TokenPayload = Depends(get_current_identity),
    use_case: UpdateMemberLinkUseCase = Depends(get_update_member_link_use_case),
) -> MemberDetailOut:
    detail = await use_case.execute(tenant_id, identity.user_id, user_id, body.role, body.active)
    return _member_detail_out(detail)


@router.post(
    "/{user_id}/senha",
    status_code=204,
    dependencies=[Depends(get_tenant_slug), Depends(_manage)],
)
async def reset_member_password(
    user_id: UUID,
    body: PasswordResetIn,
    tenant_id: UUID = Depends(get_current_tenant_id),
    identity: TokenPayload = Depends(get_current_identity),
    use_case: ResetMemberPasswordUseCase = Depends(get_reset_member_password_use_case),
) -> Response:
    await use_case.execute(tenant_id, identity.user_id, user_id, body.password)
    return Response(status_code=204)
