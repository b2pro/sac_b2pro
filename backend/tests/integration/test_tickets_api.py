from dataclasses import dataclass
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.entities import Tenant, User
from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

VALID_CPF = "39053344705"


@dataclass(frozen=True)
class _Env:
    tenant: Tenant
    admin: User
    headers: dict[str, str]


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str) -> _Env:
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin Um")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return _Env(
        tenant=tenant,
        admin=admin,
        headers=token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN),
    )


async def _brand_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/marcas", headers=headers)
    assert res.status_code == 200
    return str(res.json()[0]["id"])


async def _defect_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/defeitos", headers=headers)
    return str(res.json()[0]["id"])


async def _product_id(client: AsyncClient, headers: dict[str, str], sku: str) -> str:
    res = await client.post(
        "/api/cadastros/produtos",
        json={"name": f"Produto {sku}", "sku": sku},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_criacao_parcial_e_detalhe(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi1")
    headers = env.headers
    brand = await _brand_id(client, headers)
    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=headers
    )
    assert res.status_code == 201
    body = res.json()
    assert body["number"] >= 1
    assert body["status"] == "aberto"
    assert body["sla"] == "no_prazo"

    detail = await client.get(f"/api/tickets/{body['id']}", headers=headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["ticket"]["id"] == body["id"]
    assert data["attendant_name"] == "Admin Um"
    assert data["items"] == []
    assert data["timeline"][0]["type"] == "criacao"


async def test_criacao_completa_com_cliente_inline_e_itens(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi2")
    headers = env.headers
    brand = await _brand_id(client, headers)
    defect = await _defect_id(client, headers)
    product = await _product_id(client, headers, "SKU-T2")
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": brand,
            "priority": "urgente",
            "customer": {"name": "Joana", "document": VALID_CPF},
            "description": "chegou quebrado",
            "items": [{"product_id": product, "defect_type_id": defect, "quantity": 2}],
        },
        headers=headers,
    )
    assert res.status_code == 201
    ticket = res.json()
    assert ticket["customer_id"] is not None

    detail = await client.get(f"/api/tickets/{ticket['id']}", headers=headers)
    data = detail.json()
    assert data["customer"]["document"] == VALID_CPF
    assert data["items"][0]["quantity"] == 2
    assert data["items"][0]["product_name"] == "Produto SKU-T2"

    clientes = await client.get(
        "/api/cadastros/clientes", params={"search": VALID_CPF}, headers=headers
    )
    assert clientes.json()["total"] == 1


async def test_fk_invalida_da_422_nao_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi3")
    headers = env.headers
    res = await client.post(
        "/api/tickets",
        json={"brand_id": str(uuid4()), "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "brand_id"


async def test_lista_com_filtros_e_paginacao(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi4")
    headers = env.headers
    brand = await _brand_id(client, headers)
    for priority in ("media", "urgente", "baixa"):
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": priority}, headers=headers
        )
    res = await client.get("/api/tickets", headers=headers)
    body = res.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["items"][0]["unread"] is False  # criador marcou como lido

    res = await client.get("/api/tickets", params={"priority": "urgente"}, headers=headers)
    assert res.json()["total"] == 1

    res = await client.get("/api/tickets", params={"page": 1, "per_page": 2}, headers=headers)
    assert len(res.json()["items"]) == 2

    res = await client.get(
        "/api/tickets", params={"sort": "number", "order": "asc"}, headers=headers
    )
    numbers = [item["number"] for item in res.json()["items"]]
    assert numbers == sorted(numbers)


async def test_lista_filtra_por_atendente_e_busca_livre(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi9")
    headers = env.headers
    brand = await _brand_id(client, headers)
    outro_atendente = await seed_user(session, email="atendente@tapi9.com", name="Atendente Dois")
    await seed_link(session, user=outro_atendente, tenant=env.tenant, role=Role.ATENDENTE)

    res_admin = await client.post(
        "/api/tickets",
        json={"brand_id": brand, "priority": "media", "order_code": "PED-00099"},
        headers=headers,
    )
    assert res_admin.status_code == 201
    res_outro = await client.post(
        "/api/tickets",
        json={
            "brand_id": brand,
            "priority": "media",
            "attendant_user_id": str(outro_atendente.id),
            "order_code": "PED-00050",
        },
        headers=headers,
    )
    assert res_outro.status_code == 201

    res = await client.get(
        "/api/tickets", params={"atendente_id": str(outro_atendente.id)}, headers=headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == res_outro.json()["id"]

    res = await client.get("/api/tickets", params={"q": "00050"}, headers=headers)
    assert res.json()["total"] == 1

    res = await client.get("/api/tickets", params={"q": "   "}, headers=headers)
    assert res.json()["total"] == 2


async def test_update_recalcula_sla_e_edita_itens(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi5")
    headers = env.headers
    brand = await _brand_id(client, headers)
    defect = await _defect_id(client, headers)
    product = await _product_id(client, headers, "SKU-T5")
    created = (
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": "baixa"}, headers=headers
        )
    ).json()
    ticket_id = created["id"]

    res = await client.put(
        f"/api/tickets/{ticket_id}",
        json={"brand_id": brand, "priority": "urgente", "description": "editado"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["due_at"] < created["due_at"]

    res = await client.post(
        f"/api/tickets/{ticket_id}/itens",
        json={"product_id": product, "defect_type_id": defect},
        headers=headers,
    )
    assert res.status_code == 201
    item_id = res.json()["id"]

    res = await client.put(
        f"/api/tickets/{ticket_id}/itens/{item_id}",
        json={"product_id": product, "defect_type_id": defect, "quantity": 3},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["quantity"] == 3

    res = await client.delete(f"/api/tickets/{ticket_id}/itens/{item_id}", headers=headers)
    assert res.status_code == 204


async def test_visualizador_nao_cria_mas_lista(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi6")
    tenant = env.tenant
    viewer = await seed_user(session, email="viewer@tapi6.com")
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    viewer_headers = token_for(viewer, tenant_slug=tenant.slug, role=Role.VISUALIZADOR)
    brand = await _brand_id(client, env.headers)
    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=viewer_headers
    )
    assert res.status_code == 403
    res = await client.get("/api/tickets", headers=viewer_headers)
    assert res.status_code == 200


async def test_sem_token_401(client: AsyncClient) -> None:
    res = await client.get("/api/tickets")
    assert res.status_code == 401
