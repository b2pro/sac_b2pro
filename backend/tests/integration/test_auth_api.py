from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import DEFAULT_PASSWORD, seed_link, seed_tenant, seed_user


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_login_completo(client: AsyncClient, session: AsyncSession) -> None:
    user = await seed_user(session, email="ana@b2.com")
    tenant = await seed_tenant(session, slug="b2pro")
    await seed_link(session, user=user, tenant=tenant)

    response = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": DEFAULT_PASSWORD, "tenant_slug": "b2pro"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    assert body["user"]["email"] == "ana@b2.com"

    refreshed = await client.post(
        "/api/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


async def test_login_com_senha_errada_retorna_401_padronizado(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await seed_user(session, email="ana@b2.com")
    tenant = await seed_tenant(session, slug="b2pro")
    await seed_link(session, user=user, tenant=tenant)

    response = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": "errada", "tenant_slug": "b2pro"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["message"] == "credenciais invalidas"


async def test_rate_limit_no_login(client: AsyncClient, session: AsyncSession) -> None:
    await seed_user(session, email="ana@b2.com")
    payload = {"email": "ana@b2.com", "password": "errada", "tenant_slug": "b2pro"}

    for _ in range(5):
        await client.post("/api/auth/login", json=payload)
    response = await client.post("/api/auth/login", json=payload)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
