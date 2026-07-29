from sac.application.ports_attachments import TenantMember, TenantMemberDirectory


class ListTenantMembersUseCase:
    def __init__(self, directory: TenantMemberDirectory) -> None:
        self._directory = directory

    async def execute(self, tenant_slug: str) -> list[TenantMember]:
        return await self._directory.list_members(tenant_slug)
