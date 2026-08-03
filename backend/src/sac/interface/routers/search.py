from fastapi import APIRouter, Depends

from sac.application.ports import TokenPayload
from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.global_search import GlobalSearchUseCase
from sac.infrastructure.repositories_search import SqlGlobalSearchRepository
from sac.interface.deps import get_current_identity, get_global_search_repository
from sac.interface.schemas import GlobalSearchOut, global_search_out

router = APIRouter(prefix="/busca", tags=["busca"])


@router.get("", response_model=GlobalSearchOut)
async def global_search(
    q: str = "",
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlGlobalSearchRepository = Depends(get_global_search_repository),
) -> GlobalSearchOut:
    # qualquer papel do tenant pode buscar: a dependencia e so a sessao de
    # tenant (get_global_search_repository -> get_tenant_session), sem
    # require_permission. A visibilidade de tickets ja e cortada dentro do
    # use case (restrict_to_own vale so para aquele grupo).
    assert identity.role is not None  # garantido por get_tenant_session (exige tenant_slug)
    actor = TicketActor(user_id=identity.user_id, role=identity.role)
    result = await GlobalSearchUseCase(repo).execute(actor, q)
    return global_search_out(result)
