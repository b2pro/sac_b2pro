import httpx

from sac.application.ports_cadastros import CepAddress
from sac.domain.errors import CepUnavailableError

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"


class ViaCepGateway:
    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._timeout = timeout_seconds

    async def lookup(self, cep: str) -> CepAddress | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(VIACEP_URL.format(cep=cep))
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise CepUnavailableError("servico de CEP indisponivel") from exc
        if data.get("erro"):
            return None
        return CepAddress(
            cep=cep,
            street=data.get("logradouro", ""),
            neighborhood=data.get("bairro", ""),
            city=data.get("localidade", ""),
            state=data.get("uf", ""),
        )
