from datetime import timedelta
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.customers import CustomerInput
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.application.use_cases.tickets_crud import (
    AddCommentUseCase,
    AddTicketItemUseCase,
    CreateTicketInput,
    CreateTicketUseCase,
    RemoveTicketItemUseCase,
    TicketItemInput,
    UpdateTicketInput,
    UpdateTicketItemUseCase,
    UpdateTicketUseCase,
)
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.notifications import NotificationType
from sac.domain.permissions import Role
from sac.domain.tickets import (
    Ticket,
    TicketComment,
    TicketPriority,
    TicketStatus,
    TimelineEventType,
)
from tests.unit.fakes import InMemoryCustomerRepository
from tests.unit.fakes_notifications import (
    InMemoryNotificationPublisher,
    InMemoryNotificationRepository,
)
from tests.unit.fakes_tickets import (
    InMemorySlaPolicyRepository,
    InMemoryTicketCommentRepository,
    InMemoryTicketItemRepository,
    InMemoryTicketReadRepository,
    InMemoryTicketRepository,
    InMemoryTimelineRepository,
)

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)

VALID_CPF = "39053344705"


def make_fanout(
    comments: InMemoryTicketCommentRepository | None = None,
) -> tuple[NotificationFanout, InMemoryNotificationRepository, InMemoryNotificationPublisher]:
    """Monta um NotificationFanout real sobre fakes em memoria.

    O parametro fanout dos use cases e obrigatorio (decisao do controller:
    uma dependencia opcional que desliga notificacoes silenciosamente e
    defeito), entao todo teste que constroi um use case de ticket precisa
    de um fanout, mesmo quando nao vai inspecionar as notificacoes geradas.
    """
    notifications = InMemoryNotificationRepository()
    publisher = InMemoryNotificationPublisher()
    fanout = NotificationFanout(
        notifications, comments or InMemoryTicketCommentRepository(), publisher, "test-tenant"
    )
    return fanout, notifications, publisher


def make_create_use_case() -> tuple[
    CreateTicketUseCase,
    InMemoryTicketRepository,
    InMemoryTicketItemRepository,
    InMemoryCustomerRepository,
    InMemoryTimelineRepository,
    InMemoryTicketReadRepository,
]:
    tickets = InMemoryTicketRepository()
    items = InMemoryTicketItemRepository()
    customers = InMemoryCustomerRepository()
    timeline = InMemoryTimelineRepository()
    reads = InMemoryTicketReadRepository()
    fanout, _, _ = make_fanout()
    use_case = CreateTicketUseCase(
        tickets, items, customers, InMemorySlaPolicyRepository(), timeline, reads, fanout
    )
    return use_case, tickets, items, customers, timeline, reads


async def test_criacao_parcial_com_defaults() -> None:
    use_case, _, _, _, timeline, reads = make_create_use_case()
    ticket = await use_case.execute(
        ATENDENTE, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    assert ticket.number == 1
    assert ticket.status is TicketStatus.ABERTO
    assert ticket.attendant_user_id == ATENDENTE.user_id
    assert ticket.due_at == ticket.opened_at + timedelta(hours=72)
    assert timeline.events[0].type is TimelineEventType.CRIACAO
    assert (ticket.id, ATENDENTE.user_id) in reads.reads
    second = await use_case.execute(
        ATENDENTE, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.URGENTE)
    )
    assert second.number == 2
    assert second.due_at == second.opened_at + timedelta(hours=24)


async def test_criacao_com_itens_e_cliente_inline_novo() -> None:
    use_case, _, items, customers, _, _ = make_create_use_case()
    data = CreateTicketInput(
        brand_id=uuid4(),
        priority=TicketPriority.ALTA,
        customer=CustomerInput(name="Maria", document=VALID_CPF),
        items=(TicketItemInput(product_id=uuid4(), defect_type_id=uuid4(), quantity=2),),
    )
    ticket = await use_case.execute(ADMIN, data)
    created = await customers.get_by_document(VALID_CPF)
    assert created is not None and ticket.customer_id == created.id
    assert await items.count(ticket.id) == 1


async def test_cliente_inline_existente_vincula_e_atualiza() -> None:
    use_case, _, _, customers, _, _ = make_create_use_case()
    first = await use_case.execute(
        ADMIN,
        CreateTicketInput(
            brand_id=uuid4(),
            priority=TicketPriority.MEDIA,
            customer=CustomerInput(name="Maria", document=VALID_CPF),
        ),
    )
    second = await use_case.execute(
        ADMIN,
        CreateTicketInput(
            brand_id=uuid4(),
            priority=TicketPriority.MEDIA,
            customer=CustomerInput(name="Maria Silva", document=VALID_CPF, city="Recife"),
        ),
    )
    assert second.customer_id == first.customer_id
    updated = await customers.get_by_document(VALID_CPF)
    assert updated is not None and updated.name == "Maria Silva" and updated.city == "Recife"


async def test_customer_id_inexistente_e_quantidade_invalida() -> None:
    use_case, _, _, _, _, _ = make_create_use_case()
    with pytest.raises(ValidationError):
        await use_case.execute(
            ADMIN,
            CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA, customer_id=uuid4()),
        )
    with pytest.raises(ValidationError):
        await use_case.execute(
            ADMIN,
            CreateTicketInput(
                brand_id=uuid4(),
                priority=TicketPriority.MEDIA,
                items=(TicketItemInput(product_id=uuid4(), defect_type_id=uuid4(), quantity=0),),
            ),
        )


async def test_customer_inline_e_customer_id_juntos_e_invalido() -> None:
    use_case, _, _, _, _, _ = make_create_use_case()
    with pytest.raises(ValidationError):
        await use_case.execute(
            ADMIN,
            CreateTicketInput(
                brand_id=uuid4(),
                priority=TicketPriority.MEDIA,
                customer=CustomerInput(name="Maria", document=VALID_CPF),
                customer_id=uuid4(),
            ),
        )


async def test_atendente_nao_cria_para_outro_admin_sim() -> None:
    use_case, _, _, _, _, _ = make_create_use_case()
    outro = uuid4()
    de_atendente = await use_case.execute(
        ATENDENTE,
        CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=outro),
    )
    assert de_atendente.attendant_user_id == ATENDENTE.user_id
    de_admin = await use_case.execute(
        ADMIN,
        CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=outro),
    )
    assert de_admin.attendant_user_id == outro


def make_update_use_case(
    tickets: InMemoryTicketRepository, fanout: NotificationFanout | None = None
) -> UpdateTicketUseCase:
    return UpdateTicketUseCase(
        tickets,
        InMemoryCustomerRepository(),
        InMemorySlaPolicyRepository(),
        InMemoryTimelineRepository(),
        fanout or make_fanout()[0],
    )


async def test_update_recalcula_sla_ao_mudar_prioridade() -> None:
    create, tickets, _, _, _, _ = make_create_use_case()
    ticket = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.BAIXA)
    )
    update = make_update_use_case(tickets)
    updated = await update.execute(
        ADMIN,
        ticket.id,
        UpdateTicketInput(
            brand_id=ticket.brand_id, priority=TicketPriority.URGENTE, description="quebrou"
        ),
    )
    assert updated.priority is TicketPriority.URGENTE
    assert updated.due_at == ticket.opened_at + timedelta(hours=24)
    assert updated.description == "quebrou"


async def test_atendente_nao_edita_ticket_alheio_nem_fora_de_estado_editavel() -> None:
    create, tickets, _, _, _, _ = make_create_use_case()
    de_outro = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    update = make_update_use_case(tickets)
    with pytest.raises(NotFoundError):
        await update.execute(
            ATENDENTE,
            de_outro.id,
            UpdateTicketInput(brand_id=de_outro.brand_id, priority=TicketPriority.MEDIA),
        )
    de_outro.status = TicketStatus.AGUARDANDO_ANALISE
    with pytest.raises(ConflictError):
        await update.execute(
            ADMIN,
            de_outro.id,
            UpdateTicketInput(brand_id=de_outro.brand_id, priority=TicketPriority.MEDIA),
        )


async def test_visualizador_ve_mas_nao_edita() -> None:
    create, tickets, _, _, _, _ = make_create_use_case()
    ticket = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    update = make_update_use_case(tickets)
    visualizador = TicketActor(user_id=uuid4(), role=Role.VISUALIZADOR)
    with pytest.raises(PermissionDeniedError):
        await update.execute(
            visualizador,
            ticket.id,
            UpdateTicketInput(brand_id=ticket.brand_id, priority=TicketPriority.MEDIA),
        )


async def _ticket_aberto(tickets: InMemoryTicketRepository) -> Ticket:
    fanout, _, _ = make_fanout()
    use_case = CreateTicketUseCase(
        tickets,
        InMemoryTicketItemRepository(),
        InMemoryCustomerRepository(),
        InMemorySlaPolicyRepository(),
        InMemoryTimelineRepository(),
        InMemoryTicketReadRepository(),
        fanout,
    )
    return await use_case.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )


async def test_item_add_update_remove_com_timeline() -> None:
    tickets = InMemoryTicketRepository()
    items = InMemoryTicketItemRepository()
    timeline = InMemoryTimelineRepository()
    ticket = await _ticket_aberto(tickets)
    add = AddTicketItemUseCase(tickets, items, timeline)
    item = await add.execute(
        ADMIN, ticket.id, TicketItemInput(product_id=uuid4(), defect_type_id=uuid4())
    )
    assert await items.count(ticket.id) == 1
    update = UpdateTicketItemUseCase(tickets, items, timeline)
    updated = await update.execute(
        ADMIN,
        ticket.id,
        item.id,
        TicketItemInput(product_id=item.product_id, defect_type_id=item.defect_type_id, quantity=5),
    )
    assert updated.quantity == 5
    remove = RemoveTicketItemUseCase(tickets, items, timeline)
    await remove.execute(ADMIN, ticket.id, item.id)
    assert await items.count(ticket.id) == 0
    types = [e.type for e in timeline.events]
    assert TimelineEventType.ITEM_ADICIONADO in types
    assert TimelineEventType.ITEM_ALTERADO in types
    assert TimelineEventType.ITEM_REMOVIDO in types


async def test_item_de_outro_ticket_da_404_e_estado_nao_editavel_409() -> None:
    tickets = InMemoryTicketRepository()
    items = InMemoryTicketItemRepository()
    timeline = InMemoryTimelineRepository()
    ticket = await _ticket_aberto(tickets)
    outro = await _ticket_aberto(tickets)
    add = AddTicketItemUseCase(tickets, items, timeline)
    item = await add.execute(
        ADMIN, ticket.id, TicketItemInput(product_id=uuid4(), defect_type_id=uuid4())
    )
    remove = RemoveTicketItemUseCase(tickets, items, timeline)
    with pytest.raises(NotFoundError):
        await remove.execute(ADMIN, outro.id, item.id)
    ticket.status = TicketStatus.APROVADO
    with pytest.raises(ConflictError):
        await add.execute(
            ADMIN, ticket.id, TicketItemInput(product_id=uuid4(), defect_type_id=uuid4())
        )


async def test_comentario_reply_e_bloqueio_em_encerrado() -> None:
    tickets = InMemoryTicketRepository()
    comments = InMemoryTicketCommentRepository()
    reads = InMemoryTicketReadRepository()
    ticket = await _ticket_aberto(tickets)
    before = ticket.last_activity_at
    fanout, _, _ = make_fanout(comments)
    use_case = AddCommentUseCase(tickets, comments, reads, fanout)
    first = await use_case.execute(ADMIN, ticket.id, "primeiro comentario")
    reply = await use_case.execute(ADMIN, ticket.id, "resposta", reply_to_id=first.id)
    assert reply.reply_to_id == first.id
    assert ticket.last_activity_at >= before
    assert (ticket.id, ADMIN.user_id) in reads.reads
    with pytest.raises(ValidationError):
        await use_case.execute(ADMIN, ticket.id, "   ")
    with pytest.raises(ValidationError):
        await use_case.execute(ADMIN, ticket.id, "reply invalido", reply_to_id=uuid4())
    ticket.status = TicketStatus.FINALIZADO
    with pytest.raises(ConflictError):
        await use_case.execute(ADMIN, ticket.id, "nao pode")


async def test_criacao_com_atendente_de_terceiro_gera_timeline_e_notificacao() -> None:
    tickets = InMemoryTicketRepository()
    items = InMemoryTicketItemRepository()
    customers = InMemoryCustomerRepository()
    timeline = InMemoryTimelineRepository()
    reads = InMemoryTicketReadRepository()
    fanout, notifications, publisher = make_fanout()
    use_case = CreateTicketUseCase(
        tickets, items, customers, InMemorySlaPolicyRepository(), timeline, reads, fanout
    )
    terceiro = uuid4()

    ticket = await use_case.execute(
        ADMIN,
        CreateTicketInput(
            brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=terceiro
        ),
    )

    assert ticket.attendant_user_id == terceiro
    atribuicoes = [e for e in timeline.events if e.type is TimelineEventType.ATRIBUICAO]
    assert len(atribuicoes) == 1

    assert len(notifications.notifications) == 1
    notif = notifications.notifications[0]
    assert notif.user_id == terceiro
    assert notif.type is NotificationType.ATRIBUICAO
    assert notif.title == f"Ticket #{ticket.number} atribuido a voce"
    assert notif.actor_user_id == ADMIN.user_id
    assert len(publisher.publish_calls) == 1


async def test_criacao_sem_terceiro_nao_gera_atribuicao() -> None:
    use_case, _, _, _, timeline, _ = make_create_use_case()
    await use_case.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    assert not any(e.type is TimelineEventType.ATRIBUICAO for e in timeline.events)


async def test_update_troca_atendente_sem_permissao_levanta_permission_denied() -> None:
    tickets = InMemoryTicketRepository()
    create = CreateTicketUseCase(
        tickets,
        InMemoryTicketItemRepository(),
        InMemoryCustomerRepository(),
        InMemorySlaPolicyRepository(),
        InMemoryTimelineRepository(),
        InMemoryTicketReadRepository(),
        make_fanout()[0],
    )
    ticket = await create.execute(
        ATENDENTE, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    update = make_update_use_case(tickets)

    with pytest.raises(PermissionDeniedError):
        await update.execute(
            ATENDENTE,
            ticket.id,
            UpdateTicketInput(
                brand_id=ticket.brand_id, priority=ticket.priority, attendant_user_id=uuid4()
            ),
        )


async def test_update_troca_atendente_com_permissao_notifica_novo_atendente() -> None:
    create, tickets, _, _, timeline, _ = make_create_use_case()
    ticket = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    antigo_atendente = ticket.attendant_user_id
    novo_atendente = uuid4()
    fanout, notifications, publisher = make_fanout()
    update = UpdateTicketUseCase(
        tickets, InMemoryCustomerRepository(), InMemorySlaPolicyRepository(), timeline, fanout
    )

    updated = await update.execute(
        ADMIN,
        ticket.id,
        UpdateTicketInput(
            brand_id=ticket.brand_id, priority=ticket.priority, attendant_user_id=novo_atendente
        ),
    )

    assert updated.attendant_user_id == novo_atendente
    atribuicoes = [e for e in timeline.events if e.type is TimelineEventType.ATRIBUICAO]
    assert len(atribuicoes) == 1
    assert atribuicoes[0].old_value == str(antigo_atendente)
    assert atribuicoes[0].new_value == str(novo_atendente)

    assert len(notifications.notifications) == 1
    notif = notifications.notifications[0]
    assert notif.user_id == novo_atendente
    assert notif.type is NotificationType.ATRIBUICAO
    assert notif.title == f"Ticket #{ticket.number} atribuido a voce"
    assert notif.actor_user_id == ADMIN.user_id
    assert len(publisher.publish_calls) == 1


async def test_update_reatribuicao_notifica_so_o_novo_atendente_nao_comentaristas() -> None:
    # Fix round 1, achado 1: a notificacao de atribuicao e enderecada (spec da
    # Fase 4, decisao 3) -- um comentarista antigo do ticket NAO pode receber
    # "atribuido a voce" quando quem foi de fato atribuido e outra pessoa.
    create, tickets, _, _, timeline, _ = make_create_use_case()
    ticket = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    comments = InMemoryTicketCommentRepository()
    comentarista_anterior = uuid4()
    await comments.add(
        TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=comentarista_anterior,
            body="comentario antigo",
        )
    )
    novo_atendente = uuid4()
    fanout, notifications, publisher = make_fanout(comments)
    update = UpdateTicketUseCase(
        tickets, InMemoryCustomerRepository(), InMemorySlaPolicyRepository(), timeline, fanout
    )

    await update.execute(
        ADMIN,
        ticket.id,
        UpdateTicketInput(
            brand_id=ticket.brand_id, priority=ticket.priority, attendant_user_id=novo_atendente
        ),
    )

    assert len(notifications.notifications) == 1
    assert notifications.notifications[0].user_id == novo_atendente
    assert len(publisher.publish_calls) == 1
    assert publisher.publish_calls[0][1] == [novo_atendente]


async def test_update_troca_atendente_para_o_proprio_ator_nao_notifica() -> None:
    create, tickets, _, _, _, _ = make_create_use_case()
    terceiro = uuid4()
    ticket = await create.execute(
        ADMIN,
        CreateTicketInput(
            brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=terceiro
        ),
    )
    fanout, notifications, publisher = make_fanout()
    update = make_update_use_case(tickets, fanout)

    updated = await update.execute(
        ADMIN,
        ticket.id,
        UpdateTicketInput(
            brand_id=ticket.brand_id, priority=ticket.priority, attendant_user_id=ADMIN.user_id
        ),
    )

    assert updated.attendant_user_id == ADMIN.user_id
    # a troca aconteceu (timeline registra), mas ninguem e notificado porque
    # o unico destinatario seria o proprio ator.
    assert notifications.notifications == []
    assert publisher.publish_calls == []


async def test_update_sem_attendant_user_id_nao_mexe_no_atendente() -> None:
    create, tickets, _, _, _, _ = make_create_use_case()
    ticket = await create.execute(
        ADMIN, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
    )
    original = ticket.attendant_user_id
    update = make_update_use_case(tickets)

    updated = await update.execute(
        ADMIN, ticket.id, UpdateTicketInput(brand_id=ticket.brand_id, priority=ticket.priority)
    )

    assert updated.attendant_user_id == original


async def test_comentario_notifica_atendente_e_comentaristas_anteriores_com_snippet() -> None:
    tickets = InMemoryTicketRepository()
    comments = InMemoryTicketCommentRepository()
    reads = InMemoryTicketReadRepository()
    ticket = await _ticket_aberto(tickets)  # atendente == ADMIN

    comentarista_anterior = uuid4()
    await comments.add(
        TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=comentarista_anterior,
            body="comentario antigo",
        )
    )

    fanout, notifications, publisher = make_fanout(comments)
    use_case = AddCommentUseCase(tickets, comments, reads, fanout)
    # precisa de VER_TODOS_TICKETS pra sequer enxergar um ticket atendido por
    # outra pessoa (get_ticket_or_404); um atendente comum tomaria 404 aqui.
    autor = TicketActor(user_id=uuid4(), role=Role.SUPERVISOR)
    corpo = "novo comentario " * 20  # garante corpo longo o bastante pra testar o corte do snippet

    await use_case.execute(autor, ticket.id, corpo)

    assert len(notifications.notifications) == 2
    recipients = {n.user_id for n in notifications.notifications}
    assert recipients == {ADMIN.user_id, comentarista_anterior}
    for notif in notifications.notifications:
        assert notif.type is NotificationType.COMENTARIO
        assert notif.title == f"Novo comentario no ticket #{ticket.number}"
        assert notif.snippet == corpo.strip()[:200]
        assert notif.actor_user_id == autor.user_id
    assert len(publisher.publish_calls) == 1
