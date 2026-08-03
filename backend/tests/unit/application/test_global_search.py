from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.global_search import (
    EMPTY_RESULT,
    RESULTS_PER_GROUP,
    GlobalSearchResult,
    GlobalSearchUseCase,
)
from sac.domain.permissions import Role


class _ExplodingRepo:
    """Fake que estoura se o use case tocar o repositorio.

    Prova que o termo curto e recusado antes de qualquer query: se a
    implementacao chamar search() por engano, o teste falha alto e claro em
    vez de silenciosamente aceitar uma query cara/sem seletividade.
    """

    async def search(self, term: str, owner_user_id, limit: int) -> GlobalSearchResult:
        raise AssertionError("repositorio nao deveria ser chamado para termo curto")


class _RecordingRepo:
    def __init__(self, result: GlobalSearchResult) -> None:
        self._result = result
        self.calls: list[tuple[str, object, int]] = []

    async def search(self, term: str, owner_user_id, limit: int) -> GlobalSearchResult:
        self.calls.append((term, owner_user_id, limit))
        return self._result


async def test_termo_curto_retorna_vazio_sem_tocar_repositorio() -> None:
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    use_case = GlobalSearchUseCase(_ExplodingRepo())

    result = await use_case.execute(actor, " a ")

    assert result == EMPTY_RESULT


async def test_termo_so_espacos_retorna_vazio_sem_tocar_repositorio() -> None:
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    use_case = GlobalSearchUseCase(_ExplodingRepo())

    result = await use_case.execute(actor, "   ")

    assert result == EMPTY_RESULT


async def test_termo_vazio_retorna_vazio_sem_tocar_repositorio() -> None:
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    use_case = GlobalSearchUseCase(_ExplodingRepo())

    result = await use_case.execute(actor, "")

    assert result == EMPTY_RESULT


async def test_termo_de_um_caractere_nao_chega_ao_repositorio() -> None:
    # fronteira exata de MIN_TERM_LENGTH (2), lado de baixo: sem padding de
    # espaco (ao contrario do teste " a " acima), para isolar o off-by-one
    # do proprio guard e nao do strip().
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    use_case = GlobalSearchUseCase(_ExplodingRepo())

    result = await use_case.execute(actor, "x")

    assert result == EMPTY_RESULT


async def test_termo_de_dois_caracteres_chega_ao_repositorio() -> None:
    # fronteira exata de MIN_TERM_LENGTH (2), lado de cima: o menor termo
    # valido deve ser repassado ao repositorio, nao recusado. Sem este
    # teste, um guard `<=` em vez de `<` (ou MIN_TERM_LENGTH errado por 1)
    # passaria despercebido -- todos os outros positivos usam termos bem
    # maiores que 2 chars.
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    repo = _RecordingRepo(EMPTY_RESULT)
    use_case = GlobalSearchUseCase(repo)

    await use_case.execute(actor, "ab")

    assert repo.calls == [("ab", None, RESULTS_PER_GROUP)]


async def test_resultado_vazio_de_termo_curto_e_imutavel() -> None:
    # EMPTY_RESULT e devolvido para todo termo curto. Se os campos fossem
    # list (mutaveis), um .append() num resultado devolvido corromperia a
    # resposta de QUALQUER chamada futura com termo curto -- os campos tem
    # de ser tuple para que a mutacao seja impossivel em vez de so
    # "improvavel".
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    use_case = GlobalSearchUseCase(_ExplodingRepo())

    resultado = await use_case.execute(actor, "x")

    with pytest.raises(AttributeError):
        resultado.tickets.append(None)  # type: ignore[attr-defined]

    # mesmo que a mutacao acima tivesse sucesso, uma chamada nova com termo
    # curto ainda teria de vir vazia -- a garantia real e a impossibilidade
    # de mutar, nao so o isolamento entre chamadas.
    resultado_novo = await use_case.execute(actor, "x")
    assert resultado_novo == EMPTY_RESULT


async def test_atendente_fica_restrito_aos_proprios_tickets() -> None:
    # restrict_to_own (tickets_shared.py) e a regra unica de escopo: para
    # ATENDENTE ela devolve o proprio user_id, que o repositorio usa so para
    # filtrar o grupo de tickets.
    actor_id = uuid4()
    actor = TicketActor(user_id=actor_id, role=Role.ATENDENTE)
    repo = _RecordingRepo(EMPTY_RESULT)
    use_case = GlobalSearchUseCase(repo)

    await use_case.execute(actor, "termo valido")

    assert repo.calls == [("termo valido", actor_id, RESULTS_PER_GROUP)]


async def test_admin_nao_fica_restrito() -> None:
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    repo = _RecordingRepo(EMPTY_RESULT)
    use_case = GlobalSearchUseCase(repo)

    await use_case.execute(actor, "termo valido")

    assert repo.calls == [("termo valido", None, RESULTS_PER_GROUP)]


async def test_visualizador_nao_fica_restrito() -> None:
    # visualizador tem VER_TODOS_TICKETS (permissions.py): restrict_to_own
    # devolve None, ao contrario do atendente.
    actor = TicketActor(user_id=uuid4(), role=Role.VISUALIZADOR)
    repo = _RecordingRepo(EMPTY_RESULT)
    use_case = GlobalSearchUseCase(repo)

    await use_case.execute(actor, "termo valido")

    assert repo.calls == [("termo valido", None, RESULTS_PER_GROUP)]


async def test_termo_e_trimado_antes_de_chamar_repositorio() -> None:
    actor = TicketActor(user_id=uuid4(), role=Role.ADMIN)
    repo = _RecordingRepo(EMPTY_RESULT)
    use_case = GlobalSearchUseCase(repo)

    await use_case.execute(actor, "  532.876  ")

    assert repo.calls == [("532.876", None, RESULTS_PER_GROUP)]
