import io

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


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), color=(220, 90, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def test_foto_do_produto_da_intencao_ao_get(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, headers = await _setup(session, engine, "fotoapi1")
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "Alicate com foto", "sku": "AF-1"},
            headers=headers,
        )
    ).json()
    imagem = _png()

    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/intencao",
        json={"content_type": "image/png", "size_bytes": len(imagem)},
        headers=headers,
    )
    assert res.status_code == 201
    intencao = res.json()
    assert f"catalogo/produtos/{produto['id']}/" in intencao["object_key"]

    async with httpx.AsyncClient() as direto:
        put = await direto.put(
            intencao["upload_url"], content=imagem, headers={"Content-Type": "image/png"}
        )
    assert put.status_code == 200

    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/confirmar",
        json={"object_key": intencao["object_key"]},
        headers=headers,
    )
    assert res.status_code == 204

    listagem = (await client.get("/api/cadastros/produtos", headers=headers)).json()
    alvo = next(p for p in listagem["items"] if p["id"] == produto["id"])
    assert alvo["photo_key"] == intencao["object_key"]

    res = await client.delete(f"/api/cadastros/produtos/{produto['id']}/foto", headers=headers)
    assert res.status_code == 204
    listagem = (await client.get("/api/cadastros/produtos", headers=headers)).json()
    alvo = next(p for p in listagem["items"] if p["id"] == produto["id"])
    assert alvo["photo_key"] is None
    assert alvo["photo_url"] is None


async def test_chave_de_outro_produto_e_recusada(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, headers = await _setup(session, engine, "fotoapi2")
    a = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "A", "sku": "A-1"}, headers=headers
        )
    ).json()
    b = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "B", "sku": "B-1"}, headers=headers
        )
    ).json()
    intencao = (
        await client.post(
            f"/api/cadastros/produtos/{b['id']}/foto/intencao",
            json={"content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
    ).json()
    res = await client.post(
        f"/api/cadastros/produtos/{a['id']}/foto/confirmar",
        json={"object_key": intencao["object_key"]},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "object_key"


async def test_atendente_nao_gerencia_foto(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, headers = await _setup(session, engine, "fotoapi3")
    att = await seed_user(session, email="att@fotoapi3.com", name="Bruno")
    await seed_link(session, user=att, tenant=tenant, role=Role.ATENDENTE)
    att_headers = token_for(att, tenant_slug=tenant.slug, role=Role.ATENDENTE)
    produto = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "C", "sku": "C-1"}, headers=headers
        )
    ).json()
    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/intencao",
        json={"content_type": "image/png", "size_bytes": 100},
        headers=att_headers,
    )
    assert res.status_code == 403
