from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.notifications import NotificationType
from sac.domain.permissions import Role
from sac.infrastructure.repositories_notifications import SqlNotificationRepository
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

VALID_CPF = "39053344705"


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, admin, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def _ticket_completo(client: AsyncClient, headers: dict[str, str]) -> str:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    defeitos = (await client.get("/api/cadastros/defeitos", headers=headers)).json()
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "Produto W", "sku": f"SKU-{len(defeitos)}-W"},
            headers=headers,
        )
    ).json()
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": marcas[0]["id"],
            "priority": "media",
            "customer": {"name": "Cliente W", "document": VALID_CPF},
            "description": "produto com defeito",
            "items": [{"product_id": produto["id"], "defect_type_id": defeitos[0]["id"]}],
        },
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def _solution_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/solucoes", headers=headers)
    return str(res.json()[0]["id"])


async def test_fluxo_completo_com_reverso(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf1")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "aguardando_analise"

    res = await client.post(
        f"/api/tickets/{ticket_id}/aprovar", json={"notes": "aprovado ok"}, headers=headers
    )
    assert res.json()["status"] == "aprovado"

    res = await client.post(
        f"/api/tickets/{ticket_id}/reversos", json={"code": "BR123BR"}, headers=headers
    )
    assert res.status_code == 201
    reverso_id = res.json()["id"]
    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    assert detail["ticket"]["status"] == "aguardando_envio_reverso"

    res = await client.post(f"/api/tickets/{ticket_id}/produto-recebido", headers=headers)
    assert res.json()["status"] == "produto_recebido"

    solution = await _solution_id(client, headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/finalizar",
        json={"solution_type_id": solution, "notes": "trocado"},
        headers=headers,
    )
    assert res.json()["status"] == "finalizado"
    assert res.json()["closed_at"] is not None

    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    types = [e["type"] for e in detail["timeline"]]
    # enviar-analise, aprovar, aprovado->aguardando_envio_reverso (via reverso),
    # produto-recebido e finalizar
    assert types.count("transicao") == 5
    assert "reverso_registrado" in types
    assert detail["reverses"][0]["id"] == reverso_id


async def test_declinar_exige_motivo_e_transicao_invalida_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf2")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers)
    assert res.status_code == 409
    assert res.json()["code"] == "transicao_invalida"

    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/declinar", json={"reason": ""}, headers=headers
    )
    assert res.status_code == 422

    res = await client.post(
        f"/api/tickets/{ticket_id}/declinar",
        json={"reason": "sem cobertura"},
        headers=headers,
    )
    assert res.json()["status"] == "declinado"

    res = await client.post(f"/api/tickets/{ticket_id}/reabrir", headers=headers)
    assert res.json()["status"] == "aberto"


async def test_excluir_ultimo_reverso_volta_para_aprovado(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf3")
    ticket_id = await _ticket_completo(client, headers)
    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    await client.post(f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers)
    reverso = (
        await client.post(
            f"/api/tickets/{ticket_id}/reversos", json={"code": "BR1"}, headers=headers
        )
    ).json()
    res = await client.delete(f"/api/tickets/{ticket_id}/reversos/{reverso['id']}", headers=headers)
    assert res.status_code == 204
    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    assert detail["ticket"]["status"] == "aprovado"


async def test_enviar_analise_incompleto_422_com_faltantes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf4")
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    parcial = (
        await client.post(
            "/api/tickets",
            json={"brand_id": marcas[0]["id"], "priority": "media"},
            headers=headers,
        )
    ).json()
    res = await client.post(f"/api/tickets/{parcial['id']}/enviar-analise", headers=headers)
    assert res.status_code == 422
    assert set(res.json()["details"]["faltando"]) == {"cliente", "itens", "descricao"}


async def test_garantia_e_aguardar_cliente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf5")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(f"/api/tickets/{ticket_id}/aguardar-cliente", headers=headers)
    assert res.json()["status"] == "aguardando_cliente"
    res = await client.post(f"/api/tickets/{ticket_id}/retomar", headers=headers)
    assert res.json()["status"] == "aberto"

    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    await client.post(f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers)
    res = await client.put(
        f"/api/tickets/{ticket_id}/garantia",
        json={"order_code": "TINY-9", "tracking_code": "RA99"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "aprovado"
    assert res.json()["warranty_order_code"] == "TINY-9"


async def test_comentarios_e_nao_lido(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, admin, headers = await _setup(session, engine, "twf6")
    supervisor = await seed_user(session, email="sup@twf6.com", name="Sup")
    await seed_link(session, user=supervisor, tenant=tenant, role=Role.SUPERVISOR)
    sup_headers = token_for(supervisor, tenant_slug=tenant.slug, role=Role.SUPERVISOR)
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios", json={"body": "primeira"}, headers=headers
    )
    assert res.status_code == 201
    first_id = res.json()["id"]
    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios",
        json={"body": "resposta", "reply_to_id": first_id},
        headers=sup_headers,
    )
    assert res.json()["reply_to_id"] == first_id

    # comentario do supervisor tornou o ticket nao lido para o admin
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is True
    # abrir o detalhe marca como lido
    await client.get(f"/api/tickets/{ticket_id}", headers=headers)
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is False
    # marcar como nao lido de novo
    res = await client.post(f"/api/tickets/{ticket_id}/nao-lido", headers=headers)
    assert res.status_code == 204
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is True

    # encerrar e tentar comentar -> 409
    await client.post(f"/api/tickets/{ticket_id}/cancelar", json={}, headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios", json={"body": "tarde"}, headers=headers
    )
    assert res.status_code == 409


async def test_aprovar_ticket_com_atendente_diferente_grava_notificacao(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    # ponta a ponta do fanout: admin cria o ticket ja atribuido a outro
    # atendente (o que ja gera uma notificacao de atribuicao) e depois
    # conduz o fluxo de decisao sozinho; cada transicao deve gravar uma
    # notificacao de transicao para o atendente na tabela do schema do
    # tenant (get_notification_fanout usando o publisher real do banco).
    tenant, admin, headers = await _setup(session, engine, "twf7")
    atendente = await seed_user(session, email="atendente@twf7.com", name="Atendente")
    await seed_link(session, user=atendente, tenant=tenant, role=Role.ATENDENTE)

    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    defeitos = (await client.get("/api/cadastros/defeitos", headers=headers)).json()
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "Produto WF7", "sku": "SKU-WF7"},
            headers=headers,
        )
    ).json()
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": marcas[0]["id"],
            "priority": "media",
            "customer": {"name": "Cliente WF7", "document": VALID_CPF},
            "description": "produto com defeito",
            "attendant_user_id": str(atendente.id),
            "items": [{"product_id": produto["id"], "defect_type_id": defeitos[0]["id"]}],
        },
        headers=headers,
    )
    assert res.status_code == 201
    ticket_id = res.json()["id"]
    assert res.json()["attendant_user_id"] == str(atendente.id)

    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/aprovar", json={"notes": "aprovado ok"}, headers=headers
    )
    assert res.status_code == 200

    translated = engine.execution_options(schema_translate_map={"tenant": tenant.schema_name})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as ts:
        repo = SqlNotificationRepository(ts)
        rows, total = await repo.list_for_user(atendente.id, only_unread=False, page=1, per_page=10)

    # criacao (atribuicao) + enviar-analise (transicao) + aprovar (transicao)
    assert total == 3
    tipos = [row.type for row in rows]
    assert tipos.count(NotificationType.TRANSICAO) == 2
    assert tipos.count(NotificationType.ATRIBUICAO) == 1
    assert all(row.actor_user_id == admin.id for row in rows)
    assert all(row.ticket_number == res.json()["number"] for row in rows)
