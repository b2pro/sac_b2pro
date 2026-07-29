from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


async def test_membros_do_tenant_para_qualquer_papel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="membrosapi")
    outro = await seed_provisioned_tenant(session, engine, slug="membrosoutro")
    admin = await seed_user(session, email="admin@membrosapi.com", name="Ana Admin")
    att = await seed_user(session, email="att@membrosapi.com", name="Bruno Atendente")
    fora = await seed_user(session, email="fora@membrosoutro.com", name="Carlos Fora")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=att, tenant=tenant, role=Role.ATENDENTE)
    await seed_link(session, user=fora, tenant=outro, role=Role.ADMIN)

    for user, role in ((admin, Role.ADMIN), (att, Role.ATENDENTE)):
        headers = token_for(user, tenant_slug=tenant.slug, role=role)
        res = await client.get("/api/membros", headers=headers)
        assert res.status_code == 200
        nomes = [m["name"] for m in res.json()]
        assert nomes == ["Ana Admin", "Bruno Atendente"]
        assert "Carlos Fora" not in nomes
        assert all("email" not in m for m in res.json())


async def test_membros_exige_token_de_tenant(client: AsyncClient, session: AsyncSession) -> None:
    assert (await client.get("/api/membros")).status_code == 401
    super_admin = await seed_user(session, email="super@membros.com", is_super_admin=True)
    headers = token_for(super_admin)
    assert (await client.get("/api/membros", headers=headers)).status_code == 401


async def test_visualizador_nao_lista_membros(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="membrosvisu")
    visualizador = await seed_user(session, email="visu@membrosvisu.com", name="Vera Visu")
    await seed_link(session, user=visualizador, tenant=tenant, role=Role.VISUALIZADOR)
    headers = token_for(visualizador, tenant_slug=tenant.slug, role=Role.VISUALIZADOR)

    res = await client.get("/api/membros", headers=headers)
    assert res.status_code == 403
