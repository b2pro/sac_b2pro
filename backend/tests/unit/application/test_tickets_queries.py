from uuid import uuid4

from sac.application.ports_tickets import TicketActor, TicketFilters
from sac.application.use_cases.notifications_fanout import NotificationFanout
from sac.application.use_cases.tickets_crud import (
    AddCommentUseCase,
    CreateTicketInput,
    CreateTicketUseCase,
)
from sac.application.use_cases.tickets_queries import (
    GetTicketDetailUseCase,
    ListTicketsUseCase,
    MarkTicketUnreadUseCase,
)
from sac.domain.permissions import Role
from sac.domain.tickets import SlaState, Ticket, TicketPriority
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
    InMemoryUserDirectory,
)


def _fanout(comments: InMemoryTicketCommentRepository | None = None) -> NotificationFanout:
    # dependencia obrigatoria dos use cases de ticket (ver decisao do
    # controller na Task 3); estes testes nao inspecionam notificacoes,
    # entao um fanout descartavel sobre fakes basta.
    return NotificationFanout(
        InMemoryNotificationRepository(),
        comments or InMemoryTicketCommentRepository(),
        InMemoryNotificationPublisher(),
        "test-tenant",
    )


ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)
VISUALIZADOR = TicketActor(user_id=uuid4(), role=Role.VISUALIZADOR)


class Env:
    def __init__(self) -> None:
        self.tickets = InMemoryTicketRepository()
        self.items = InMemoryTicketItemRepository()
        self.comments = InMemoryTicketCommentRepository()
        self.timeline = InMemoryTimelineRepository()
        self.reverses = InMemoryReverseCodeRepository()
        self.reads = InMemoryTicketReadRepository()
        self.customers = InMemoryCustomerRepository()
        self.users = InMemoryUserDirectory({ADMIN.user_id: "Admin", ATENDENTE.user_id: "Atendente"})

    async def novo_ticket(self, actor: TicketActor) -> Ticket:
        create = CreateTicketUseCase(
            self.tickets,
            self.items,
            self.customers,
            InMemorySlaPolicyRepository(),
            self.timeline,
            self.reads,
            _fanout(self.comments),
        )
        return await create.execute(
            actor, CreateTicketInput(brand_id=uuid4(), priority=TicketPriority.MEDIA)
        )


async def test_atendente_so_lista_os_seus_e_nomes_preenchidos() -> None:
    env = Env()
    await env.novo_ticket(ADMIN)
    await env.novo_ticket(ATENDENTE)
    use_case = ListTicketsUseCase(env.tickets, env.users)
    rows, total = await use_case.execute(ATENDENTE, TicketFilters())
    assert total == 1
    assert rows[0].ticket.attendant_user_id == ATENDENTE.user_id
    assert rows[0].attendant_name == "Atendente"
    rows_admin, total_admin = await use_case.execute(ADMIN, TicketFilters())
    assert total_admin == 2


async def test_visualizador_lista_tudo_e_super_sem_papel_barrado() -> None:
    env = Env()
    await env.novo_ticket(ADMIN)
    use_case = ListTicketsUseCase(env.tickets, env.users)
    _, total = await use_case.execute(VISUALIZADOR, TicketFilters())
    assert total == 1


async def test_detalhe_marca_lido_e_calcula_sla() -> None:
    env = Env()
    ticket = await env.novo_ticket(ADMIN)
    detail_use_case = GetTicketDetailUseCase(
        env.tickets,
        env.items,
        env.comments,
        env.timeline,
        env.reverses,
        env.reads,
        env.customers,
        env.users,
    )
    outro_leitor = TicketActor(user_id=uuid4(), role=Role.SUPERVISOR)
    detail = await detail_use_case.execute(outro_leitor, ticket.id)
    assert detail.sla is SlaState.NO_PRAZO
    assert detail.ticket.number == ticket.number
    assert (ticket.id, outro_leitor.user_id) in env.reads.reads
    assert detail.user_names[ADMIN.user_id] == "Admin"


async def test_detalhe_com_comentarios_e_mark_unread() -> None:
    env = Env()
    ticket = await env.novo_ticket(ADMIN)
    await AddCommentUseCase(env.tickets, env.comments, env.reads, _fanout(env.comments)).execute(
        ADMIN, ticket.id, "olha isso"
    )
    detail_use_case = GetTicketDetailUseCase(
        env.tickets,
        env.items,
        env.comments,
        env.timeline,
        env.reverses,
        env.reads,
        env.customers,
        env.users,
    )
    detail = await detail_use_case.execute(ADMIN, ticket.id)
    assert len(detail.comments) == 1
    unread = MarkTicketUnreadUseCase(env.tickets, env.reads)
    await unread.execute(ADMIN, ticket.id)
    assert (ticket.id, ADMIN.user_id) not in env.reads.reads
