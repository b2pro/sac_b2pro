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
        json={"email": "outro@conflito.com", "role": "supervisor"},
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
