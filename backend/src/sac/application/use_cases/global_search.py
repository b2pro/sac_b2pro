"""Busca global: um termo so resolve tickets, clientes e produtos pelos seus
identificadores (numero, order_code, documento, telefone, email, sku, nome).

A UI de comando (Ctrl+K, Task 13 da Fase 4) consome o endpoint que usa este
caso de uso; aqui fica so o backend (Task 7).
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.tickets_shared import restrict_to_own
from sac.domain.tickets import TicketStatus

# termo com 1 caractere so gera ruido demais: ilike '%x%' varre a tabela
# inteira sem seletividade nenhuma (mesmo com os indices GIN de trigrama, um
# termo de 1 char casa quase tudo). Por isso o minimo e 2.
MIN_TERM_LENGTH = 2

# mesma logica de seletividade do MIN_TERM_LENGTH, mas para o atalho de
# digitos usado por documento/telefone: normalize_digits() colapsa o termo
# original para so os digitos, entao um termo qualquer com 1 ou 2 digitos
# (ex.: "zz7zz") virava um LIKE de 1-2 chars sobre a coluna inteira e casava
# quase todo cliente. Abaixo deste piso o atalho de digitos fica desligado
# -- o termo ainda casa por nome/email normalmente.
MIN_DOCUMENT_DIGITS = 3

# limite por grupo, nao total: a busca e um preview rapido de command
# palette, nao uma listagem paginada.
RESULTS_PER_GROUP = 5


@dataclass(frozen=True)
class TicketHit:
    id: UUID
    number: int
    status: TicketStatus
    customer_name: str | None
    brand_name: str | None


@dataclass(frozen=True)
class CustomerHit:
    id: UUID
    name: str
    document: str | None


@dataclass(frozen=True)
class ProductHit:
    id: UUID
    name: str
    sku: str | None


@dataclass(frozen=True)
class GlobalSearchResult:
    # tuple, nao list: EMPTY_RESULT abaixo e um singleton compartilhado por
    # toda chamada de termo curto. `frozen=True` so impede reatribuir os
    # campos -- uma list continuaria mutavel via .append()/.extend(), e
    # corromperia a resposta de QUALQUER termo curto futuro. tuple fecha essa
    # brecha: a mutacao vira AttributeError na hora, em vez de bug latente.
    tickets: tuple[TicketHit, ...]
    customers: tuple[CustomerHit, ...]
    products: tuple[ProductHit, ...]


EMPTY_RESULT = GlobalSearchResult(tickets=(), customers=(), products=())


class GlobalSearchRepository(Protocol):
    async def search(
        self, term: str, owner_user_id: UUID | None, limit: int
    ) -> GlobalSearchResult: ...


class GlobalSearchUseCase:
    def __init__(self, repo: GlobalSearchRepository) -> None:
        self._repo = repo

    async def execute(self, actor: TicketActor, term: str) -> GlobalSearchResult:
        trimmed = term.strip()
        if len(trimmed) < MIN_TERM_LENGTH:
            # termo curto nem toca o repositorio: o command palette da UI
            # dispara a cada tecla digitada, entao um termo de 0-1 char nao
            # pode virar Seq Scan (ou ate Bitmap Index Scan largo) no banco.
            return EMPTY_RESULT
        # restrict_to_own (tickets_shared.py) e a regra unica de escopo do
        # projeto para tickets. Ela vale so para o grupo de tickets: clientes
        # e produtos sao cadastros visiveis a qualquer papel do tenant, entao
        # o owner_user_id resolvido aqui e repassado ao repositorio so para
        # filtrar aquele grupo.
        owner_user_id = restrict_to_own(actor)
        return await self._repo.search(trimmed, owner_user_id, RESULTS_PER_GROUP)
