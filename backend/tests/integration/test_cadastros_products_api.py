from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def test_crud_de_produtos_e_conflito_de_sku(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="prod@b2.com")
    await seed_provisioned_tenant(session, engine, slug="prod_a")
    headers = token_for(user, tenant_slug="prod_a", role=Role.SUPERVISOR)

    created = await client.post(
        "/api/cadastros/produtos",
        json={"name": "Alicate", "sku": "PLN-10-7", "segment": "Manicure"},
        headers=headers,
    )
    assert created.status_code == 201
    produto = created.json()
    assert produto["photo_key"] is None

    duplicado = await client.post(
        "/api/cadastros/produtos",
        json={"name": "Outro", "sku": "PLN-10-7"},
        headers=headers,
    )
    assert duplicado.status_code == 409

    busca = await client.get("/api/cadastros/produtos?search=pln-10", headers=headers)
    assert busca.json()["total"] == 1

    updated = await client.put(
        f"/api/cadastros/produtos/{produto['id']}",
        json={"name": "Alicate Pro", "sku": "PLN-10-7", "segment": "Manicure"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Alicate Pro"

    disabled = await client.patch(
        f"/api/cadastros/produtos/{produto['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False


async def test_get_produto_por_id(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="prod-get@b2.com")
    await seed_provisioned_tenant(session, engine, slug="prod_get")
    headers = token_for(user, tenant_slug="prod_get", role=Role.SUPERVISOR)

    created = await client.post(
        "/api/cadastros/produtos",
        json={"name": "Lixa", "sku": "SKU-GET-1", "segment": "Manicure"},
        headers=headers,
    )
    assert created.status_code == 201
    produto = created.json()

    found = await client.get(f"/api/cadastros/produtos/{produto['id']}", headers=headers)
    assert found.status_code == 200
    assert found.json() == produto

    missing = await client.get(f"/api/cadastros/produtos/{uuid4()}", headers=headers)
    assert missing.status_code == 404

    disabled = await client.patch(
        f"/api/cadastros/produtos/{produto['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200

    inativo = await client.get(f"/api/cadastros/produtos/{produto['id']}", headers=headers)
    assert inativo.status_code == 200
    assert inativo.json()["active"] is False
    assert inativo.json()["name"] == "Lixa"


async def test_get_produto_por_id_sem_token_recebe_401(client: AsyncClient) -> None:
    assert (await client.get(f"/api/cadastros/produtos/{uuid4()}")).status_code == 401


async def test_atendente_cria_mas_nao_edita_produto(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="atd@b2.com")
    await seed_provisioned_tenant(session, engine, slug="prod_b")
    headers = token_for(user, tenant_slug="prod_b", role=Role.ATENDENTE)

    created = await client.post(
        "/api/cadastros/produtos", json={"name": "A", "sku": "SKU-ATD"}, headers=headers
    )
    assert created.status_code == 201
    assert (
        await client.put(
            f"/api/cadastros/produtos/{created.json()['id']}",
            json={"name": "B", "sku": "SKU-ATD"},
            headers=headers,
        )
    ).status_code == 403
