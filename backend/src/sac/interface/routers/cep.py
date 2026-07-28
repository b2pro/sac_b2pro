from fastapi import APIRouter, Depends

from sac.application.use_cases.cep import LookupCepUseCase
from sac.infrastructure.cep import ViaCepGateway
from sac.interface.deps import get_cep_gateway, get_current_identity
from sac.interface.schemas import CepOut, cep_out

router = APIRouter(prefix="/cep", tags=["cep"], dependencies=[Depends(get_current_identity)])


@router.get("/{cep}", response_model=CepOut)
async def lookup_cep(cep: str, gateway: ViaCepGateway = Depends(get_cep_gateway)) -> CepOut:
    return cep_out(await LookupCepUseCase(gateway).execute(cep))
