import asyncio

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


async def _setup_full(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    users = {}
    for role in (Role.ADMIN, Role.SUPERVISOR, Role.ATENDENTE, Role.VISUALIZADOR):
        user = await seed_user(session, email=f"{role.value}@{slug}.com", name=role.value.title())
        await seed_link(session, user=user, tenant=tenant, role=role)
        users[role] = (user, token_for(user, tenant_slug=tenant.slug, role=role))
    return tenant, users


async def _criar_ticket(client: AsyncClient, headers: dict[str, str]) -> dict:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets", json={"brand_id": marcas[0]["id"], "priority": "media"}, headers=headers
    )
    assert res.status_code == 201
    return res.json()


async def test_atendente_so_ve_e_opera_os_seus(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flow1")
    _, admin_headers = users[Role.ADMIN]
    _, atendente_headers = users[Role.ATENDENTE]

    do_admin = await _criar_ticket(client, admin_headers)
    do_atendente = await _criar_ticket(client, atendente_headers)

    lista = (await client.get("/api/tickets", headers=atendente_headers)).json()
    assert lista["total"] == 1
    assert lista["items"][0]["id"] == do_atendente["id"]

    res = await client.get(f"/api/tickets/{do_admin['id']}", headers=atendente_headers)
    assert res.status_code == 404

    res = await client.post(
        f"/api/tickets/{do_admin['id']}/enviar-analise", headers=atendente_headers
    )
    assert res.status_code == 404

    lista_admin = (await client.get("/api/tickets", headers=admin_headers)).json()
    assert lista_admin["total"] == 2


async def test_papeis_decisao_e_logistica(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flow2")
    admin, admin_headers = users[Role.ADMIN]
    _, atendente_headers = users[Role.ATENDENTE]
    _, viewer_headers = users[Role.VISUALIZADOR]

    defeitos = (await client.get("/api/cadastros/defeitos", headers=admin_headers)).json()
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "P Flow", "sku": "SKU-FLOW2"},
            headers=admin_headers,
        )
    ).json()
    marcas = (await client.get("/api/cadastros/marcas", headers=admin_headers)).json()
    ticket = (
        await client.post(
            "/api/tickets",
            json={
                "brand_id": marcas[0]["id"],
                "priority": "alta",
                "customer": {"name": "C Flow", "document": "39053344705"},
                "description": "quebrou a ponta",
                "items": [{"product_id": produto["id"], "defect_type_id": defeitos[0]["id"]}],
            },
            headers=atendente_headers,
        )
    ).json()
    tid = ticket["id"]

    # atendente envia o proprio ticket para analise
    res = await client.post(f"/api/tickets/{tid}/enviar-analise", headers=atendente_headers)
    assert res.status_code == 200

    # atendente NAO decide (403), visualizador NAO decide (403)
    res = await client.post(f"/api/tickets/{tid}/aprovar", json={}, headers=atendente_headers)
    assert res.status_code == 403
    res = await client.post(f"/api/tickets/{tid}/aprovar", json={}, headers=viewer_headers)
    assert res.status_code == 403

    # admin aprova; atendente opera logistica do proprio ticket
    res = await client.post(f"/api/tickets/{tid}/aprovar", json={}, headers=admin_headers)
    assert res.status_code == 200
    res = await client.post(
        f"/api/tickets/{tid}/reversos", json={"code": "BRX"}, headers=atendente_headers
    )
    assert res.status_code == 201

    # visualizador nao comenta nem opera
    res = await client.post(
        f"/api/tickets/{tid}/comentarios", json={"body": "oi"}, headers=viewer_headers
    )
    assert res.status_code == 403
    res = await client.post(f"/api/tickets/{tid}/produto-recebido", headers=viewer_headers)
    assert res.status_code == 403

    # visualizador le o detalhe
    res = await client.get(f"/api/tickets/{tid}", headers=viewer_headers)
    assert res.status_code == 200


async def test_isolamento_entre_tenants(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users_a = await _setup_full(session, engine, "flowa")
    _, users_b = await _setup_full(session, engine, "flowb")
    _, headers_a = users_a[Role.ADMIN]
    _, headers_b = users_b[Role.ADMIN]

    ticket_a = await _criar_ticket(client, headers_a)

    lista_b = (await client.get("/api/tickets", headers=headers_b)).json()
    assert lista_b["total"] == 0
    res = await client.get(f"/api/tickets/{ticket_a['id']}", headers=headers_b)
    assert res.status_code == 404

    ticket_b = await _criar_ticket(client, headers_b)
    assert ticket_b["number"] == 1  # sequence propria por tenant


async def test_numeracao_concorrente_unica_e_crescente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flowseq")
    _, headers = users[Role.ADMIN]
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()

    async def criar() -> int:
        res = await client.post(
            "/api/tickets",
            json={"brand_id": marcas[0]["id"], "priority": "media"},
            headers=headers,
        )
        assert res.status_code == 201
        return int(res.json()["number"])

    numbers = await asyncio.gather(*(criar() for _ in range(5)))
    assert len(set(numbers)) == 5
    assert sorted(numbers) == list(range(1, 6))


async def test_historico_do_cliente_via_customer_id(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flowcli")
    _, headers = users[Role.ADMIN]
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    primeiro = (
        await client.post(
            "/api/tickets",
            json={
                "brand_id": marcas[0]["id"],
                "priority": "media",
                "customer": {"name": "Historico", "document": "39053344705"},
            },
            headers=headers,
        )
    ).json()
    await _criar_ticket(client, headers)
    res = await client.get(
        "/api/tickets", params={"customer_id": primeiro["customer_id"]}, headers=headers
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == primeiro["id"]
