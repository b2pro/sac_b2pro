from enum import StrEnum

from sac.domain.errors import InvalidTransitionError


class TicketStatus(StrEnum):
    ABERTO = "aberto"
    AGUARDANDO_CLIENTE = "aguardando_cliente"
    AGUARDANDO_ANALISE = "aguardando_analise"
    APROVADO = "aprovado"
    AGUARDANDO_ENVIO_REVERSO = "aguardando_envio_reverso"
    PRODUTO_RECEBIDO = "produto_recebido"
    FINALIZADO = "finalizado"
    DECLINADO = "declinado"
    CANCELADO = "cancelado"


CLOSED_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.FINALIZADO, TicketStatus.DECLINADO, TicketStatus.CANCELADO}
)

VALID_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.ABERTO: frozenset(
        {TicketStatus.AGUARDANDO_CLIENTE, TicketStatus.AGUARDANDO_ANALISE, TicketStatus.CANCELADO}
    ),
    TicketStatus.AGUARDANDO_CLIENTE: frozenset(
        {TicketStatus.ABERTO, TicketStatus.AGUARDANDO_ANALISE, TicketStatus.CANCELADO}
    ),
    TicketStatus.AGUARDANDO_ANALISE: frozenset(
        {TicketStatus.APROVADO, TicketStatus.DECLINADO, TicketStatus.CANCELADO}
    ),
    TicketStatus.APROVADO: frozenset(
        {
            TicketStatus.AGUARDANDO_ENVIO_REVERSO,
            TicketStatus.FINALIZADO,
            TicketStatus.CANCELADO,
        }
    ),
    TicketStatus.AGUARDANDO_ENVIO_REVERSO: frozenset(
        {TicketStatus.PRODUTO_RECEBIDO, TicketStatus.APROVADO, TicketStatus.CANCELADO}
    ),
    TicketStatus.PRODUTO_RECEBIDO: frozenset({TicketStatus.FINALIZADO, TicketStatus.CANCELADO}),
    TicketStatus.FINALIZADO: frozenset({TicketStatus.APROVADO, TicketStatus.ABERTO}),
    TicketStatus.DECLINADO: frozenset({TicketStatus.APROVADO, TicketStatus.ABERTO}),
    TicketStatus.CANCELADO: frozenset({TicketStatus.APROVADO, TicketStatus.ABERTO}),
}


def ensure_transition(current: TicketStatus, target: TicketStatus) -> None:
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"transicao invalida: {current} -> {target}",
            details={"de": current, "para": target},
        )
