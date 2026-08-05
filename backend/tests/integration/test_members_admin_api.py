from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    DEFAULT_PASSWORD,
    seed_link,
    seed_tenant,
    seed_user,
    token_for,
)

_ENDPOINTS_SOMENTE_ADMIN = (
    ("GET", "/api/membros/gerencia", None),
    ("POST", "/api/membros", {"email": "novo@matriz.com", "role": "atendente"}),
    ("PATCH", "/api/membros/{user_id}", {"role": "supervisor"}),
    ("POST", "/api/membros/{user_id}/senha", {"password": "nova-senha-forte"}),
)


async def _request(
    client: AsyncClient, method: str, path: str, json: dict | None, headers: dict
) -> object:
    if method == "GET":
        return await client.get(path, headers=headers)
    if method == "POST":
        return await client.post(path, json=json, headers=headers)
    if method == "PATCH":
        return await client.patch(path, json=json, headers=headers)
    raise AssertionError(f"metodo nao coberto: {method}")


async def test_matriz_de_autorizacao_nega_papeis_sem_gerenciar_usuarios(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="matriz")
    admin = await seed_user(session, email="admin@matriz.com")
    alvo = await seed_user(session, email="alvo@matriz.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=alvo, tenant=tenant, role=Role.ATENDENTE)

    for role in (Role.SUPERVISOR, Role.ATENDENTE, Role.VISUALIZADOR):
        headers = token_for(admin, tenant_slug=tenant.slug, role=role)
        for method, path_tpl, body in _ENDPOINTS_SOMENTE_ADMIN:
            path = path_tpl.format(user_id=alvo.id)
            response = await _request(client, method, path, body, headers)
            assert response.status_code == 403, f"{role} deveria levar 403 em {method} {path}"


async def test_admin_cria_membro_novo_e_login_funciona(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="criamembro")
    admin = await seed_user(session, email="admin@criamembro.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    created = await client.post(
        "/api/membros",
        json={
            "email": "novo@criamembro.com",
            "role": "atendente",
            "name": "Novo Membro",
            "password": "senha-forte-123",
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "novo@criamembro.com"
    assert body["role"] == "atendente"
    assert body["active"] is True
    assert body["user_active"] is True

    login = await client.post(
        "/api/auth/login",
        json={
            "email": "novo@criamembro.com",
            "password": "senha-forte-123",
            "tenant_slug": "criamembro",
        },
    )
    assert login.status_code == 200
    assert login.json()["role"] == "atendente"


async def test_criar_membro_com_email_ja_vinculado_gera_conflito(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="conflito")
    admin = await seed_user(session, email="admin@conflito.com")
    outro = await seed_user(session, email="outro@conflito.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=outro, tenant=tenant, role=Role.ATENDENTE)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    response = await client.post(
        "/api/membros",
        json={
            "email": "outro@conflito.com",
            "role": "supervisor",
            "name": "Nome Ignorado",
            "password": "senha-de-preenchimento-123",
        },
        headers=headers,
    )
    assert response.status_code == 409


async def test_criar_membro_com_email_novo_sem_senha_e_erro_de_validacao(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="semsenha")
    admin = await seed_user(session, email="admin@semsenha.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    response = await client.post(
        "/api/membros",
        json={"email": "semsenha@semsenha.com", "role": "atendente"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_admin_nao_pode_alterar_o_proprio_vinculo(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="proprio")
    admin = await seed_user(session, email="admin@proprio.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    desativar = await client.patch(
        f"/api/membros/{admin.id}", json={"active": False}, headers=headers
    )
    assert desativar.status_code == 409

    resetar = await client.post(
        f"/api/membros/{admin.id}/senha", json={"password": "outra-senha-forte"}, headers=headers
    )
    assert resetar.status_code == 409


async def test_patch_de_papel_reflete_no_proximo_login(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="reflete")
    admin = await seed_user(session, email="admin@reflete.com")
    membro = await seed_user(session, email="membro@reflete.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=membro, tenant=tenant, role=Role.ATENDENTE)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    patched = await client.patch(
        f"/api/membros/{membro.id}", json={"role": "supervisor"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["role"] == "supervisor"

    login = await client.post(
        "/api/auth/login",
        json={
            "email": "membro@reflete.com",
            "password": DEFAULT_PASSWORD,
            "tenant_slug": "reflete",
        },
    )
    assert login.status_code == 200
    assert login.json()["role"] == "supervisor"


async def test_desativar_vinculo_bloqueia_login_no_tenant(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="desativa")
    admin = await seed_user(session, email="admin@desativa.com")
    membro = await seed_user(session, email="membro@desativa.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=membro, tenant=tenant, role=Role.ATENDENTE)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    login_antes = await client.post(
        "/api/auth/login",
        json={
            "email": "membro@desativa.com",
            "password": DEFAULT_PASSWORD,
            "tenant_slug": "desativa",
        },
    )
    assert login_antes.status_code == 200

    patched = await client.patch(
        f"/api/membros/{membro.id}", json={"active": False}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is False

    login_depois = await client.post(
        "/api/auth/login",
        json={
            "email": "membro@desativa.com",
            "password": DEFAULT_PASSWORD,
            "tenant_slug": "desativa",
        },
    )
    assert login_depois.status_code == 401


async def test_reset_de_senha_pelo_admin_permite_login_com_nova_senha(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="resetapi")
    admin = await seed_user(session, email="admin@resetapi.com")
    membro = await seed_user(session, email="membro@resetapi.com")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=membro, tenant=tenant, role=Role.ATENDENTE)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    reset = await client.post(
        f"/api/membros/{membro.id}/senha",
        json={"password": "senha-nova-do-admin"},
        headers=headers,
    )
    assert reset.status_code == 204

    login = await client.post(
        "/api/auth/login",
        json={
            "email": "membro@resetapi.com",
            "password": "senha-nova-do-admin",
            "tenant_slug": "resetapi",
        },
    )
    assert login.status_code == 200


async def test_admin_nao_consegue_vincular_e_assumir_usuario_de_outro_tenant(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Caminho completo do ataque apontado na revisao: o brief so previa
    'email existente: cria vinculo', mas combinado com o reset de senha
    (escreve na linha GLOBAL do usuario) isso deixaria o admin do tenant A
    vincular a vitima do tenant B a si mesmo e depois assumir a conta dela lá.
    Aqui o teste exercita o fluxo INTEIRO pela API (nao so um PATCH direto
    num user_id estrangeiro, que so testava a metade do problema).
    """
    tenant_a = await seed_tenant(session, slug="ataquea")
    tenant_b = await seed_tenant(session, slug="ataqueb")
    admin_a = await seed_user(session, email="admin@ataquea.com")
    vitima = await seed_user(session, email="vitima@ataqueb.com", name="Vitima")
    await seed_link(session, user=admin_a, tenant=tenant_a, role=Role.ADMIN)
    await seed_link(session, user=vitima, tenant=tenant_b, role=Role.ATENDENTE)
    headers = token_for(admin_a, tenant_slug=tenant_a.slug, role=Role.ADMIN)

    tentativa_de_vinculo = await client.post(
        "/api/membros",
        json={
            "email": "vitima@ataqueb.com",
            "role": "atendente",
            "name": "Nome Do Atacante",
            "password": "senha-do-atacante-123",
        },
        headers=headers,
    )
    assert tentativa_de_vinculo.status_code == 404

    # nao apareceu na listagem do tenant A (nenhum vinculo foi criado)
    listagem = await client.get("/api/membros/gerencia", headers=headers)
    assert "Vitima" not in [m["name"] for m in listagem.json()]

    # a senha e o login da vitima no PROPRIO tenant continuam intocados
    login_vitima = await client.post(
        "/api/auth/login",
        json={
            "email": "vitima@ataqueb.com",
            "password": DEFAULT_PASSWORD,
            "tenant_slug": "ataqueb",
        },
    )
    assert login_vitima.status_code == 200
    assert login_vitima.json()["role"] == "atendente"


async def test_reset_de_senha_recusado_para_vinculo_cruzado_com_outro_tenant(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Defesa em profundidade (item 2): mesmo que o teste anterior prove que
    esta API nao cria mais esse estado, um super_admin pode vincular o mesmo
    usuario a dois tenants deliberadamente pelo painel de plataforma. Esse
    vinculo cruzado e simulado aqui via seed_link direto (nao pela API, que
    ja bloqueia). O admin de qualquer um dos dois tenants nao pode resetar a
    senha GLOBAL desse usuario.
    """
    tenant_a = await seed_tenant(session, slug="cruzadoa")
    tenant_b = await seed_tenant(session, slug="cruzadob")
    admin_a = await seed_user(session, email="admin@cruzadoa.com")
    compartilhado = await seed_user(session, email="compartilhado@cruzado.com")
    await seed_link(session, user=admin_a, tenant=tenant_a, role=Role.ADMIN)
    await seed_link(session, user=compartilhado, tenant=tenant_a, role=Role.ATENDENTE)
    await seed_link(session, user=compartilhado, tenant=tenant_b, role=Role.ATENDENTE)
    headers = token_for(admin_a, tenant_slug=tenant_a.slug, role=Role.ADMIN)

    reset = await client.post(
        f"/api/membros/{compartilhado.id}/senha",
        json={"password": "senha-do-admin-a-123"},
        headers=headers,
    )
    assert reset.status_code == 409

    # login com a senha ORIGINAL continua funcionando nos dois tenants
    for slug in ("cruzadoa", "cruzadob"):
        login = await client.post(
            "/api/auth/login",
            json={
                "email": "compartilhado@cruzado.com",
                "password": DEFAULT_PASSWORD,
                "tenant_slug": slug,
            },
        )
        assert login.status_code == 200


async def test_vincular_email_existente_sem_outro_tenant_continua_funcionando(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Nao quebrar o caso legitimo do brief original: usuario global sem
    nenhum vinculo (ex.: criado pelo super_admin e ainda nao alocado) continua
    vinculavel por um admin de tenant. name/password no corpo (agora
    obrigatorios sempre) sao ignorados -- a conta mantem identidade e senha
    proprias.
    """
    tenant = await seed_tenant(session, slug="livre")
    admin = await seed_user(session, email="admin@livre.com")
    livre = await seed_user(session, email="livre@livre.com", name="Nome Real")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    vinculado = await client.post(
        "/api/membros",
        json={
            "email": "livre@livre.com",
            "role": "atendente",
            "name": "Nome Que Nao Deveria Colar",
            "password": "senha-que-nao-deveria-colar-123",
        },
        headers=headers,
    )
    assert vinculado.status_code == 201
    body = vinculado.json()
    assert body["id"] == str(livre.id)
    assert body["name"] == "Nome Real"

    # a senha original (nao a enviada no corpo do POST) continua valendo
    login = await client.post(
        "/api/auth/login",
        json={"email": "livre@livre.com", "password": DEFAULT_PASSWORD, "tenant_slug": "livre"},
    )
    assert login.status_code == 200


async def test_recusas_de_super_admin_e_de_outro_tenant_sao_indistinguiveis_na_api(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Item 3 da revisao: as duas recusas (email de super_admin, email
    vinculado a outro tenant) tem que devolver a MESMA resposta -- mesmo
    status e mesmo corpo -- para que o admin nao consiga diferencia-las
    testando emails a esmo.
    """
    tenant_a = await seed_tenant(session, slug="indistinguivela")
    tenant_b = await seed_tenant(session, slug="indistinguivelb")
    admin_a = await seed_user(session, email="admin@indistinguivela.com")
    await seed_user(session, email="sa@indistinguivel.com", is_super_admin=True)
    de_outro_tenant = await seed_user(session, email="outro@indistinguivel.com")
    await seed_link(session, user=admin_a, tenant=tenant_a, role=Role.ADMIN)
    await seed_link(session, user=de_outro_tenant, tenant=tenant_b, role=Role.ATENDENTE)
    headers = token_for(admin_a, tenant_slug=tenant_a.slug, role=Role.ADMIN)

    corpo_base = {"role": "atendente", "name": "Preenchimento", "password": "senha-forte-123"}

    resposta_sa = await client.post(
        "/api/membros", json={**corpo_base, "email": "sa@indistinguivel.com"}, headers=headers
    )
    resposta_outro = await client.post(
        "/api/membros", json={**corpo_base, "email": "outro@indistinguivel.com"}, headers=headers
    )

    assert resposta_sa.status_code == 404
    assert resposta_outro.status_code == 404
    assert resposta_sa.json() == resposta_outro.json()

    # o mesmo corpo minimo (sem name/password) tambem da 422 para os dois --
    # nao vira oraculo de "email existe" so por omitir campos.
    minimo_sa = await client.post(
        "/api/membros",
        json={"email": "sa@indistinguivel.com", "role": "atendente"},
        headers=headers,
    )
    minimo_inexistente = await client.post(
        "/api/membros",
        json={"email": "jamais-existiu@indistinguivel.com", "role": "atendente"},
        headers=headers,
    )
    assert minimo_sa.status_code == 422
    assert minimo_inexistente.status_code == 422


async def test_admin_de_um_tenant_nao_alcanca_membro_de_outro(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant_a = await seed_tenant(session, slug="isoladoa")
    tenant_b = await seed_tenant(session, slug="isoladob")
    admin_a = await seed_user(session, email="admin@isoladoa.com")
    membro_b = await seed_user(session, email="membro@isoladob.com")
    await seed_link(session, user=admin_a, tenant=tenant_a, role=Role.ADMIN)
    await seed_link(session, user=membro_b, tenant=tenant_b, role=Role.ATENDENTE)
    headers = token_for(admin_a, tenant_slug=tenant_a.slug, role=Role.ADMIN)

    patched = await client.patch(
        f"/api/membros/{membro_b.id}", json={"role": "supervisor"}, headers=headers
    )
    assert patched.status_code == 404

    reset = await client.post(
        f"/api/membros/{membro_b.id}/senha", json={"password": "outra-senha-forte"}, headers=headers
    )
    assert reset.status_code == 404


async def test_recusas_de_vinculo_inexistente_e_de_outro_tenant_sao_indistinguiveis(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Mesma logica do teste de indistinguibilidade do POST /api/membros, mas
    para as duas rotas que passam por _resolve_target: PATCH e o reset de
    senha. Um user_id que nao existe em lugar nenhum tem que devolver a MESMA
    resposta (status E corpo) que um user_id real mas vinculado so a outro
    tenant -- senao o admin usa o 404 como oraculo para confirmar que um UUID
    estrangeiro e de fato uma conta valida.
    """
    tenant_a = await seed_tenant(session, slug="resolvea")
    tenant_b = await seed_tenant(session, slug="resolveb")
    admin_a = await seed_user(session, email="admin@resolvea.com")
    de_outro_tenant = await seed_user(session, email="outro@resolve.com")
    await seed_link(session, user=admin_a, tenant=tenant_a, role=Role.ADMIN)
    await seed_link(session, user=de_outro_tenant, tenant=tenant_b, role=Role.ATENDENTE)
    headers = token_for(admin_a, tenant_slug=tenant_a.slug, role=Role.ADMIN)
    jamais_existiu = uuid4()

    patch_inexistente = await client.patch(
        f"/api/membros/{jamais_existiu}", json={"role": "supervisor"}, headers=headers
    )
    patch_outro_tenant = await client.patch(
        f"/api/membros/{de_outro_tenant.id}", json={"role": "supervisor"}, headers=headers
    )
    assert patch_inexistente.status_code == 404
    assert patch_outro_tenant.status_code == 404
    assert patch_inexistente.json() == patch_outro_tenant.json()

    senha_inexistente = await client.post(
        f"/api/membros/{jamais_existiu}/senha",
        json={"password": "outra-senha-forte"},
        headers=headers,
    )
    senha_outro_tenant = await client.post(
        f"/api/membros/{de_outro_tenant.id}/senha",
        json={"password": "outra-senha-forte"},
        headers=headers,
    )
    assert senha_inexistente.status_code == 404
    assert senha_outro_tenant.status_code == 404
    assert senha_inexistente.json() == senha_outro_tenant.json()


async def test_listagem_gerencial_traz_email_e_estado_do_usuario(
    client: AsyncClient, session: AsyncSession
) -> None:
    tenant = await seed_tenant(session, slug="gerencia")
    admin = await seed_user(session, email="admin@gerencia.com", name="Ana Admin")
    membro = await seed_user(session, email="membro@gerencia.com", name="Bea Membro")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=membro, tenant=tenant, role=Role.ATENDENTE)
    headers = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)

    response = await client.get("/api/membros/gerencia", headers=headers)
    assert response.status_code == 200
    por_nome = {m["name"]: m for m in response.json()}
    assert por_nome["Ana Admin"]["email"] == "admin@gerencia.com"
    assert por_nome["Bea Membro"]["role"] == "atendente"
    assert por_nome["Bea Membro"]["user_active"] is True
    assert por_nome["Bea Membro"]["active"] is True
