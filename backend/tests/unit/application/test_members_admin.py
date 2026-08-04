from uuid import uuid4

import pytest

from sac.application.use_cases.members_admin import (
    CreateMemberInput,
    CreateMemberUseCase,
    ListMembersAdminUseCase,
    ResetMemberPasswordUseCase,
    UpdateMemberLinkUseCase,
)
from sac.domain.entities import Tenant, User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)

# name/senha "de preenchimento": exigidos sempre no corpo (mesmo quando o
# email ja existe e eles serao ignorados) para que a validacao nao funcione
# como oraculo de existencia -- ver CreateMemberUseCase.execute.
_NOME_PREENCHIMENTO = "Preenchimento"
_SENHA_PREENCHIMENTO = "senha-de-preenchimento-123"


async def _tenant(tenants: InMemoryTenantRepository, slug: str = "b2pro") -> Tenant:
    tenant = Tenant(id=uuid4(), slug=slug, name=slug.upper())
    await tenants.add(tenant)
    return tenant


def _input(
    email: str, role: Role, *, name: str | None = None, password: str | None = None
) -> CreateMemberInput:
    return CreateMemberInput(
        email=email,
        role=role,
        name=name if name is not None else _NOME_PREENCHIMENTO,
        password=password if password is not None else _SENHA_PREENCHIMENTO,
    )


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

    # nome/senha no corpo sao exigidos mas IGNORADOS: o usuario existente
    # mantem sua propria identidade e senha, so ganha um vinculo novo.
    detail = await use_case.execute(
        tenant.id, _input("ana@b2.com", Role.SUPERVISOR, name="Nome Que Nao Deveria Colar")
    )

    assert detail.id == existente.id
    assert detail.name == "Ana"
    assert detail.role is Role.SUPERVISOR
    assert existente.password_hash == "h:antiga"


async def test_criar_membro_com_email_ja_vinculado_gera_conflito() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    existente = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h")
    await users.add(existente)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())
    await use_case.execute(tenant.id, _input("ana@b2.com", Role.ATENDENTE))

    with pytest.raises(ConflictError):
        await use_case.execute(tenant.id, _input("ana@b2.com", Role.ADMIN))


async def test_criar_membro_com_email_de_super_admin_nao_revela_existencia() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    await users.add(sa)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    with pytest.raises(NotFoundError):
        await use_case.execute(tenant.id, _input("sa@b2.com", Role.ATENDENTE))


async def test_criar_membro_com_email_vinculado_a_outro_tenant_e_recusado() -> None:
    """O ataque que a revisao apontou: o brief so previa 'email existente:
    cria vinculo', mas combinado com o reset de senha (que escreve no usuario
    GLOBAL) isso permitiria o admin de um tenant vincular -- e depois assumir
    -- a conta de alguem de outro tenant. Vincular usuario de outro tenant e
    privilegio de super_admin (unico papel que cria vinculos hoje pelo painel
    de plataforma).
    """
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant_a = await _tenant(tenants, slug="tenant_a")
    tenant_b = await _tenant(tenants, slug="tenant_b")
    vitima = User(id=uuid4(), name="Vitima", email="vitima@b2.com", password_hash="h")
    await users.add(vitima)
    await links.add(UserTenant(user_id=vitima.id, tenant_id=tenant_b.id, role=Role.ATENDENTE))

    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())
    with pytest.raises(NotFoundError):
        await use_case.execute(tenant_a.id, _input("vitima@b2.com", Role.ATENDENTE))

    # nao criou vinculo nenhum com o tenant A
    assert await links.get(vitima.id, tenant_a.id) is None


async def test_recusas_de_super_admin_e_de_outro_tenant_sao_indistinguiveis() -> None:
    """Item 3 da revisao: as duas recusas usam a mesma mensagem/tipo de erro,
    para que um admin nao consiga, testando emails a esmo, diferenciar 'e
    super_admin' de 'pertence a outro tenant' -- as duas leriam como 'usuario
    nao encontrado' de qualquer forma.
    """
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant_a = await _tenant(tenants, slug="tenant_a")
    tenant_b = await _tenant(tenants, slug="tenant_b")
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    outro_tenant = User(id=uuid4(), name="Outro", email="outro@b2.com", password_hash="h")
    await users.add(sa)
    await users.add(outro_tenant)
    await links.add(UserTenant(user_id=outro_tenant.id, tenant_id=tenant_b.id, role=Role.ATENDENTE))

    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    with pytest.raises(NotFoundError) as erro_sa:
        await use_case.execute(tenant_a.id, _input("sa@b2.com", Role.ATENDENTE))
    with pytest.raises(NotFoundError) as erro_outro:
        await use_case.execute(tenant_a.id, _input("outro@b2.com", Role.ATENDENTE))

    assert str(erro_sa.value) == str(erro_outro.value)


async def test_corpo_minimo_da_422_mesmo_para_email_de_super_admin() -> None:
    """Colapsa o oraculo barato: enviar so {email, role} (sem name/password)
    dava 422 para email inexistente e nao-422 para email existente, revelando
    quais emails sao contas de verdade sem gastar nada. Agora a validacao de
    nome/senha roda ANTES de olhar o banco, entao o corpo minimo sempre da
    422, exista ou nao o usuario por tras do email.
    """
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    sa = User(id=uuid4(), name="SA", email="sa@b2.com", password_hash="h", is_super_admin=True)
    await users.add(sa)
    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())

    with pytest.raises(ValidationError):
        await use_case.execute(tenant.id, CreateMemberInput(email="sa@b2.com", role=Role.ATENDENTE))
    with pytest.raises(ValidationError):
        await use_case.execute(
            tenant.id, CreateMemberInput(email="jamais-existiu@b2.com", role=Role.ATENDENTE)
        )


async def test_vinculo_de_email_existente_sem_outro_tenant_continua_funcionando() -> None:
    """Nao quebrar o caso legitimo: usuario global sem vinculo em NENHUM
    tenant (ex.: criado e ainda nao alocado) continua vinculavel normalmente.
    """
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    tenant = await _tenant(tenants)
    livre = User(id=uuid4(), name="Livre", email="livre@b2.com", password_hash="h:original")
    await users.add(livre)

    use_case = CreateMemberUseCase(users, tenants, links, FakeHasher())
    detail = await use_case.execute(tenant.id, _input("livre@b2.com", Role.ATENDENTE))

    assert detail.id == livre.id
    assert detail.active is True
    assert await links.get(livre.id, tenant.id) is not None


async def test_atualizar_vinculo_altera_papel_e_ativo_e_persiste() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    membro = User(id=uuid4(), name="Bea", email="bea@b2.com", password_hash="h")
    await users.add(membro)
    await CreateMemberUseCase(users, tenants, links, FakeHasher()).execute(
        tenant.id, _input("bea@b2.com", Role.ATENDENTE)
    )
    acting_id = uuid4()

    use_case = UpdateMemberLinkUseCase(users, links)
    detail = await use_case.execute(tenant.id, acting_id, membro.id, Role.SUPERVISOR, False)

    assert detail.role is Role.SUPERVISOR
    assert detail.active is False
    # re-busca no repositorio (nao no objeto que o use case ja tinha em maos)
    # para provar que a mudanca foi PERSISTIDA por update(), nao so mutada em
    # memoria no objeto retornado.
    persistido = await links.get(membro.id, tenant.id)
    assert persistido is not None
    assert persistido.role is Role.SUPERVISOR
    assert persistido.active is False


async def test_atualizar_proprio_vinculo_gera_conflito() -> None:
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant = await _tenant(tenants)
    admin = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="h")
    await users.add(admin)
    await CreateMemberUseCase(users, tenants, links, FakeHasher()).execute(
        tenant.id, _input("ana@b2.com", Role.ADMIN)
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
        tenant.id, _input("bea@b2.com", Role.ATENDENTE)
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


async def test_resetar_senha_recusado_para_vinculo_cruzado_com_outro_tenant() -> None:
    """Defesa em profundidade (item 2): mesmo que o item 1 impeca criar esse
    estado por ESTA rota, um super_admin pode vincular deliberadamente o
    mesmo usuario a dois tenants pelo painel de plataforma. Nesse caso o
    admin de UM dos tenants nao pode resetar a senha GLOBAL desse usuario --
    ele afetaria o outro tenant tambem.
    """
    users = InMemoryUserRepository()
    links = InMemoryUserTenantRepository()
    tenants = InMemoryTenantRepository()
    tenant_a = await _tenant(tenants, slug="tenant_a")
    tenant_b = await _tenant(tenants, slug="tenant_b")
    compartilhado = User(
        id=uuid4(), name="Compartilhado", email="compartilhado@b2.com", password_hash="h:original"
    )
    await users.add(compartilhado)
    await links.add(
        UserTenant(user_id=compartilhado.id, tenant_id=tenant_a.id, role=Role.ATENDENTE)
    )
    await links.add(
        UserTenant(user_id=compartilhado.id, tenant_id=tenant_b.id, role=Role.ATENDENTE)
    )

    use_case = ResetMemberPasswordUseCase(users, links, FakeHasher())
    with pytest.raises(ConflictError):
        await use_case.execute(tenant_a.id, uuid4(), compartilhado.id, "nova-senha-forte")

    # senha global nao mudou
    atual = await users.get_by_id(compartilhado.id)
    assert atual is not None and atual.password_hash == "h:original"


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
