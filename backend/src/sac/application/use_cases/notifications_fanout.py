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

    Determina quem recebe notificação baseado em: atendente atual e
    comentaristas (fan-out), ou um unico destinatario enderecado quando
    `only_recipient` e informado. Exclui o ator de notificações para si mesmo.
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
        only_recipient: UUID | None = None,
    ) -> None:
        """Cria e publica notificações para os destinatarios do evento.

        Por padrao (fan-out, usado por transicoes e comentarios) o conjunto de
        destinatarios inclui:
        - Atendente atual (ticket.attendant_user_id)
        - Todos os autores de comentários no ticket
        - Exclui o ator (quem dispara a ação)

        Quando `only_recipient` e informado (usado pela atribuicao — decisao 3
        do spec da Fase 4: "atribuicao notifica o novo atendente", enderecada,
        nao fan-out), o UNICO candidato a destinatario e essa pessoa; nem o
        atendente atual do ticket nem os comentaristas sao consultados. Ainda
        assim o ator continua excluido, entao `only_recipient == actor.user_id`
        resulta em zero destinatarios e nenhuma escrita/publish.

        Se nenhum destinatario restante, nada é criado.

        Args:
            actor: Quem dispara a ação (excluído de notificações)
            ticket: Ticket afetado
            type_: Tipo de notificação (ATRIBUICAO, TRANSICAO, COMENTARIO)
            title: Título da notificação
            snippet: Resumo opcional da mudança
            only_recipient: quando informado, restringe a notificacao a essa
                unica pessoa (atribuicao enderecada), sem consultar comentarios
        """
        if only_recipient is not None:
            recipients: set[UUID] = {only_recipient}
        else:
            recipients = {ticket.attendant_user_id}
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
