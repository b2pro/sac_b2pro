import io
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.entities import User
from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

pytestmark = pytest.mark.anyio


def _png(width: int = 20, height: int = 20) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _upload_and_confirm(
    client: AsyncClient, headers: dict[str, str], ticket_id: str, imagem: bytes
) -> dict:
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "foto.png", "content_type": "image/png", "size_bytes": len(imagem)},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    intencao = res.json()
    async with httpx.AsyncClient() as direto:
        put = await direto.put(
            intencao["upload_url"], content=imagem, headers={"Content-Type": "image/png"}
        )
    assert put.status_code == 200
    confirm = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    return confirm.json()


async def _setup(client: AsyncClient, session: AsyncSession, engine: AsyncEngine):
    tenant = await seed_provisioned_tenant(session, engine, slug="vis")
    admin = await seed_user(session, email="admin@vis.dev", name="Admin Vis")
    viewer = await seed_user(session, email="view@vis.dev")
    atendente = await seed_user(session, email="atend@vis.dev", name="Atendente Vis")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    await seed_link(session, user=atendente, tenant=tenant, role=Role.ATENDENTE)
    h_admin = token_for(admin, tenant_slug="vis", role=Role.ADMIN)
    h_view = token_for(viewer, tenant_slug="vis", role=Role.VISUALIZADOR)
    h_atendente = token_for(atendente, tenant_slug="vis", role=Role.ATENDENTE)

    async def post(path: str, body: dict) -> dict:
        res = await client.post(f"/api{path}", json=body, headers=h_admin)
        assert res.status_code == 201, res.text
        return res.json()

    # marca e defeito nao vem mais do provisionamento (ver tenant_seeds): o
    # tenant nasce sem nenhum dos dois e quem opera cadastra os seus.
    brand = await post("/cadastros/marcas", {"name": "KODI"})
    defect = await post("/cadastros/defeitos", {"name": "Oxidação"})
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
    # atendente e seu token sao retornados sem ticket proprio: os testes de
    # escopo por actor criam o segundo ticket sob demanda (via
    # _add_atendente_ticket) para nao alterar as contagens dos testes ja
    # existentes, que assumem um unico ticket no tenant.
    return h_admin, h_view, brand, product, defect, solution, ticket, h_atendente, atendente


async def _add_atendente_ticket(
    client: AsyncClient,
    h_admin: dict[str, str],
    atendente: User,
    brand: dict,
    product: dict,
    defect: dict,
) -> dict:
    """Segundo ticket, atribuido ao atendente por um admin (que pode atribuir
    a qualquer um), usado pelos testes de escopo por actor."""
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": brand["id"],
            "priority": "media",
            "attendant_user_id": str(atendente.id),
            "customer": {"name": "Cliente Atendente", "document": "11144477735"},
            "description": "outro defeito",
            "items": [{"product_id": product["id"], "defect_type_id": defect["id"], "quantity": 1}],
        },
        headers=h_admin,
    )
    assert res.status_code == 201, res.text
    return res.json()


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
    h_admin, h_view, brand, product, defect, solution, ticket, *_ = await _setup(
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


# /relatorios, /relatorios/export e /midias aceitam "de"/"ate" e compartilham
# a mesma regra de periodo (helper _validate_period em routers/reporting.py):
# a validacao precisa dar o mesmo resultado nas tres, nao so na dupla de
# relatorios.
_PERIODO_PATHS = ["/api/relatorios", "/api/relatorios/export", "/api/midias"]


@pytest.mark.parametrize("path", _PERIODO_PATHS)
async def test_periodo_invertido_retorna_422(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine, path: str
) -> None:
    _, h_view, *_ = await _setup(client, session, engine)

    invertido = await client.get(f"{path}?de=2026-08-01&ate=2026-07-01", headers=h_view)
    assert invertido.status_code == 422
    assert invertido.json()["code"] == "validation_error"

    # O limite superior e EXCLUSIVO (opened_at/created_at < ate), entao de == ate
    # descreve o conjunto vazio, nao "um unico dia": tambem e periodo invertido.
    # O front ja manda dia+1 em "ate" (isoEndExclusive), logo de == ate so chega
    # aqui quando o usuario inverteu as datas em um dia.
    mesmo_instante = await client.get(f"{path}?de=2026-08-01&ate=2026-08-01", headers=h_view)
    assert mesmo_instante.status_code == 422
    assert mesmo_instante.json()["code"] == "validation_error"


@pytest.mark.parametrize("path", _PERIODO_PATHS)
async def test_periodo_com_awareness_mista_nao_quebra(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine, path: str
) -> None:
    """de naive + ate aware (e vice-versa) precisa comparar sem TypeError.

    O Pydantic parseia "2026-08-01" como datetime naive e "2026-08-05T00:00:00Z"
    como aware; comparar os dois direto levanta TypeError, que escaparia do
    handler de erro de dominio como 500.
    """
    _, h_view, *_ = await _setup(client, session, engine)

    de_naive = await client.get(f"{path}?de=2026-08-01&ate=2026-08-05T00:00:00Z", headers=h_view)
    assert de_naive.status_code == 200

    ate_naive = await client.get(f"{path}?de=2026-08-01T00:00:00Z&ate=2026-08-05", headers=h_view)
    assert ate_naive.status_code == 200

    # invertido continua 422 (e nao 500) mesmo com awareness mista
    invertido_misto = await client.get(
        f"{path}?de=2026-08-05&ate=2026-08-01T00:00:00Z", headers=h_view
    )
    assert invertido_misto.status_code == 422
    assert invertido_misto.json()["code"] == "validation_error"

    invertido_misto_invertido = await client.get(
        f"{path}?de=2026-08-05T00:00:00Z&ate=2026-08-01", headers=h_view
    )
    assert invertido_misto_invertido.status_code == 422
    assert invertido_misto_invertido.json()["code"] == "validation_error"


@pytest.mark.parametrize("path", _PERIODO_PATHS)
async def test_periodo_com_apenas_um_campo_continua_valido(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine, path: str
) -> None:
    """A guarda so dispara com "de" e "ate" preenchidos: informar apenas um
    dos dois continua um filtro valido (200), sem exigir o par."""
    _, h_view, *_ = await _setup(client, session, engine)

    so_de = await client.get(f"{path}?de=2026-08-01", headers=h_view)
    assert so_de.status_code == 200

    so_ate = await client.get(f"{path}?ate=2026-08-05", headers=h_view)
    assert so_ate.status_code == 200


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
    assert text.startswith("﻿número,")
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


# --- escopo por actor: atendente so ve as proprias linhas, kpis ficam tenant-wide ---


async def test_dashboard_recent_e_por_atendente_mas_kpi_fica_tenant_wide(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    (
        h_admin,
        h_view,
        brand,
        product,
        defect,
        solution,
        ticket,
        h_atendente,
        atendente,
    ) = await _setup(client, session, engine)
    ticket_atendente = await _add_atendente_ticket(
        client, h_admin, atendente, brand, product, defect
    )

    res = await client.get("/api/dashboard", headers=h_atendente)
    assert res.status_code == 200
    body = res.json()
    kpis = {k["key"]: k["count"] for k in body["kpis"]}
    assert kpis["total"] == 2  # kpi continua tenant-wide
    numeros_recentes = {item["number"] for item in body["recent"]}
    assert numeros_recentes == {ticket_atendente["number"]}  # so o proprio ticket

    admin_res = await client.get("/api/dashboard", headers=h_view)
    numeros_admin = {item["number"] for item in admin_res.json()["recent"]}
    assert numeros_admin == {ticket["number"], ticket_atendente["number"]}


async def test_relatorio_tabela_e_por_atendente_mas_kpi_fica_tenant_wide(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    (
        h_admin,
        h_view,
        brand,
        product,
        defect,
        solution,
        ticket,
        h_atendente,
        atendente,
    ) = await _setup(client, session, engine)
    ticket_atendente = await _add_atendente_ticket(
        client, h_admin, atendente, brand, product, defect
    )

    res = await client.get("/api/relatorios", headers=h_atendente)
    assert res.status_code == 200
    body = res.json()
    assert body["kpis"]["total"] == 2  # kpi continua tenant-wide
    assert body["total"] == 1  # tabela restrita ao proprio ticket
    assert body["items"][0]["number"] == ticket_atendente["number"]

    admin_res = await client.get("/api/relatorios", headers=h_view)
    assert admin_res.json()["total"] == 2


async def test_export_csv_e_por_atendente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    (
        h_admin,
        h_view,
        brand,
        product,
        defect,
        solution,
        ticket,
        h_atendente,
        atendente,
    ) = await _setup(client, session, engine)
    ticket_atendente = await _add_atendente_ticket(
        client, h_admin, atendente, brand, product, defect
    )

    res = await client.get("/api/relatorios/export", headers=h_atendente)
    assert res.status_code == 200
    linhas = [linha for linha in res.text.splitlines() if linha.strip()]
    assert len(linhas) == 2  # header + so o proprio ticket
    assert str(ticket_atendente["number"]) in linhas[1]

    admin_res = await client.get("/api/relatorios/export", headers=h_view)
    linhas_admin = [linha for linha in admin_res.text.splitlines() if linha.strip()]
    assert len(linhas_admin) == 3  # header + os dois tickets


async def test_midias_e_por_atendente_mas_admin_ve_tudo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    (
        h_admin,
        h_view,
        brand,
        product,
        defect,
        solution,
        ticket,
        h_atendente,
        atendente,
    ) = await _setup(client, session, engine)
    ticket_atendente = await _add_atendente_ticket(
        client, h_admin, atendente, brand, product, defect
    )
    imagem = _png()
    await _upload_and_confirm(client, h_admin, ticket["id"], imagem)
    await _upload_and_confirm(client, h_atendente, ticket_atendente["id"], imagem)

    res_atendente = await client.get("/api/midias", headers=h_atendente)
    assert res_atendente.status_code == 200
    body_atendente = res_atendente.json()
    assert body_atendente["total"] == 1
    assert body_atendente["items"][0]["ticket_id"] == ticket_atendente["id"]

    res_admin = await client.get("/api/midias", headers=h_view)
    assert res_admin.json()["total"] == 2
