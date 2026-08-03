from datetime import UTC, datetime
from uuid import uuid4

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.domain.notifications import NotificationType
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketComment, TicketPriority, TicketStatus
from tests.unit.fakes_notifications import (
    InMemoryNotificationPublisher,
    InMemoryNotificationRepository,
)
from tests.unit.fakes_tickets import InMemoryTicketCommentRepository


def make_ticket(
    attendant_user_id=None,
    brand_id=None,
    ticket_id=None,
) -> Ticket:
    if ticket_id is None:
        ticket_id = uuid4()
    if brand_id is None:
        brand_id = uuid4()
    if attendant_user_id is None:
        attendant_user_id = uuid4()

    return Ticket(
        id=ticket_id,
        number=1,
        brand_id=brand_id,
        status=TicketStatus.ABERTO,
        priority=TicketPriority.MEDIA,
        attendant_user_id=attendant_user_id,
        opened_at=datetime.now(UTC),
        due_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
    )


def make_comment(ticket_id: str, author_user_id=None) -> TicketComment:
    if author_user_id is None:
        author_user_id = uuid4()

    return TicketComment(
        id=uuid4(),
        ticket_id=ticket_id,
        author_user_id=author_user_id,
        body="Test comment",
        created_at=datetime.now(UTC),
    )


async def test_notifica_atribuido_e_comentaristas_excluindo_ator() -> None:
    # Arrange
    attendant_a = uuid4()
    actor_b = uuid4()
    commenter_c = uuid4()

    ticket_id = uuid4()
    ticket = make_ticket(attendant_user_id=attendant_a, ticket_id=ticket_id)

    comments_repo = InMemoryTicketCommentRepository()
    comment_b = make_comment(ticket_id, actor_b)
    comment_c = make_comment(ticket_id, commenter_c)
    await comments_repo.add(comment_b)
    await comments_repo.add(comment_c)

    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor = TicketActor(user_id=actor_b, role=Role.ATENDENTE)

    # Act
    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.COMENTARIO,
        title="Nova atividade",
        snippet="Novo comentario",
    )

    # Assert
    assert len(notifications_repo.notifications) == 2
    recipient_ids = {n.user_id for n in notifications_repo.notifications}
    assert recipient_ids == {attendant_a, commenter_c}

    assert len(publisher.publish_calls) == 1
    tenant_slug, user_ids = publisher.publish_calls[0]
    assert tenant_slug == "test-tenant"
    assert sorted(user_ids) == sorted([attendant_a, commenter_c])


async def test_ator_unico_envolvido_nao_gera_nada() -> None:
    # Arrange
    actor_a = uuid4()
    ticket_id = uuid4()
    ticket = make_ticket(attendant_user_id=actor_a, ticket_id=ticket_id)

    comments_repo = InMemoryTicketCommentRepository()
    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor = TicketActor(user_id=actor_a, role=Role.ATENDENTE)

    # Act
    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.TRANSICAO,
        title="Ticket atualizado",
    )

    # Assert
    assert notifications_repo.add_many_call_count == 0
    assert len(publisher.publish_calls) == 0


async def test_destinatarios_deduplicados() -> None:
    # Arrange
    attendant_a = uuid4()
    actor_b = uuid4()

    ticket_id = uuid4()
    ticket = make_ticket(attendant_user_id=attendant_a, ticket_id=ticket_id)

    comments_repo = InMemoryTicketCommentRepository()
    # A comentou tambem
    comment_a = make_comment(ticket_id, attendant_a)
    await comments_repo.add(comment_a)

    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor = TicketActor(user_id=actor_b, role=Role.ATENDENTE)

    # Act
    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.COMENTARIO,
        title="Novo comentario",
    )

    # Assert
    assert len(notifications_repo.notifications) == 1
    assert notifications_repo.notifications[0].user_id == attendant_a

    assert len(publisher.publish_calls) == 1
    _, user_ids = publisher.publish_calls[0]
    assert user_ids == [attendant_a]


async def test_snippet_e_titulo_propagados() -> None:
    # Arrange
    attendant_a = uuid4()
    commenter_b = uuid4()
    actor_c = uuid4()

    ticket_id = uuid4()
    ticket = make_ticket(attendant_user_id=attendant_a, ticket_id=ticket_id)

    comments_repo = InMemoryTicketCommentRepository()
    comment_b = make_comment(ticket_id, commenter_b)
    await comments_repo.add(comment_b)

    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor = TicketActor(user_id=actor_c, role=Role.ATENDENTE)

    title = "Reatribuido"
    snippet = "Voce foi atribuido ao ticket"

    # Act
    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.ATRIBUICAO,
        title=title,
        snippet=snippet,
    )

    # Assert
    notifications = {n.user_id: n for n in notifications_repo.notifications}

    notif_a = notifications[attendant_a]
    assert notif_a.title == title
    assert notif_a.snippet == snippet
    assert notif_a.type == NotificationType.ATRIBUICAO
    assert notif_a.actor_user_id == actor_c
    assert notif_a.ticket_id == ticket_id
    assert notif_a.ticket_number == ticket.number

    notif_b = notifications[commenter_b]
    assert notif_b.title == title
    assert notif_b.snippet == snippet


async def test_only_recipient_enderaca_ignorando_atendente_e_comentaristas() -> None:
    # Fix round 1 da Task 3: atribuicao (decisao 3 do spec da Fase 4) e
    # enderecada a uma pessoa so, nao fan-out -- nem o atendente atual nem
    # comentaristas do ticket devem ser notificados junto.
    attendant_a = uuid4()
    commenter_b = uuid4()
    actor_c = uuid4()
    destinatario_d = uuid4()

    ticket_id = uuid4()
    ticket = make_ticket(attendant_user_id=attendant_a, ticket_id=ticket_id)

    comments_repo = InMemoryTicketCommentRepository()
    await comments_repo.add(make_comment(ticket_id, commenter_b))

    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor = TicketActor(user_id=actor_c, role=Role.ATENDENTE)

    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.ATRIBUICAO,
        title="Ticket atribuido a voce",
        only_recipient=destinatario_d,
    )

    assert len(notifications_repo.notifications) == 1
    assert notifications_repo.notifications[0].user_id == destinatario_d
    assert len(publisher.publish_calls) == 1
    assert publisher.publish_calls[0][1] == [destinatario_d]


async def test_only_recipient_igual_ao_ator_nao_notifica() -> None:
    ticket = make_ticket()
    comments_repo = InMemoryTicketCommentRepository()
    notifications_repo = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()

    fanout = NotificationFanout(
        notifications=notifications_repo,
        comments=comments_repo,
        publisher=publisher,
        tenant_slug="test-tenant",
    )

    actor_id = uuid4()
    actor = TicketActor(user_id=actor_id, role=Role.ATENDENTE)

    await fanout.notify(
        actor=actor,
        ticket=ticket,
        type_=NotificationType.ATRIBUICAO,
        title="Ticket atribuido a voce",
        only_recipient=actor_id,
    )

    assert notifications_repo.add_many_call_count == 0
    assert len(publisher.publish_calls) == 0
