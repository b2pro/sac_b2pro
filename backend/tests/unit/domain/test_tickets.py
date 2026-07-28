import pytest

from sac.domain.errors import InvalidTransitionError
from sac.domain.tickets import (
    CLOSED_STATUSES,
    VALID_TRANSITIONS,
    TicketStatus,
    ensure_transition,
)


def test_fluxo_principal_e_valido() -> None:
    ensure_transition(TicketStatus.ABERTO, TicketStatus.AGUARDANDO_ANALISE)
    ensure_transition(TicketStatus.AGUARDANDO_ANALISE, TicketStatus.APROVADO)
    ensure_transition(TicketStatus.APROVADO, TicketStatus.AGUARDANDO_ENVIO_REVERSO)
    ensure_transition(TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.PRODUTO_RECEBIDO)
    ensure_transition(TicketStatus.PRODUTO_RECEBIDO, TicketStatus.FINALIZADO)


def test_declinio_aprovacao_direta_e_laterais() -> None:
    ensure_transition(TicketStatus.AGUARDANDO_ANALISE, TicketStatus.DECLINADO)
    ensure_transition(TicketStatus.APROVADO, TicketStatus.FINALIZADO)
    ensure_transition(TicketStatus.ABERTO, TicketStatus.AGUARDANDO_CLIENTE)
    ensure_transition(TicketStatus.AGUARDANDO_CLIENTE, TicketStatus.ABERTO)
    ensure_transition(TicketStatus.AGUARDANDO_CLIENTE, TicketStatus.AGUARDANDO_ANALISE)
    ensure_transition(TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.APROVADO)


def test_cancelado_a_partir_de_todo_nao_encerrado() -> None:
    for status in TicketStatus:
        if status in CLOSED_STATUSES:
            assert TicketStatus.CANCELADO not in VALID_TRANSITIONS[status]
        else:
            ensure_transition(status, TicketStatus.CANCELADO)


def test_reabertura_de_encerrados() -> None:
    for status in CLOSED_STATUSES:
        ensure_transition(status, TicketStatus.APROVADO)
        ensure_transition(status, TicketStatus.ABERTO)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TicketStatus.ABERTO, TicketStatus.APROVADO),
        (TicketStatus.ABERTO, TicketStatus.FINALIZADO),
        (TicketStatus.AGUARDANDO_ANALISE, TicketStatus.AGUARDANDO_ENVIO_REVERSO),
        (TicketStatus.APROVADO, TicketStatus.ABERTO),
        (TicketStatus.PRODUTO_RECEBIDO, TicketStatus.APROVADO),
        (TicketStatus.FINALIZADO, TicketStatus.FINALIZADO),
        (TicketStatus.FINALIZADO, TicketStatus.CANCELADO),
    ],
)
def test_transicoes_invalidas(current: TicketStatus, target: TicketStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        ensure_transition(current, target)
    assert exc.value.code == "transicao_invalida"
    assert exc.value.details == {"de": current, "para": target}


def test_todo_status_tem_linha_na_tabela() -> None:
    assert set(VALID_TRANSITIONS.keys()) == set(TicketStatus)
