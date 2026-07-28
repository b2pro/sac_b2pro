from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def _admin_headers(session: AsyncSession, engine: AsyncEngine, slug: str) -> dict[str, str]:
    user = await seed_user(session, email=f"admin-{slug}@b2.com")
    await seed_provisioned_tenant(session, engine, slug=slug)
    return token_for(user, tenant_slug=slug, role=Role.ADMIN)


async def test_crud_de_clientes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_a")

    created = await client.post(
        "/api/cadastros/clientes",
        json={
            "name": "Ana Silva",
            "document": "529.982.247-25",
            "phone": "(54) 99982-3566",
            "cep": "95010-000",
            "state": "rs",
        },
        headers=headers,
    )
    assert created.status_code == 201
    cliente = created.json()
    assert cliente["document"] == "52998224725"
    assert cliente["state"] == "RS"

    busca = await client.get("/api/cadastros/clientes?search=529.982", headers=headers)
    assert busca.status_code == 200
    assert busca.json()["total"] == 1

    updated = await client.put(
        f"/api/cadastros/clientes/{cliente['id']}",
        json={"name": "Ana Maria", "document": "529.982.247-25"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Ana Maria"

    disabled = await client.patch(
        f"/api/cadastros/clientes/{cliente['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False


async def test_documento_invalido_422_e_duplicado_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_b")
    payload = {"name": "Ana", "document": "529.982.247-25"}

    invalido = await client.post(
        "/api/cadastros/clientes",
        json={"name": "Ana", "document": "123.456.789-00"},
        headers=headers,
    )
    assert invalido.status_code == 422
    assert invalido.json()["code"] == "validation_error"

    assert (
        await client.post("/api/cadastros/clientes", json=payload, headers=headers)
    ).status_code == 201
    duplicado = await client.post("/api/cadastros/clientes", json=payload, headers=headers)
    assert duplicado.status_code == 409


async def test_paginacao_de_clientes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_c")
    documentos = ["529.982.247-25", "153.509.460-56", "11.222.333/0001-81"]
    for i, doc in enumerate(documentos):
        response = await client.post(
            "/api/cadastros/clientes",
            json={"name": f"Cliente {i}", "document": doc},
            headers=headers,
        )
        assert response.status_code == 201

    pagina = await client.get("/api/cadastros/clientes?page=1&per_page=2", headers=headers)
    body = pagina.json()
    assert body["total"] == 3 and len(body["items"]) == 2 and body["per_page"] == 2


async def test_paginacao_de_clientes_com_valores_fora_do_intervalo_e_clampada(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_d")

    pagina = await client.get("/api/cadastros/clientes?page=0&per_page=500", headers=headers)
    assert pagina.status_code == 200
    body = pagina.json()
    assert body["page"] == 1
    assert body["per_page"] == 100
