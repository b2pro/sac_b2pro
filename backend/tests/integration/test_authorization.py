from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Permission, Role
from sac.infrastructure.settings import Settings
from sac.interface.app import create_app
from sac.interface.deps import require_module, require_permission, require_super_admin
from tests.integration.helpers import seed_link, seed_tenant, seed_user

router = APIRouter(prefix="/api/teste")


@router.get("/plataforma", dependencies=[Depends(require_super_admin)])
async def rota_plataforma() -> dict[str, bool]:
    return {"ok": True}


@router.get("/decidir", dependencies=[Depends(require_permission(Permission.DECIDIR_TICKET))])
async def rota_decidir() -> dict[str, bool]:
    return {"ok": True}


@router.get("/modulo", dependencies=[Depends(require_module("tickets"))])
async def rota_modulo() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
async def guarded_client(engine: AsyncEngine, database: str) -> AsyncIterator[AsyncClient]:
    application: FastAPI = create_app(Settings(database_url=database))
    application.include_router(router)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await application.state.engine.dispose()


async def test_sem_token_retorna_401(guarded_client: AsyncClient) -> None:
    response = await guarded_client.get("/api/teste/plataforma")
    assert response.status_code == 401


async def test_super_admin_exigido(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    comum = await seed_user(session, email="comum@b2.com")
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)

    negado = await guarded_client.get("/api/teste/plataforma", headers=token_for(comum))
    permitido = await guarded_client.get("/api/teste/plataforma", headers=token_for(sa))

    assert negado.status_code == 403
    assert permitido.status_code == 200


async def test_permissao_por_papel(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    user = await seed_user(session, email="ana@b2.com")

    atendente = await guarded_client.get(
        "/api/teste/decidir", headers=token_for(user, tenant_slug="b2pro", role=Role.ATENDENTE)
    )
    supervisor = await guarded_client.get(
        "/api/teste/decidir", headers=token_for(user, tenant_slug="b2pro", role=Role.SUPERVISOR)
    )

    assert atendente.status_code == 403
    assert supervisor.status_code == 200


async def test_modulo_por_tenant(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    user = await seed_user(session, email="ana@b2.com")
    com_modulo = await seed_tenant(session, slug="com_mod", modules={"tickets": True})
    sem_modulo = await seed_tenant(session, slug="sem_mod", modules={})
    await seed_link(session, user=user, tenant=com_modulo)
    await seed_link(session, user=user, tenant=sem_modulo)

    permitido = await guarded_client.get(
        "/api/teste/modulo", headers=token_for(user, tenant_slug="com_mod", role=Role.ADMIN)
    )
    negado = await guarded_client.get(
        "/api/teste/modulo", headers=token_for(user, tenant_slug="sem_mod", role=Role.ADMIN)
    )

    assert permitido.status_code == 200
    assert negado.status_code == 403
