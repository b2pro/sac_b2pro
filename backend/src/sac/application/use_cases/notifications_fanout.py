from datetime import UTC, datetime
from uuid import UUID, uuid4

from sac.application.ports_notifications import (
    NotificationPublisher,
    NotificationRepository,
)
from sac.application.ports_tickets import TicketActor, TicketCommentRepository
from sac.domain.notifications import Notification, NotificationType
from sac.domain.tickets import Ticket


class NotificationFanout:
    """Serviço que centraliza a lógica de destinatários de notificações.

    Determina quem recebe notificação baseado em: atendente atual, comentaristas
    e destinatarios extras. Exclui o ator de notificações para si mesmo.
    """

    def __init__(
        self,
        notifications: NotificationRepository,
        comments: TicketCommentRepository,
        publisher: NotificationPublisher,
        tenant_slug: str,
    ) -> None:
        self._notifications = notifications
        self._comments = comments
        self._publisher = publisher
        self._tenant_slug = tenant_slug

    async def notify(
        self,
        actor: TicketActor,
        ticket: Ticket,
        type_: NotificationType,
        title: str,
        snippet: str | None = None,
        extra_recipient: UUID | None = None,
    ) -> None:
        """Cria e publica notificações para destinatarios relevantes do ticket.

        O conjunto de destinatarios inclui:
        - Atendente atual (ticket.attendant_user_id)
        - Destinatario extra se fornecido (para futuras reatribuições)
        - Todos os autores de comentários no ticket
        - Exclui o ator (quem dispara a ação)

        Se nenhum destinatario restante, nada é criado.

        Args:
            actor: Quem dispara a ação (excluído de notificações)
            ticket: Ticket afetado
            type_: Tipo de notificação (ATRIBUICAO, TRANSICAO, COMENTARIO)
            title: Título da notificação
            snippet: Resumo opcional da mudança
            extra_recipient: UUID adicional de destinatario (ex: atendente anterior)
        """
        recipients: set[UUID] = {ticket.attendant_user_id}
        if extra_recipient is not None:
            recipients.add(extra_recipient)

        for comment in await self._comments.list_by_ticket(ticket.id):
            recipients.add(comment.author_user_id)

        recipients.discard(actor.user_id)

        if not recipients:
            return

        now = datetime.now(UTC)
        sorted_recipients = sorted(recipients)

        await self._notifications.add_many(
            [
                Notification(
                    id=uuid4(),
                    user_id=uid,
                    ticket_id=ticket.id,
                    ticket_number=ticket.number,
                    type=type_,
                    title=title,
                    snippet=snippet,
                    actor_user_id=actor.user_id,
                    created_at=now,
                )
                for uid in sorted_recipients
            ]
        )

        await self._publisher.publish(self._tenant_slug, sorted_recipients)
