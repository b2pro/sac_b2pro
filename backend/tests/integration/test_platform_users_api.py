from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import (
    DEFAULT_PASSWORD,
    seed_link,
    seed_tenant,
    seed_user,
    token_for,
)


async def test_fluxo_de_usuarios_e_vinculos(client: AsyncClient, session: AsyncSession) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    tenant = await seed_tenant(session, slug="b2pro")
    headers = token_for(sa)

    created = await client.post(
        "/api/platform/users",
        json={"name": "Ana", "email": "ana@b2.com", "password": "senha-forte-123"},
        headers=headers,
    )
    assert created.status_code == 201
    user = created.json()

    listed = await client.get("/api/platform/users", headers=headers)
    assert listed.status_code == 200
    assert {u["email"] for u in listed.json()} == {"ana@b2.com", "sa@b2.com"}

    linked = await client.post(
        f"/api/platform/tenants/{tenant.id}/links",
        json={"user_id": user["id"], "role": "atendente"},
        headers=headers,
    )
    assert linked.status_code == 201
    assert linked.json()["role"] == "atendente"

    links = await client.get(f"/api/platform/tenants/{tenant.id}/links", headers=headers)
    assert links.status_code == 200 and len(links.json()) == 1

    login = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": "senha-forte-123", "tenant_slug": "b2pro"},
    )
    assert login.status_code == 200 and login.json()["role"] == "atendente"

    unlinked = await client.delete(
        f"/api/platform/tenants/{tenant.id}/links/{user['id']}", headers=headers
    )
    assert unlinked.status_code == 204

    deactivated = await client.patch(
        f"/api/platform/users/{user['id']}/active", json={"active": False}, headers=headers
    )
    assert deactivated.status_code == 200 and deactivated.json()["active"] is False

    reset = await client.post(
        f"/api/platform/users/{user['id']}/password",
        json={"password": "outra-senha-forte"},
        headers=headers,
    )
    assert reset.status_code == 204


async def test_criacao_de_usuario_exige_super_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    comum = await seed_user(session, email="comum@b2.com")
    response = await client.post(
        "/api/platform/users",
        json={"name": "X", "email": "x@b2.com", "password": DEFAULT_PASSWORD},
        headers=token_for(comum),
    )
    assert response.status_code == 403


async def test_reset_de_senha_derruba_a_sessao_ja_emitida(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Fim a fim do versionamento de credencial: um refresh token roubado tem de
    morrer no reset de senha, senao a contencao do incidente nao contem nada -
    o token valeria por todo o TTL de 7 dias."""
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    ana = await seed_user(session, email="ana@b2.com")
    tenant = await seed_tenant(session, slug="b2pro")
    await seed_link(session, user=ana, tenant=tenant)

    login = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": DEFAULT_PASSWORD, "tenant_slug": "b2pro"},
    )
    assert login.status_code == 200
    roubado = login.json()["refresh_token"]

    antes = await client.post("/api/auth/refresh", json={"refresh_token": roubado})
    assert antes.status_code == 200

    reset = await client.post(
        f"/api/platform/users/{ana.id}/password",
        json={"password": "outra-senha-forte-123"},
        headers=token_for(sa),
    )
    assert reset.status_code == 204

    depois = await client.post("/api/auth/refresh", json={"refresh_token": roubado})
    assert depois.status_code == 401

    novo = await client.post(
        "/api/auth/login",
        json={
            "email": "ana@b2.com",
            "password": "outra-senha-forte-123",
            "tenant_slug": "b2pro",
        },
    )
    assert novo.status_code == 200
    revalidado = await client.post(
        "/api/auth/refresh", json={"refresh_token": novo.json()["refresh_token"]}
    )
    assert revalidado.status_code == 200
