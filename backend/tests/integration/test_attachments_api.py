import io
from uuid import uuid4

import httpx
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


def _png(width: int = 800, height: int = 400) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 140, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Alice Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, admin, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def _ticket(client: AsyncClient, headers: dict[str, str]) -> str:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets",
        json={"brand_id": marcas[0]["id"], "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_ciclo_completo_de_anexo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi1")
    ticket_id = await _ticket(client, headers)
    imagem = _png()

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={
            "filename": "foto do defeito.png",
            "content_type": "image/png",
            "size_bytes": len(imagem),
        },
        headers=headers,
    )
    assert res.status_code == 201
    intencao = res.json()
    assert intencao["object_key"].endswith(".png")
    assert "foto do defeito" not in intencao["object_key"]
    # isolamento por tenant: a chave nasce sob o slug do token, nunca de outro tenant
    assert intencao["object_key"].startswith("anexapi1/")
    assert intencao["preview_upload_url"] is None

    # o navegador sobe direto no storage
    async with httpx.AsyncClient() as direto:
        put = await direto.put(
            intencao["upload_url"], content=imagem, headers={"Content-Type": "image/png"}
        )
    assert put.status_code == 200

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
        headers=headers,
    )
    assert res.status_code == 200
    anexo = res.json()
    assert anexo["preview_status"] == "pendente"
    assert anexo["size_bytes"] == len(imagem)
    assert anexo["author_name"] == "Alice Admin"

    listados = (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json()
    assert len(listados) == 1
    assert listados[0]["preview_url"] is None

    url = (
        await client.get(
            f"/api/tickets/{ticket_id}/anexos/{anexo['id']}/url?variante=original",
            headers=headers,
        )
    ).json()
    async with httpx.AsyncClient() as direto:
        baixado = await direto.get(url["url"])
    assert baixado.status_code == 200
    assert baixado.content == imagem

    res = await client.delete(f"/api/tickets/{ticket_id}/anexos/{anexo['id']}", headers=headers)
    assert res.status_code == 204
    assert (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json() == []


async def test_confirmacao_sem_upload_da_422(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi2")
    ticket_id = await _ticket(client, headers)
    intencao = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
    ).json()
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "object_key"


async def test_tipo_e_tamanho_recusados(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi3")
    ticket_id = await _ticket(client, headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.gif", "content_type": "image/gif", "size_bytes": 100},
        headers=headers,
    )
    assert res.status_code == 422
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 52428801},
        headers=headers,
    )
    assert res.status_code == 422


async def test_cota_de_dez_anexos(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi4")
    ticket_id = await _ticket(client, headers)
    for _ in range(10):
        res = await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
        assert res.status_code == 201
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["details"]["limite"] == 10


async def test_variante_desconhecida_e_recusada_em_vez_de_cair_no_original(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    """Variante fora do vocabulario nao pode falhar aberto entregando o objeto
    original (um pedido de "thumbnail" devolveria os 50 MB da fonte). O router
    restringe o parametro, entao a recusa vem como 422 antes de qualquer busca;
    uma variante valida passa da validacao e ai sim chega ao 404 do anexo."""
    _, _, headers = await _setup(session, engine, "anexapi7")
    ticket_id = await _ticket(client, headers)
    inexistente = uuid4()

    res = await client.get(
        f"/api/tickets/{ticket_id}/anexos/{inexistente}/url?variante=thumbnail",
        headers=headers,
    )
    assert res.status_code == 422

    for variante in ("medio", "original"):
        res = await client.get(
            f"/api/tickets/{ticket_id}/anexos/{inexistente}/url?variante={variante}",
            headers=headers,
        )
        assert res.status_code == 404


async def test_video_recebe_duas_urls_e_thumb_do_navegador(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi5")
    ticket_id = await _ticket(client, headers)
    intencao = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={
                "filename": "clipe.mp4",
                "content_type": "video/mp4",
                "size_bytes": 12,
                "with_preview": True,
            },
            headers=headers,
        )
    ).json()
    assert intencao["preview_upload_url"] is not None

    async with httpx.AsyncClient() as direto:
        await direto.put(
            intencao["upload_url"],
            content=b"conteudo-mp4",
            headers={"Content-Type": "video/mp4"},
        )
        await direto.put(
            intencao["preview_upload_url"],
            content=_png(100, 100),
            headers={"Content-Type": "image/webp"},
        )

    anexo = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
            headers=headers,
        )
    ).json()
    assert anexo["kind"] == "video"
    assert anexo["preview_status"] == "pronto"
    listados = (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json()
    assert listados[0]["preview_url"] is not None


async def test_visualizador_le_mas_nao_anexa_e_ticket_encerrado_bloqueia(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, _, headers = await _setup(session, engine, "anexapi6")
    viewer = await seed_user(session, email="viewer@anexapi6.com", name="Carla")
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    viewer_headers = token_for(viewer, tenant_slug=tenant.slug, role=Role.VISUALIZADOR)
    ticket_id = await _ticket(client, headers)

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 10},
        headers=viewer_headers,
    )
    assert res.status_code == 403
    assert (
        await client.get(f"/api/tickets/{ticket_id}/anexos", headers=viewer_headers)
    ).status_code == 200

    # a mesma permissao (COMENTAR_ANEXAR) tambem bloqueia confirmar e excluir; o
    # anexo_id nem precisa existir, pois a permissao e negada antes de qualquer
    # busca no repositorio
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{uuid4()}/confirmar",
        headers=viewer_headers,
    )
    assert res.status_code == 403
    res = await client.delete(
        f"/api/tickets/{ticket_id}/anexos/{uuid4()}",
        headers=viewer_headers,
    )
    assert res.status_code == 403

    await client.post(f"/api/tickets/{ticket_id}/cancelar", json={}, headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 10},
        headers=headers,
    )
    assert res.status_code == 409
