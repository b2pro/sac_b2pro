from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class NotificationType(StrEnum):
    ATRIBUICAO = "atribuicao"
    TRANSICAO = "transicao"
    COMENTARIO = "comentario"


@dataclass
class Notification:
    id: UUID
    user_id: UUID
    ticket_id: UUID
    # desnormalizado de proposito: o dropdown de notificacoes lista o numero
    # do ticket sem precisar de join, e number e imutavel apos a criacao do
    # ticket (TicketModel.number), entao a copia nunca diverge do original.
    ticket_number: int
    type: NotificationType
    title: str
    snippet: str | None = None
    actor_user_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None
