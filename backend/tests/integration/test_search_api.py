from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.entities import Tenant
from sac.domain.permissions import Role
from tests.integration.helpers import seed_link, seed_provisioned_tenant, seed_user, token_for

# CPFs validos ja usados em outros testes de integracao (validate_document
# aceita), so reaproveitados aqui para nao inventar digito verificador novo.
CPF_A = "39053344705"
CPF_B = "52998224725"


async def _setup_trio(
    session: AsyncSession, engine: AsyncEngine, slug: str
) -> tuple[dict[str, str], dict[str, str], dict[str, str], Tenant]:
    """Provisiona um tenant com admin (ve tudo) e dois atendentes distintos.

    Atendente tem CRIAR_LISTAR_CADASTROS e CRIAR_TICKET (permissions.py),
    entao ambos os papeis abaixo bastam para semear cadastros e tickets sem
    precisar de um terceiro papel so para isso.
    """
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    atendente_a = await seed_user(session, email=f"a@{slug}.com", name="Atendente A")
    await seed_link(session, user=atendente_a, tenant=tenant, role=Role.ATENDENTE)
    atendente_b = await seed_user(session, email=f"b@{slug}.com", name="Atendente B")
    await seed_link(session, user=atendente_b, tenant=tenant, role=Role.ATENDENTE)
    headers_admin = token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)
    headers_a = token_for(atendente_a, tenant_slug=tenant.slug, role=Role.ATENDENTE)
    headers_b = token_for(atendente_b, tenant_slug=tenant.slug, role=Role.ATENDENTE)
    return headers_admin, headers_a, headers_b, tenant


async def _criar_cliente(
    client: AsyncClient, headers: dict[str, str], *, name: str, document: str, email: str
) -> str:
    res = await client.post(
        "/api/cadastros/clientes",
        json={"name": name, "document": document, "email": email},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def _criar_produto(
    client: AsyncClient, headers: dict[str, str], *, name: str, sku: str
) -> str:
    res = await client.post(
        "/api/cadastros/produtos", json={"name": name, "sku": sku}, headers=headers
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def _criar_ticket(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    order_code: str | None = None,
    customer_id: str | None = None,
) -> dict[str, object]:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    body: dict[str, object] = {"brand_id": marcas[0]["id"], "priority": "media"}
    if order_code is not None:
        body["order_code"] = order_code
    if customer_id is not None:
        body["customer_id"] = customer_id
    res = await client.post("/api/tickets", json=body, headers=headers)
    assert res.status_code == 201
    return dict(res.json())


async def test_busca_encontra_cliente_por_documento_e_email(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscacli")
    customer_id = await _criar_cliente(
        client,
        headers_admin,
        name="Fulano Trigrama",
        document=CPF_A,
        email="fulano.trigrama@example.com",
    )

    # fragmento do documento com pontuacao: prova que o termo digitado com
    # mascara (ponto/traco) e normalizado para digitos antes do ilike.
    res = await client.get("/api/busca", params={"q": "390.533"}, headers=headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert [c["id"] for c in body["clientes"]] == [customer_id]
    assert body["tickets"] == []
    assert body["produtos"] == []

    res = await client.get("/api/busca", params={"q": "trigrama@example"}, headers=headers_admin)
    body = res.json()
    assert [c["id"] for c in body["clientes"]] == [customer_id]


async def test_busca_encontra_produto_por_sku(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscaprod")
    product_id = await _criar_produto(
        client, headers_admin, name="Produto Trigrama", sku="SKU-TRIGRAMA-001"
    )

    res = await client.get("/api/busca", params={"q": "TRIGRAMA-001"}, headers=headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert [p["id"] for p in body["produtos"]] == [product_id]
    assert body["clientes"] == []
    assert body["tickets"] == []


async def test_busca_de_ticket_por_order_code_respeita_escopo_do_atendente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, headers_a, headers_b, _ = await _setup_trio(session, engine, "buscatick")
    ticket = await _criar_ticket(client, headers_b, order_code="PED-TRIGRAMA-777")

    # admin (VER_TODOS_TICKETS) enxerga o ticket de B
    res = await client.get("/api/busca", params={"q": "TRIGRAMA-777"}, headers=headers_admin)
    body = res.json()
    assert [t["id"] for t in body["tickets"]] == [ticket["id"]]
    assert body["tickets"][0]["number"] == ticket["number"]
    assert body["tickets"][0]["status"] == "aberto"

    # atendente B (dono do ticket) tambem enxerga
    res = await client.get("/api/busca", params={"q": "TRIGRAMA-777"}, headers=headers_b)
    body = res.json()
    assert [t["id"] for t in body["tickets"]] == [ticket["id"]]

    # atendente A nao enxerga o ticket alheio no grupo de tickets
    res = await client.get("/api/busca", params={"q": "TRIGRAMA-777"}, headers=headers_a)
    body = res.json()
    assert body["tickets"] == []


async def test_busca_de_ticket_por_numero_prefixo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscanum")
    # 9 tickets descartaveis antes: garante numero de 2+ digitos, senao o
    # termo de busca teria 1 char so e seria recusado pelo MIN_TERM_LENGTH
    # antes mesmo de chegar ao repositorio.
    for _ in range(9):
        await _criar_ticket(client, headers_admin)
    ticket = await _criar_ticket(client, headers_admin)
    numero = str(ticket["number"])
    assert len(numero) >= 2

    res = await client.get("/api/busca", params={"q": numero}, headers=headers_admin)
    body = res.json()
    assert ticket["id"] in [t["id"] for t in body["tickets"]]

    # com # na frente (como o usuario ve o numero na UI) tambem casa
    res = await client.get("/api/busca", params={"q": f"#{numero}"}, headers=headers_admin)
    body = res.json()
    assert ticket["id"] in [t["id"] for t in body["tickets"]]


async def test_atendente_ve_clientes_e_produtos_mesmo_sem_ver_ticket_alheio(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, headers_a, headers_b, _ = await _setup_trio(session, engine, "buscaesco")
    customer_id = await _criar_cliente(
        client, headers_admin, name="Cliente Visivel", document=CPF_A, email="visivel@example.com"
    )
    product_id = await _criar_produto(
        client, headers_admin, name="Produto Visivel", sku="SKU-VISIVEL-1"
    )
    await _criar_ticket(client, headers_b, order_code="PED-ESCOPO-999")

    res = await client.get("/api/busca", params={"q": "Visivel"}, headers=headers_a)
    body = res.json()
    assert customer_id in [c["id"] for c in body["clientes"]]

    res = await client.get("/api/busca", params={"q": "SKU-VISIVEL"}, headers=headers_a)
    body = res.json()
    assert product_id in [p["id"] for p in body["produtos"]]


async def test_busca_escapa_percent_no_termo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscaesc")
    literal_id = await _criar_cliente(
        client,
        headers_admin,
        name="Malha 100% algodao",
        document=CPF_A,
        email="malha100@example.com",
    )
    isca_id = await _criar_cliente(
        client,
        headers_admin,
        name="Malha 1000 fios trama",
        document=CPF_B,
        email="malha1000@example.com",
    )

    res = await client.get("/api/busca", params={"q": "100%"}, headers=headers_admin)
    body = res.json()
    ids = [c["id"] for c in body["clientes"]]
    assert literal_id in ids
    assert isca_id not in ids


async def test_busca_limita_5_por_grupo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscalim")
    for i in range(6):
        await _criar_produto(
            client, headers_admin, name=f"Produto Limite {i}", sku=f"SKU-LIMITE-{i}"
        )

    res = await client.get("/api/busca", params={"q": "SKU-LIMITE"}, headers=headers_admin)
    body = res.json()
    assert len(body["produtos"]) == 5


async def test_busca_termo_curto_nao_retorna_nada(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers_admin, _, _, _ = await _setup_trio(session, engine, "buscacurta")
    await _criar_produto(client, headers_admin, name="Produto X", sku="X")

    res = await client.get("/api/busca", params={"q": "x"}, headers=headers_admin)
    assert res.status_code == 200
    assert res.json() == {"tickets": [], "clientes": [], "produtos": []}
