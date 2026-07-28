from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sac.domain.errors import InvalidTransitionError
from sac.domain.tickets import (
    CLOSED_STATUSES,
    DEFAULT_SLA_POLICIES,
    VALID_TRANSITIONS,
    SlaPolicy,
    SlaState,
    Ticket,
    TicketPriority,
    TicketStatus,
    compute_due_at,
    ensure_transition,
    is_closed,
    missing_for_analysis,
    sla_state,
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


def _ticket(**overrides: object) -> Ticket:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "id": uuid4(),
        "number": 1,
        "brand_id": uuid4(),
        "status": TicketStatus.ABERTO,
        "priority": TicketPriority.MEDIA,
        "attendant_user_id": uuid4(),
        "opened_at": now,
        "due_at": now + timedelta(hours=72),
        "last_activity_at": now,
    }
    base.update(overrides)
    return Ticket(**base)  # type: ignore[arg-type]


def test_politicas_default_de_sla() -> None:
    assert DEFAULT_SLA_POLICIES[TicketPriority.URGENTE].hours == 24
    assert DEFAULT_SLA_POLICIES[TicketPriority.ALTA].hours == 48
    assert DEFAULT_SLA_POLICIES[TicketPriority.MEDIA].hours == 72
    assert DEFAULT_SLA_POLICIES[TicketPriority.BAIXA].hours == 120
    assert all(p.warn_hours == 12 for p in DEFAULT_SLA_POLICIES.values())


def test_compute_due_at() -> None:
    opened = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    policy = SlaPolicy(TicketPriority.URGENTE, hours=24)
    assert compute_due_at(opened, policy) == datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def test_sla_state_limites() -> None:
    due = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    assert sla_state(due - timedelta(hours=13), due, closed=False) is SlaState.NO_PRAZO
    assert sla_state(due - timedelta(hours=12), due, closed=False) is SlaState.VENCE_EM_BREVE
    assert sla_state(due - timedelta(minutes=1), due, closed=False) is SlaState.VENCE_EM_BREVE
    assert sla_state(due, due, closed=False) is SlaState.ATRASADO
    assert sla_state(due + timedelta(hours=1), due, closed=False) is SlaState.ATRASADO
    assert sla_state(due + timedelta(hours=1), due, closed=True) is SlaState.ENCERRADO


def test_missing_for_analysis() -> None:
    incompleto = _ticket()
    assert missing_for_analysis(incompleto, items_count=0) == ["cliente", "itens", "descricao"]
    completo = _ticket(customer_id=uuid4(), description="produto chegou quebrado")
    assert missing_for_analysis(completo, items_count=2) == []
    so_descricao_em_branco = _ticket(customer_id=uuid4(), description="   ")
    assert missing_for_analysis(so_descricao_em_branco, items_count=1) == ["descricao"]


def test_is_closed() -> None:
    assert not is_closed(_ticket())
    assert is_closed(_ticket(status=TicketStatus.CANCELADO))
