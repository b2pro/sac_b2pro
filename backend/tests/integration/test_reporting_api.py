from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

pytestmark = pytest.mark.anyio


async def _setup(client: AsyncClient, session: AsyncSession, engine: AsyncEngine):
    tenant = await seed_provisioned_tenant(session, engine, slug="vis")
    admin = await seed_user(session, email="admin@vis.dev", name="Admin Vis")
    viewer = await seed_user(session, email="view@vis.dev")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    h_admin = token_for(admin, tenant_slug="vis", role=Role.ADMIN)
    h_view = token_for(viewer, tenant_slug="vis", role=Role.VISUALIZADOR)

    async def post(path: str, body: dict) -> dict:
        res = await client.post(f"/api{path}", json=body, headers=h_admin)
        assert res.status_code == 201, res.text
        return res.json()

    async def get_list(path: str) -> list[dict]:
        res = await client.get(f"/api{path}", headers=h_admin)
        assert res.status_code == 200, res.text
        return res.json()

    # marca e defeito padrao ja vem do provisionamento do tenant
    # (seed_tenant_defaults); criar de novo violaria a unicidade de nome.
    marcas = await get_list("/cadastros/marcas")
    brand = next(m for m in marcas if m["name"] == "KODI")
    defeitos = await get_list("/cadastros/defeitos")
    defect = next(d for d in defeitos if d["name"] == "Oxidacao")
    product = await post(
        "/cadastros/produtos", {"name": "Alicate", "sku": f"SKU-{uuid4().hex[:6]}"}
    )
    solution = await post("/cadastros/solucoes", {"name": "Troca"})
    ticket = await post(
        "/tickets",
        {
            "brand_id": brand["id"],
            "priority": "media",
            "customer": {"name": "Cliente Vis", "document": "52998224725"},
            "description": "produto oxidado",
            "items": [{"product_id": product["id"], "defect_type_id": defect["id"], "quantity": 2}],
        },
    )
    return h_admin, h_view, brand, product, defect, solution, ticket


async def test_dashboard_conta_e_exige_permissao(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, *_ = await _setup(client, session, engine)

    res = await client.get("/api/dashboard", headers=h_view)
    assert res.status_code == 200
    body = res.json()
    kpis = {k["key"]: k["count"] for k in body["kpis"]}
    assert kpis["total"] == 1
    assert kpis["abertos"] == 1
    assert body["status_counts"]["aberto"] == 1
    assert body["products"][0]["count"] == 2
    assert body["recent"][0]["customer_name"] == "Cliente Vis"
    assert body["kpis"][1]["filters"] == {"status": "aberto"}

    outro_brand = await client.get(f"/api/dashboard?brand_id={uuid4()}", headers=h_view)
    assert outro_brand.status_code == 200
    assert {k["key"]: k["count"] for k in outro_brand.json()["kpis"]}["total"] == 0

    sem_token = await client.get("/api/dashboard")
    assert sem_token.status_code == 401


async def test_relatorio_filtra_e_pagina(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, product, defect, solution, ticket = await _setup(
        client, session, engine
    )
    res = await client.get(f"/api/relatorios?product_id={product['id']}", headers=h_view)
    assert res.status_code == 200
    body = res.json()
    assert body["kpis"]["total"] == 1
    assert body["total"] == 1
    assert body["items"][0]["number"] == ticket["number"]

    vazio = await client.get(f"/api/relatorios?product_id={uuid4()}", headers=h_view)
    assert vazio.json()["kpis"]["total"] == 0

    invalido = await client.get("/api/relatorios?de=nao-e-data", headers=h_view)
    assert invalido.status_code == 422


async def test_midias_lista_vazia_sem_anexos(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, h_view, *_ = await _setup(client, session, engine)
    res = await client.get("/api/midias", headers=h_view)
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0, "page": 1, "per_page": 20}


async def test_export_csv_com_bom_e_mesmos_filtros_da_tela(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    h_admin, h_view, brand, product, *_ = await _setup(client, session, engine)

    res = await client.get("/api/relatorios/export", headers=h_view)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    text = res.text
    assert text.startswith("﻿numero,")
    linhas = [linha for linha in text.splitlines() if linha.strip()]
    assert len(linhas) == 2  # header + 1 ticket
    assert "Cliente Vis" in linhas[1]
    assert "Alicate x2" in linhas[1]

    # paridade: filtro que zera a tela zera o CSV
    produto_inexistente = uuid4()
    tela = await client.get(f"/api/relatorios?product_id={produto_inexistente}", headers=h_view)
    vazio = await client.get(
        f"/api/relatorios/export?product_id={produto_inexistente}", headers=h_view
    )
    assert tela.json()["kpis"]["total"] == 0
    assert len([linha for linha in vazio.text.splitlines() if linha.strip()]) == 1  # so o header
