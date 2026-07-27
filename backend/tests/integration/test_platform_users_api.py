from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import DEFAULT_PASSWORD, seed_tenant, seed_user, token_for


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
