from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.helpers import seed_user, token_for


async def test_crud_de_tenants_pelo_painel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    headers = token_for(sa)

    created = await client.post(
        "/api/platform/tenants",
        json={"slug": "b2pro", "name": "B2PRO", "modules": {"tickets": True}},
        headers=headers,
    )
    assert created.status_code == 201
    tenant = created.json()
    assert tenant["slug"] == "b2pro"

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 't_b2pro'")
        )
        assert result.scalar() == 1

    listed = await client.get("/api/platform/tenants", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    status = await client.patch(
        f"/api/platform/tenants/{tenant['id']}/status",
        json={"status": "suspensa"},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "suspensa"

    modules = await client.put(
        f"/api/platform/tenants/{tenant['id']}/modules",
        json={"modules": {"tickets": False, "cadastros": True}},
        headers=headers,
    )
    assert modules.status_code == 200
    assert modules.json()["modules"] == {"tickets": False, "cadastros": True}


async def test_slug_duplicado_retorna_409(client: AsyncClient, session: AsyncSession) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    headers = token_for(sa)
    payload = {"slug": "b2pro", "name": "B2PRO", "modules": {}}

    assert (
        await client.post("/api/platform/tenants", json=payload, headers=headers)
    ).status_code == 201
    assert (
        await client.post("/api/platform/tenants", json=payload, headers=headers)
    ).status_code == 409


async def test_nao_super_admin_recebe_403(client: AsyncClient, session: AsyncSession) -> None:
    comum = await seed_user(session, email="comum@b2.com")
    response = await client.get("/api/platform/tenants", headers=token_for(comum))
    assert response.status_code == 403
