from uuid import uuid4

import pytest

from sac.application.use_cases.members_admin import (
    CreateMemberInput,
    CreateMemberUseCase,
    ListMembersAdminUseCase,
    ResetMemberPasswordUseCase,
    UpdateMemberLinkUseCase,
)
from sac.domain.entities import Tenant, User
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)


async def _tenant(tenants: InMemoryTenantRepository) -> Tenant:
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    await tenants.add(tenant)
    return tenant


async def test_criar_membro_com_email_novo_exige_nome_e_senha() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    with pytest.raises(ValidationError):
        await use_case.execute(
            tenant.id, CreateMemberInput(email="nova@b2.com", role=Role.ATENDENTE)
        )

    with pytest.raises(ValidationError):
        await use_case.execute(
            tenant.id,
            CreateMemberInput(email="nova@b2.com", role=Role.ATENDENTE, name="Nova"),
        )


async def test_criar_membro_com_email_novo_cria_usuario_e_vinculo() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    detail = await use_case.execute(
        tenant.id,
        CreateMemberInput(
            email="  Nova@B2.com ", role=Role.ATENDENTE, name="Nova", password="senha-forte-123"
        ),
    )

    assert detail.email == "nova@b2.com"
    assert detail.role is Role.ATENDENTE
    assert detail.active is True
    assert detail.user_active is True
    stored = await users.get_by_email("nova@b2.com")
    assert stored is not None
    assert stored.password_hash == "h:senha-forte-123"


async def test_criar_membro_com_email_existente_so_cria_vinculo() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    existente = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h:antiga")
    await users.add(existente)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    detail = await use_case.execute(
        tenant.id, CreateMemberInput(email="ana@b2.com", role=Role.SUPERVISOR)
    )

    assert detail.id == existente.id
    assert detail.role is Role.SUPERVISOR
    # senha do usuario existente nao muda so por ganhar um vinculo novo
    assert existente.password_hash == "h:antiga"


async def test_criar_membro_com_email_ja_vinculado_gera_conflito() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    existente = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h")
    await users.add(existente)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())
    await use_case.execute(tenant.id, CreateMemberInput(email="ana@b2.com", role=Role.ATENDENTE))

    with pytest.raises(ConflictError):
        await use_case.execute(tenant.id, CreateMemberInput(email="ana@b2.com", role=Role.ADMIN))


async def test_criar_membro_com_email_de_super_admin_nao_revela_existencia() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    await users.add(sa)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    with pytest.raises(NotFoundError):
        await use_case.execute(tenant.id, CreateMemberInput(email="sa@b2.com", role=Role.ATENDENTE))


async def test_atualizar_vinculo_altera_papel_e_ativo() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    membro = User(id=uuid4(), name="Bea", email="bea@b2.com", password_hash="h")
    await users.add(membro)
    await CreateMemberUseCase(users, tenants, links, FakeHasher()).execute(
        tenant.id, CreateMemberInput(email="bea@b2.com", role=Role.ATENDENTE)
    )
    acting_id = uuid4()

    use_case = UpdateMemberLinkUseCase(users, links)
    detail = await use_case.execute(tenant.id, acting_id, membro.id, Role.SUPERVISOR, False)

    assert detail.role is Role.SUPERVISOR
    assert detail.active is False


async def test_atualizar_proprio_vinculo_gera_conflito() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    admin = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h")
    await users.add(admin)
    await CreateMemberUseCase(users, tenants, links, FakeHasher()).execute(
        tenant.id, CreateMemberInput(email="ana@b2.com", role=Role.ADMIN)
    )

    use_case = UpdateMemberLinkUseCase(users, links)
    with pytest.raises(ConflictError):
        await use_case.execute(tenant.id, admin.id, admin.id, None, False)


async def test_atualizar_vinculo_de_super_admin_nao_encontrado() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenant_id = uuid4()
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    await users.add(sa)

    use_case = UpdateMemberLinkUseCase(users, links)
    with pytest.raises(NotFoundError):
        await use_case.execute(tenant_id, uuid4(), sa.id, Role.ATENDENTE, None)


async def test_atualizar_vinculo_inexistente_neste_tenant_nao_encontrado() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    membro = User(id=uuid4(), name="Bea", email="bea@b2.com", password_hash="h")
    await users.add(membro)

    use_case = UpdateMemberLinkUseCase(users, links)
    with pytest.raises(NotFoundError):
        await use_case.execute(uuid4(), uuid4(), membro.id, Role.ATENDENTE, None)


async def test_resetar_senha_de_membro() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    membro = User(id=uuid4(), name="Bea", email="bea@b2.com", password_hash="h:antiga")
    await users.add(membro)
    await CreateMemberUseCase(users, tenants, links, FakeHasher()).execute(
        tenant.id, CreateMemberInput(email="bea@b2.com", role=Role.ATENDENTE)
    )

    use_case = ResetMemberPasswordUseCase(users, links, FakeHasher())
    await use_case.execute(tenant.id, uuid4(), membro.id, "nova-senha-forte")

    atualizado = await users.get_by_id(membro.id)
    assert atualizado is not None and atualizado.password_hash == "h:nova-senha-forte"


async def test_resetar_a_propria_senha_gera_conflito() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    admin = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h")
    await users.add(admin)

    use_case = ResetMemberPasswordUseCase(users, links, FakeHasher())
    with pytest.raises(ConflictError):
        await use_case.execute(uuid4(), admin.id, admin.id, "nova-senha-forte")


async def test_resetar_senha_com_vinculo_inexistente_nao_encontrado() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    membro = User(id=uuid4(), name="Bea", email="bea@b2.com", password_hash="h")
    await users.add(membro)

    use_case = ResetMemberPasswordUseCase(users, links, FakeHasher())
    with pytest.raises(NotFoundError):
        await use_case.execute(uuid4(), uuid4(), membro.id, "nova-senha-forte")


async def test_listagem_gerencial_traz_dados_completos_e_esconde_super_admin() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    create = CreateMemberUseCase(users, tenants, links, FakeHasher())
    await create.execute(
        tenant.id,
        CreateMemberInput(
            email="bea@b2.com", role=Role.ATENDENTE, name="Bea", password="senha-forte-123"
        ),
    )
    await create.execute(
        tenant.id,
        CreateMemberInput(
            email="ana@b2.com", role=Role.ADMIN, name="Ana", password="senha-forte-123"
        ),
    )
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    await users.add(sa)

    use_case = ListMembersAdminUseCase(users, links)
    membros = await use_case.execute(tenant.id)

    nomes = [m.name for m in membros]
    assert nomes == ["Ana", "Bea"]
    por_nome = {m.name: m for m in membros}
    assert por_nome["Ana"].email == "ana@b2.com"
    assert por_nome["Ana"].role is Role.ADMIN
    assert por_nome["Ana"].user_active is True
