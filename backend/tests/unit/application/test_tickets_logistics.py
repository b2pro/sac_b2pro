from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.application.use_cases.tickets_crud import CreateTicketInput, CreateTicketUseCase
from sac.application.use_cases.tickets_workflow import (
    ApproveTicketUseCase,
    DeleteReverseUseCase,
    FinalizeTicketUseCase,
    ReceiveProductUseCase,
    RegisterReverseUseCase,
    SetWarrantyUseCase,
    SubmitTicketUseCase,
)
from sac.domain.errors import (
    ConflictError,
    InvalidTransitionError,
    ValidationError,
)
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketItem, TicketPriority, TicketStatus
from tests.unit.fakes import InMemoryCustomerRepository
from tests.unit.fakes_notifications import (
    InMemoryNotificationPublisher,
    InMemoryNotificationRepository,
)
from tests.unit.fakes_tickets import (
    InMemoryReverseCodeRepository,
    InMemorySlaPolicyRepository,
    InMemoryTicketCommentRepository,
    InMemoryTicketItemRepository,
    InMemoryTicketReadRepository,
    InMemoryTicketRepository,
    InMemoryTimelineRepository,
)

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)


def _fanout() -> NotificationFanout:
    # dependencia obrigatoria dos use cases de ticket (ver decisao do
    # controller na Task 3); estes testes nao inspecionam notificacoes,
    # entao um fanout descartavel sobre fakes basta.
    return NotificationFanout(
        InMemoryNotificationRepository(),
        InMemoryTicketCommentRepository(),
        InMemoryNotificationPublisher(),
        "test-tenant",
    )


class Env:
    def __init__(self) -> None:
        self.tickets = InMemoryTicketRepository()
        self.items = InMemoryTicketItemRepository()
        self.timeline = InMemoryTimelineRepository()
        self.reverses = InMemoryReverseCodeRepository()

    async def ticket_aprovado(self, actor: TicketActor = ADMIN) -> Ticket:
        create = CreateTicketUseCase(
            self.tickets,
            self.items,
            InMemoryCustomerRepository(),
            InMemorySlaPolicyRepository(),
            self.timeline,
            InMemoryTicketReadRepository(),
            _fanout(),
        )
        ticket = await create.execute(
            actor,
            CreateTicketInput(
                brand_id=uuid4(), priority=TicketPriority.MEDIA, description="defeito"
            ),
        )
        ticket.customer_id = uuid4()
        await self.items.add(
            TicketItem(
                id=uuid4(),
                ticket_id=ticket.id,
                product_id=uuid4(),
                defect_type_id=uuid4(),
                quantity=1,
            )
        )
        await SubmitTicketUseCase(self.tickets, self.items, self.timeline, _fanout()).execute(
            actor, ticket.id
        )
        return await ApproveTicketUseCase(self.tickets, self.timeline, _fanout()).execute(
            ADMIN, ticket.id
        )


async def test_reverso_move_e_excluir_ultimo_volta() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout())
    with pytest.raises(ValidationError):
        await register.execute(ADMIN, ticket.id, code="   ")
    reverse = await register.execute(ADMIN, ticket.id, code="BR123")
    assert ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
    second = await register.execute(ADMIN, ticket.id, code="BR456")
    assert ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
    delete = DeleteReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout())
    await delete.execute(ADMIN, ticket.id, second.id)
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.AGUARDANDO_ENVIO_REVERSO  # type: ignore[union-attr]
    await delete.execute(ADMIN, ticket.id, reverse.id)
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.APROVADO  # type: ignore[union-attr]


async def test_reverso_em_estado_errado_e_invalido() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    ticket.status = TicketStatus.ABERTO
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout())
    with pytest.raises(InvalidTransitionError):
        await register.execute(ADMIN, ticket.id, code="BR123")


async def test_recebimento_e_finalizacao_com_solucao() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    await RegisterReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout()).execute(
        ADMIN, ticket.id, code="BR123"
    )
    ticket = await ReceiveProductUseCase(env.tickets, env.timeline, _fanout()).execute(
        ADMIN, ticket.id
    )
    assert ticket.status is TicketStatus.PRODUTO_RECEBIDO
    solution = uuid4()
    ticket = await FinalizeTicketUseCase(env.tickets, env.timeline, _fanout()).execute(
        ADMIN, ticket.id, solution_type_id=solution, notes="troca feita"
    )
    assert ticket.status is TicketStatus.FINALIZADO
    assert ticket.solution_type_id == solution
    assert ticket.final_notes == "troca feita"
    assert ticket.closed_at is not None


async def test_finalizacao_direta_de_aprovado() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    ticket = await FinalizeTicketUseCase(env.tickets, env.timeline, _fanout()).execute(
        ADMIN, ticket.id, solution_type_id=uuid4()
    )
    assert ticket.status is TicketStatus.FINALIZADO


async def test_garantia_nao_muda_status_e_bloqueia_encerrado() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    warranty = SetWarrantyUseCase(env.tickets, env.timeline, _fanout())
    ticket = await warranty.execute(ADMIN, ticket.id, order_code="TINY-1", tracking_code="RA1")
    assert ticket.status is TicketStatus.APROVADO
    assert ticket.warranty_order_code == "TINY-1"
    assert ticket.warranty_tracking_code == "RA1"
    ticket.status = TicketStatus.FINALIZADO
    with pytest.raises(ConflictError):
        await warranty.execute(ADMIN, ticket.id, order_code="TINY-2")


async def test_atendente_nao_opera_ticket_alheio() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout())
    # atendente nem enxerga ticket de outro atendente: 404
    from sac.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await register.execute(ATENDENTE, ticket.id, code="BR999")


async def test_atendente_opera_o_proprio() -> None:
    env = Env()
    ticket = await env.ticket_aprovado(actor=ATENDENTE)
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline, _fanout())
    await register.execute(ATENDENTE, ticket.id, code="BR777")
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.AGUARDANDO_ENVIO_REVERSO  # type: ignore[union-attr]
