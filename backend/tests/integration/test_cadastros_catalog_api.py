from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def test_crud_de_marcas_pelo_admin(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="admin@b2.com")
    await seed_provisioned_tenant(session, engine, slug="alfa")
    headers = token_for(user, tenant_slug="alfa", role=Role.ADMIN)

    created = await client.post(
        "/api/cadastros/marcas", json={"name": "MARCA-NOVA"}, headers=headers
    )
    assert created.status_code == 201
    marca = created.json()

    listed = await client.get("/api/cadastros/marcas", headers=headers)
    assert listed.status_code == 200
    assert any(i["name"] == "MARCA-NOVA" for i in listed.json())

    updated = await client.put(
        f"/api/cadastros/marcas/{marca['id']}",
        json={"name": "MARCA-RENOMEADA", "description": "desc"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "MARCA-RENOMEADA"

    disabled = await client.patch(
        f"/api/cadastros/marcas/{marca['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False

    inativos = await client.get("/api/cadastros/marcas?active=false", headers=headers)
    assert any(i["name"] == "MARCA-RENOMEADA" for i in inativos.json())

    duplicada = await client.post(
        "/api/cadastros/marcas", json={"name": "MARCA-RENOMEADA"}, headers=headers
    )
    assert duplicada.status_code == 409


async def test_permissoes_por_papel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="user@b2.com")
    await seed_provisioned_tenant(session, engine, slug="beta")
    visualizador = token_for(user, tenant_slug="beta", role=Role.VISUALIZADOR)
    atendente = token_for(user, tenant_slug="beta", role=Role.ATENDENTE)

    assert (await client.get("/api/cadastros/defeitos", headers=visualizador)).status_code == 200
    assert (
        await client.post("/api/cadastros/defeitos", json={"name": "X-VIS"}, headers=visualizador)
    ).status_code == 403

    criado = await client.post("/api/cadastros/defeitos", json={"name": "X-ATD"}, headers=atendente)
    assert criado.status_code == 201
    assert (
        await client.put(
            f"/api/cadastros/defeitos/{criado.json()['id']}",
            json={"name": "X-ATD-2"},
            headers=atendente,
        )
    ).status_code == 403


async def test_super_admin_sem_papel_de_tenant_recebe_403(
    client: AsyncClient, session: AsyncSession
) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    response = await client.get("/api/cadastros/marcas", headers=token_for(sa))
    assert response.status_code == 403


async def test_sem_token_recebe_401(client: AsyncClient) -> None:
    assert (await client.get("/api/cadastros/marcas")).status_code == 401


async def test_isolamento_entre_tenants(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="iso@b2.com")
    await seed_provisioned_tenant(session, engine, slug="iso_a")
    await seed_provisioned_tenant(session, engine, slug="iso_b")
    headers_a = token_for(user, tenant_slug="iso_a", role=Role.ADMIN)
    headers_b = token_for(user, tenant_slug="iso_b", role=Role.ADMIN)

    created = await client.post(
        "/api/cadastros/canais", json={"name": "CANAL-SO-DO-A"}, headers=headers_a
    )
    assert created.status_code == 201

    no_a = await client.get("/api/cadastros/canais", headers=headers_a)
    no_b = await client.get("/api/cadastros/canais", headers=headers_b)
    assert any(i["name"] == "CANAL-SO-DO-A" for i in no_a.json())
    assert not any(i["name"] == "CANAL-SO-DO-A" for i in no_b.json())
