from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_cadastros import CepAddress
from sac.domain.errors import CepUnavailableError
from sac.interface.deps import get_cep_gateway
from tests.integration.helpers import seed_user, token_for

ENDERECO = CepAddress(
    cep="95010000", street="Rua Sinimbu", neighborhood="Centro", city="Caxias do Sul", state="RS"
)


class StubGateway:
    def __init__(self, result: CepAddress | None = None, unavailable: bool = False) -> None:
        self._result = result
        self._unavailable = unavailable

    async def lookup(self, cep: str) -> CepAddress | None:
        if self._unavailable:
            raise CepUnavailableError("servico de CEP indisponivel")
        return self._result


@pytest.fixture
async def stubbed_client(app: FastAPI) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    app.dependency_overrides.clear()


async def test_cep_encontrado(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    user = await seed_user(session, email="cep@b2.com")

    response = await client.get("/api/cep/95010-000", headers=token_for(user))
    assert response.status_code == 200
    assert response.json() == {
        "cep": "95010000",
        "street": "Rua Sinimbu",
        "neighborhood": "Centro",
        "city": "Caxias do Sul",
        "state": "RS",
    }


async def test_cep_invalido_422(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    user = await seed_user(session, email="cep2@b2.com")
    assert (await client.get("/api/cep/123", headers=token_for(user))).status_code == 422


async def test_cep_nao_encontrado_404(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=None)
    user = await seed_user(session, email="cep3@b2.com")
    assert (await client.get("/api/cep/95010000", headers=token_for(user))).status_code == 404


async def test_cep_indisponivel_503(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(unavailable=True)
    user = await seed_user(session, email="cep4@b2.com")
    response = await client.get("/api/cep/95010000", headers=token_for(user))
    assert response.status_code == 503
    assert response.json()["code"] == "cep_indisponivel"


async def test_cep_sem_token_401(stubbed_client) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    assert (await client.get("/api/cep/95010000")).status_code == 401
