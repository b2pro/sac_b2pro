import pytest

from sac.application.ports_cadastros import CepAddress
from sac.application.use_cases.cep import LookupCepUseCase
from sac.domain.errors import CepUnavailableError, NotFoundError, ValidationError

ENDERECO = CepAddress(
    cep="95010000", street="Rua Sinimbu", neighborhood="Centro", city="Caxias do Sul", state="RS"
)


class StubGateway:
    def __init__(self, result: CepAddress | None = None, unavailable: bool = False) -> None:
        self._result = result
        self._unavailable = unavailable
        self.chamado_com: str | None = None

    async def lookup(self, cep: str) -> CepAddress | None:
        self.chamado_com = cep
        if self._unavailable:
            raise CepUnavailableError("servico de CEP indisponivel")
        return self._result


async def test_lookup_normaliza_e_retorna() -> None:
    gateway = StubGateway(result=ENDERECO)
    result = await LookupCepUseCase(gateway).execute("95010-000")
    assert result == ENDERECO
    assert gateway.chamado_com == "95010000"


@pytest.mark.parametrize("cep", ["123", "abcdefgh", ""])
async def test_formato_invalido(cep: str) -> None:
    with pytest.raises(ValidationError):
        await LookupCepUseCase(StubGateway()).execute(cep)


async def test_nao_encontrado() -> None:
    with pytest.raises(NotFoundError):
        await LookupCepUseCase(StubGateway(result=None)).execute("95010000")


async def test_indisponivel_propaga() -> None:
    with pytest.raises(CepUnavailableError):
        await LookupCepUseCase(StubGateway(unavailable=True)).execute("95010000")
