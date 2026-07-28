from sac.application.ports_cadastros import CepAddress, CepGatewayPort
from sac.domain.documents import normalize_digits
from sac.domain.errors import NotFoundError, ValidationError


class LookupCepUseCase:
    def __init__(self, gateway: CepGatewayPort) -> None:
        self._gateway = gateway

    async def execute(self, cep: str) -> CepAddress:
        digits = normalize_digits(cep)
        if len(digits) != 8:
            raise ValidationError("CEP invalido: use 8 digitos")
        result = await self._gateway.lookup(digits)
        if result is None:
            raise NotFoundError("CEP nao encontrado")
        return result
