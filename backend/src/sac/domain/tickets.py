from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

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


class TicketPriority(StrEnum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


@dataclass(frozen=True)
class SlaPolicy:
    priority: TicketPriority
    hours: int
    warn_hours: int = 12


DEFAULT_SLA_POLICIES: dict[TicketPriority, SlaPolicy] = {
    TicketPriority.URGENTE: SlaPolicy(TicketPriority.URGENTE, hours=24),
    TicketPriority.ALTA: SlaPolicy(TicketPriority.ALTA, hours=48),
    TicketPriority.MEDIA: SlaPolicy(TicketPriority.MEDIA, hours=72),
    TicketPriority.BAIXA: SlaPolicy(TicketPriority.BAIXA, hours=120),
}


class SlaState(StrEnum):
    NO_PRAZO = "no_prazo"
    VENCE_EM_BREVE = "vence_em_breve"
    ATRASADO = "atrasado"
    ENCERRADO = "encerrado"


def compute_due_at(opened_at: datetime, policy: SlaPolicy) -> datetime:
    return opened_at + timedelta(hours=policy.hours)


def sla_state(now: datetime, due_at: datetime, closed: bool, warn_hours: int = 12) -> SlaState:
    if closed:
        return SlaState.ENCERRADO
    if now >= due_at:
        return SlaState.ATRASADO
    if due_at - now <= timedelta(hours=warn_hours):
        return SlaState.VENCE_EM_BREVE
    return SlaState.NO_PRAZO


class TimelineEventType(StrEnum):
    CRIACAO = "criacao"
    TRANSICAO = "transicao"
    PRIORIDADE_ALTERADA = "prioridade_alterada"
    EDICAO = "edicao"
    ITEM_ADICIONADO = "item_adicionado"
    ITEM_ALTERADO = "item_alterado"
    ITEM_REMOVIDO = "item_removido"
    REVERSO_REGISTRADO = "reverso_registrado"
    REVERSO_EXCLUIDO = "reverso_excluido"
    GARANTIA_REGISTRADA = "garantia_registrada"


@dataclass
class Ticket:
    id: UUID
    number: int
    brand_id: UUID
    status: TicketStatus
    priority: TicketPriority
    attendant_user_id: UUID
    opened_at: datetime
    due_at: datetime
    last_activity_at: datetime
    customer_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = None
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None
    decision_notes: str | None = None
    final_notes: str | None = None
    solution_type_id: UUID | None = None
    warranty_order_code: str | None = None
    warranty_tracking_code: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    declined_at: datetime | None = None
    closed_at: datetime | None = None
    deleted_at: datetime | None = None


@dataclass
class TicketItem:
    id: UUID
    ticket_id: UUID
    product_id: UUID
    defect_type_id: UUID
    quantity: int


@dataclass
class TicketComment:
    id: UUID
    ticket_id: UUID
    author_user_id: UUID
    body: str
    reply_to_id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class TicketTimelineEvent:
    id: UUID
    ticket_id: UUID
    type: TimelineEventType
    title: str
    old_value: str | None = None
    new_value: str | None = None
    author_user_id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class ReverseCode:
    id: UUID
    ticket_id: UUID
    code: str
    author_user_id: UUID | None = None
    created_at: datetime | None = None


def is_closed(ticket: Ticket) -> bool:
    return ticket.status in CLOSED_STATUSES


def missing_for_analysis(ticket: Ticket, items_count: int) -> list[str]:
    missing: list[str] = []
    if ticket.customer_id is None:
        missing.append("cliente")
    if items_count == 0:
        missing.append("itens")
    if not (ticket.description or "").strip():
        missing.append("descricao")
    return missing
