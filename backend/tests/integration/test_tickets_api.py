from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.entities import Tenant, User
from sac.domain.permissions import Role
from sac.infrastructure.models_tenant import TicketModel
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


async def _solution_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/solucoes", headers=headers)
    return str(res.json()[0]["id"])


def _tenant_session_factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


async def _force_due_at(engine: AsyncEngine, schema: str, ticket_id: str, due_at: datetime) -> None:
    # nenhum endpoint permite escrever due_at diretamente (a data e recalculada
    # pela SLA da prioridade); o cenario de atrasado exige escrita direta na
    # tabela do schema do tenant.
    factory = _tenant_session_factory(engine, schema)
    async with factory() as ts:
        await ts.execute(
            update(TicketModel).where(TicketModel.id == UUID(ticket_id)).values(due_at=due_at)
        )
        await ts.commit()


async def _soft_delete(engine: AsyncEngine, schema: str, ticket_id: str) -> None:
    # idem: nao ha rota de exclusao de ticket: o cenario de excluido exige
    # escrita direta.
    factory = _tenant_session_factory(engine, schema)
    async with factory() as ts:
        await ts.execute(
            update(TicketModel)
            .where(TicketModel.id == UUID(ticket_id))
            .values(deleted_at=datetime.now(UTC))
        )
        await ts.commit()


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


async def test_contadores_da_fila(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tctd1")
    headers = env.headers
    tenant = env.tenant
    brand = await _brand_id(client, headers)
    defect = await _defect_id(client, headers)
    product = await _product_id(client, headers, "SKU-CTD1")
    solution = await _solution_id(client, headers)
    outro_atendente = await seed_user(session, email="atendente@tctd1.com", name="Atendente")
    await seed_link(session, user=outro_atendente, tenant=tenant, role=Role.ATENDENTE)

    def _ticket_completo_payload(customer_name: str) -> dict[str, object]:
        return {
            "brand_id": brand,
            "priority": "media",
            "customer": {"name": customer_name, "document": VALID_CPF},
            "description": "defeito relatado",
            "items": [{"product_id": product, "defect_type_id": defect}],
        }

    # T1: aberto, no prazo, atendente = admin, fica LIDO (o criador ja e
    # marcado como leitor na criacao e nada mais toca o ticket depois) -
    # unico lido do cenario, para que nao_lidos != todos e o FILTER de
    # nao lidos tenha algo a excluir de fato.
    await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=headers
    )

    # T2: aguardando_analise, atendente = admin
    t2 = (
        await client.post(
            "/api/tickets", json=_ticket_completo_payload("Cliente Dois"), headers=headers
        )
    ).json()
    res = await client.post(f"/api/tickets/{t2['id']}/enviar-analise", headers=headers)
    assert res.status_code == 200
    await client.post(f"/api/tickets/{t2['id']}/nao-lido", headers=headers)

    # T3: finalizado (encerrado), atendente = admin
    t3 = (
        await client.post(
            "/api/tickets", json=_ticket_completo_payload("Cliente Tres"), headers=headers
        )
    ).json()
    await client.post(f"/api/tickets/{t3['id']}/enviar-analise", headers=headers)
    await client.post(f"/api/tickets/{t3['id']}/aprovar", json={}, headers=headers)
    res = await client.post(
        f"/api/tickets/{t3['id']}/finalizar",
        json={"solution_type_id": solution},
        headers=headers,
    )
    assert res.status_code == 200
    await client.post(f"/api/tickets/{t3['id']}/nao-lido", headers=headers)
    # devolve devidamente vencido: garante que "atrasados" exige nao encerrado
    # alem de due_at vencido, senao um finalizado antigo tambem entraria na conta
    await _force_due_at(
        engine, tenant.schema_name, t3["id"], datetime.now(UTC) - timedelta(hours=1)
    )

    # T4: atrasado (due_at no passado, nao encerrado), atendente = admin
    t4 = (
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=headers
        )
    ).json()
    await client.post(f"/api/tickets/{t4['id']}/nao-lido", headers=headers)
    await _force_due_at(
        engine, tenant.schema_name, t4["id"], datetime.now(UTC) - timedelta(hours=1)
    )

    # T5: de outro atendente, em espera do cliente (fora de aberto/aguardando_analise)
    t5 = (
        await client.post(
            "/api/tickets",
            json={
                "brand_id": brand,
                "priority": "media",
                "attendant_user_id": str(outro_atendente.id),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/api/tickets/{t5['id']}/nao-lido", headers=headers)
    res = await client.post(f"/api/tickets/{t5['id']}/aguardar-cliente", headers=headers)
    assert res.status_code == 200

    # T6: excluido (soft delete), fora de qualquer contagem
    t6 = (
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=headers
        )
    ).json()
    await _soft_delete(engine, tenant.schema_name, t6["id"])

    res = await client.get("/api/tickets/contadores", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["todos"] == 5  # excluido (T6) fora
    assert body["ativos"] == 4  # finalizado (T3) fora
    assert body["abertos"] == 2  # T1 e T4
    assert body["aguardando_analise"] == 1  # T2
    assert body["atrasados"] == 1  # T4
    assert body["nao_lidos"] == 4  # T2, T3, T4, T5 (T1 continua lido pelo criador)
    assert body["meus"] == 4  # T1, T2, T3, T4 (T5 e de outro atendente)


async def test_contadores_de_atendente_veem_so_os_proprios(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tctd2")
    tenant = env.tenant
    brand = await _brand_id(client, env.headers)
    atendente = await seed_user(session, email="proprio@tctd2.com", name="Atendente Proprio")
    await seed_link(session, user=atendente, tenant=tenant, role=Role.ATENDENTE)
    atendente_headers = token_for(atendente, tenant_slug=tenant.slug, role=Role.ATENDENTE)

    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=atendente_headers
    )
    assert res.status_code == 201

    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=env.headers
    )
    assert res.status_code == 201

    res = await client.get("/api/tickets/contadores", headers=atendente_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["todos"] == 1
    assert body["meus"] == 1


async def test_contadores_exigem_autenticacao(client: AsyncClient) -> None:
    res = await client.get("/api/tickets/contadores")
    assert res.status_code == 401
