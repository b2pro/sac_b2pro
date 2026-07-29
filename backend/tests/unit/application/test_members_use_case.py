from uuid import uuid4

from sac.application.ports_attachments import TenantMember
from sac.application.use_cases.members import ListTenantMembersUseCase
from sac.domain.permissions import Role
from tests.unit.fakes_attachments import InMemoryTenantMemberDirectory


async def test_lista_membros_do_tenant_do_token() -> None:
    ana = TenantMember(id=uuid4(), name="Ana", role=Role.ADMIN, active=True)
    bruno = TenantMember(id=uuid4(), name="Bruno", role=Role.ATENDENTE, active=True)
    de_outro = TenantMember(id=uuid4(), name="Carlos", role=Role.ADMIN, active=True)
    directory = InMemoryTenantMemberDirectory({"acme": [ana, bruno], "outro": [de_outro]})

    membros = await ListTenantMembersUseCase(directory).execute("acme")
    assert [m.name for m in membros] == ["Ana", "Bruno"]
    assert await ListTenantMembersUseCase(directory).execute("inexistente") == []
