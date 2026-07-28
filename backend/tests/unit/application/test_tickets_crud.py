from datetime import timedelta
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.customers import CustomerInput
from sac.application.use_cases.tickets_crud import (
    CreateTicketInput,
    CreateTicketUseCase,
    TicketItemInput,
    UpdateTicketInput,
    UpdateTicketUseCase,
)
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.permissions import Role
from sac.domain.tickets import TicketPriority, TicketStatus, TimelineEventType
from tests.unit.fakes import InMemoryCustomerRepository
from tests.unit.fakes_tickets import (
    InMemorySlaPolicyRepository,
    InMemoryTicketItemRepository,
    InMemoryTicketReadRepository,
    InMemoryTicketRepository,
    InMemoryTimelineRepository,
)

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)

VALID_CPF = "39053344705"


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
    use_case = CreateTicketUseCase(
        tickets, items, customers, InMemorySlaPolicyRepository(), timeline, reads
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


def make_update_use_case(tickets: InMemoryTicketRepository) -> UpdateTicketUseCase:
    return UpdateTicketUseCase(
        tickets,
        InMemoryCustomerRepository(),
        InMemorySlaPolicyRepository(),
        InMemoryTimelineRepository(),
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
