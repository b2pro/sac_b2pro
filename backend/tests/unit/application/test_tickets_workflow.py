from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.tickets_crud import CreateTicketInput, CreateTicketUseCase
from sac.application.use_cases.tickets_workflow import (
    ApproveTicketUseCase,
    CancelTicketUseCase,
    DeclineTicketUseCase,
    HoldForCustomerUseCase,
    ReopenTicketUseCase,
    ResumeTicketUseCase,
    SubmitTicketUseCase,
)
from sac.domain.errors import InvalidTransitionError, ValidationError
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketPriority, TicketStatus, TimelineEventType
from tests.unit.fakes import InMemoryCustomerRepository
from tests.unit.fakes_tickets import (
    InMemorySlaPolicyRepository,
    InMemoryTicketItemRepository,
    InMemoryTicketReadRepository,
    InMemoryTicketRepository,
    InMemoryTimelineRepository,
)

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)


class Env:
    def __init__(self) -> None:
        self.tickets = InMemoryTicketRepository()
        self.items = InMemoryTicketItemRepository()
        self.timeline = InMemoryTimelineRepository()

    async def novo_ticket(self, **kwargs: object) -> Ticket:
        create = CreateTicketUseCase(
            self.tickets,
            self.items,
            InMemoryCustomerRepository(),
            InMemorySlaPolicyRepository(),
            self.timeline,
            InMemoryTicketReadRepository(),
        )
        defaults = {
            "brand_id": uuid4(),
            "priority": TicketPriority.MEDIA,
            "customer_id": None,
            "description": "descricao do problema",
        }
        defaults.update(kwargs)  # type: ignore[arg-type]
        data = CreateTicketInput(**defaults)  # type: ignore[arg-type]
        ticket = await create.execute(ADMIN, data)
        return ticket

    async def ticket_completo(self) -> Ticket:
        ticket = await self.novo_ticket()
        ticket.customer_id = uuid4()
        from sac.domain.tickets import TicketItem

        await self.items.add(
            TicketItem(
                id=uuid4(),
                ticket_id=ticket.id,
                product_id=uuid4(),
                defect_type_id=uuid4(),
                quantity=1,
            )
        )
        return ticket


async def test_submit_exige_completude() -> None:
    env = Env()
    incompleto = await env.novo_ticket(description=None)
    submit = SubmitTicketUseCase(env.tickets, env.items, env.timeline)
    with pytest.raises(ValidationError) as exc:
        await submit.execute(ADMIN, incompleto.id)
    assert "faltando" in exc.value.details


async def test_fluxo_submit_approve() -> None:
    env = Env()
    ticket = await env.ticket_completo()
    submit = SubmitTicketUseCase(env.tickets, env.items, env.timeline)
    ticket = await submit.execute(ADMIN, ticket.id)
    assert ticket.status is TicketStatus.AGUARDANDO_ANALISE
    assert ticket.submitted_at is not None
    approve = ApproveTicketUseCase(env.tickets, env.timeline)
    ticket = await approve.execute(ADMIN, ticket.id, notes="ok")
    assert ticket.status is TicketStatus.APROVADO
    assert ticket.approved_at is not None
    assert ticket.decision_notes == "ok"
    transicoes = [e for e in env.timeline.events if e.type is TimelineEventType.TRANSICAO]
    assert len(transicoes) == 2


async def test_decline_exige_motivo_e_encerra() -> None:
    env = Env()
    ticket = await env.ticket_completo()
    await SubmitTicketUseCase(env.tickets, env.items, env.timeline).execute(ADMIN, ticket.id)
    decline = DeclineTicketUseCase(env.tickets, env.timeline)
    with pytest.raises(ValidationError):
        await decline.execute(ADMIN, ticket.id, reason="  ")
    ticket = await decline.execute(ADMIN, ticket.id, reason="fora de garantia")
    assert ticket.status is TicketStatus.DECLINADO
    assert ticket.declined_at is not None and ticket.closed_at is not None
    assert ticket.decision_notes == "fora de garantia"


async def test_approve_de_aberto_e_invalido() -> None:
    env = Env()
    ticket = await env.novo_ticket()
    with pytest.raises(InvalidTransitionError):
        await ApproveTicketUseCase(env.tickets, env.timeline).execute(ADMIN, ticket.id)


async def test_hold_resume_e_cancel() -> None:
    env = Env()
    ticket = await env.novo_ticket()
    hold = HoldForCustomerUseCase(env.tickets, env.timeline)
    ticket = await hold.execute(ADMIN, ticket.id)
    assert ticket.status is TicketStatus.AGUARDANDO_CLIENTE
    resume = ResumeTicketUseCase(env.tickets, env.timeline)
    ticket = await resume.execute(ADMIN, ticket.id)
    assert ticket.status is TicketStatus.ABERTO
    cancel = CancelTicketUseCase(env.tickets, env.timeline)
    ticket = await cancel.execute(ADMIN, ticket.id, reason="aberto por engano")
    assert ticket.status is TicketStatus.CANCELADO
    assert ticket.closed_at is not None
    assert ticket.decision_notes == "aberto por engano"
    with pytest.raises(InvalidTransitionError):
        await cancel.execute(ADMIN, ticket.id)


async def test_reopen_volta_para_aprovado_se_ja_aprovado_senao_aberto() -> None:
    env = Env()
    ticket = await env.ticket_completo()
    await SubmitTicketUseCase(env.tickets, env.items, env.timeline).execute(ADMIN, ticket.id)
    await ApproveTicketUseCase(env.tickets, env.timeline).execute(ADMIN, ticket.id)
    await CancelTicketUseCase(env.tickets, env.timeline).execute(ADMIN, ticket.id)
    reopen = ReopenTicketUseCase(env.tickets, env.timeline)
    ticket = await reopen.execute(ADMIN, ticket.id)
    assert ticket.status is TicketStatus.APROVADO
    assert ticket.closed_at is None

    nunca_aprovado = await env.novo_ticket()
    await CancelTicketUseCase(env.tickets, env.timeline).execute(ADMIN, nunca_aprovado.id)
    ticket2 = await reopen.execute(ADMIN, nunca_aprovado.id)
    assert ticket2.status is TicketStatus.ABERTO
