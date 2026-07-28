# Fase 2A (Tickets — core) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Core de tickets por tenant: máquina de estados explícita (um use case por transição), numeração por sequence nativa, TicketItem como fonte única de verdade, SLA por prioridade, comentários com reply, timeline, lido/não lido, códigos reversos e garantia; front com lista, detalhe (2/3 + 1/3, uma ação primária contextual) e criação.

**Architecture:** Mesma Clean Architecture das fases anteriores (`interface -> application -> domain`; `infrastructure` implementa ports). Novidades: tabela declarativa de transições no domínio (`VALID_TRANSITIONS` + `ensure_transition`), numeração via `Sequence` do SQLAlchemy traduzida por `schema_translate_map`, e repositório de tickets com mapeamento de `IntegrityError` por nome de constraint (dívida da Fase 1).

**Tech Stack:** o existente (FastAPI, SQLAlchemy 2 async, Alembic, pytest; React + TanStack Query + shadcn/ui + sonner).

**Spec:** `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-2a-tickets-design.md`.

## Global Constraints

- PROIBIDO usar emojis em código, comentários, commits, UI, documentação e mensagens.
- Clean Architecture: `domain` e `application` são Python puro (sem FastAPI/SQLAlchemy/Pydantic); `infrastructure` implementa os ports.
- TDD no backend: teste antes da implementação em toda tarefa de backend.
- SEM CI. Antes de CADA commit rodar localmente e exigir sucesso:
  - Backend (em `backend/`): `uv run ruff format .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
  - Frontend (em `frontend/`): `pnpm lint` e `pnpm build`.
- Testes de integração exigem o Postgres do compose de pé (`docker compose up -d db` na raiz).
- Toda tarefa de frontend (Tasks 13-17) DEVE invocar o skill `frontend-design` antes de escrever UI e seguir `docs/identidade-visual.md` (número de ticket, documentos, códigos e timestamps em `font-mono`; Paprika APENAS em ação primária, SLA apertado e número do ticket; lucide `strokeWidth={1.5}`, 16px em tabelas / 20px em botões; borda esquerda de 3px na cor do status em cards/linhas de ticket; trilha de status segmentada — NÃO stepper com bolinhas; empty states de texto direto; zero sombra decorativa).
- Commits em português, imperativo, sem prefixo convencional, corpo terminando com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Não existe DELETE de ticket. Ticket errado vira `cancelado`. Nenhum campo de produto/defeito duplicado em `tickets` (TicketItem é a fonte única).
- Rotas de transição são POSTs dedicados; NENHUMA rota genérica de troca de status.
- Erros seguem o handler único: 401 sem token; 403 sem permissão; 404 inexistente/fora do escopo de visão; 409 `transicao_invalida`/conflito; 422 validação (inclui completude e FK inexistente).
- Testes de integração devem tolerar seeds pré-existentes (provisionamento semeia catálogos e `sla_policies`): nunca assertar contagens absolutas de catálogo.
- Datas sempre timezone-aware UTC no backend (`datetime.now(UTC)`).

## Mapa de arquivos novos/modificados

```
backend/src/sac/
  domain/
    tickets.py              # TicketStatus, VALID_TRANSITIONS, ensure_transition, TicketPriority,
                            # SlaPolicy, sla, TimelineEventType, entidades, missing_for_analysis
    errors.py               # +InvalidTransitionError
  application/
    ports_tickets.py        # TicketActor, TicketFilters, TicketListRow, TicketItemView, TicketDetail,
                            # protocolos de repositorio + UserDirectoryPort
    use_cases/
      tickets_shared.py     # get_ticket_or_404, ensure_can_edit/operate, add_transition_event, touch
      tickets_crud.py       # CreateTicket, UpdateTicket, Add/Update/RemoveTicketItem, AddComment
      tickets_workflow.py   # EnviarParaAnalise, Aprovar, Declinar, Cancelar, AguardarCliente, Retomar,
                            # Reabrir, RegistrarReverso, ExcluirReverso, ProdutoRecebido, Finalizar, SetWarranty
      tickets_queries.py    # ListTickets, GetTicketDetail, MarkTicketUnread
  infrastructure/
    models_tenant.py        # +TicketModel, TicketItemModel, TicketCommentModel, TicketTimelineEventModel,
                            # TicketReadModel, ReverseCodeModel, SlaPolicyModel, TICKET_NUMBER_SEQ
    repositories_tickets.py # SqlTicketRepository (+_flush_tickets por constraint), satelites, SqlUserDirectory,
                            # TicketRepos (bundle)
    tenant_seeds.py         # +seed de sla_policies
  interface/
    errors.py               # STATUS_BY_CODE += transicao_invalida: 409
    schemas.py              # +schemas de ticket
    deps.py                 # +get_ticket_repos
    routers/tickets.py      # todas as rotas /api/tickets
    app.py                  # include_router(tickets)
backend/migrations/tenant/versions/0003_tickets.py
backend/tests/unit/domain/test_tickets.py
backend/tests/unit/fakes_tickets.py
backend/tests/unit/application/test_tickets_crud.py, test_tickets_workflow.py,
  test_tickets_logistics.py, test_tickets_queries.py
backend/tests/integration/test_tickets_schema.py, test_repositories_tickets.py,
  test_tickets_api.py, test_tickets_workflow_api.py, test_tickets_flow.py
frontend/src/
  lib/tickets.ts            # tipos, client da API, labels, helpers de permissao/acao primaria
  lib/useDebounce.ts
  components/ui/textarea.tsx
  components/tickets/badges.tsx        # StatusBadge, PriorityBadge, SlaBadge
  components/tickets/StatusTrail.tsx   # trilha de status (identidade visual)
  pages/tickets/TicketsListPage.tsx
  pages/tickets/TicketDetailPage.tsx
  components/tickets/ActionPanel.tsx   # acao primaria contextual + menu + modais
  pages/tickets/TicketCreatePage.tsx
  components/layout/Sidebar.tsx        # +grupo Tickets
  main.tsx                             # +rotas /tickets
```

Convenção dos use cases: recebem `actor: TicketActor` (montado no router a partir do `TokenPayload`) e aplicam escopo de visão/dono internamente; o router aplica a permissão grossa via `require_permission`.

---

### Task 1: Domínio — estados, transições e InvalidTransitionError

**Files:**
- Create: `backend/src/sac/domain/tickets.py`
- Modify: `backend/src/sac/domain/errors.py`
- Modify: `backend/src/sac/interface/errors.py` (STATUS_BY_CODE)
- Test: `backend/tests/unit/domain/test_tickets.py`

**Interfaces:**
- Consumes: `DomainError` (domain/errors.py).
- Produces: `TicketStatus` (StrEnum, 9 valores), `CLOSED_STATUSES: frozenset[TicketStatus]`, `VALID_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]]`, `ensure_transition(current: TicketStatus, target: TicketStatus) -> None` (levanta `InvalidTransitionError`), `InvalidTransitionError` (code `transicao_invalida`, HTTP 409).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/domain/test_tickets.py`:

```python
import pytest

from sac.domain.errors import InvalidTransitionError
from sac.domain.tickets import (
    CLOSED_STATUSES,
    VALID_TRANSITIONS,
    TicketStatus,
    ensure_transition,
)


def test_fluxo_principal_e_valido() -> None:
    ensure_transition(TicketStatus.ABERTO, TicketStatus.AGUARDANDO_ANALISE)
    ensure_transition(TicketStatus.AGUARDANDO_ANALISE, TicketStatus.APROVADO)
    ensure_transition(TicketStatus.APROVADO, TicketStatus.AGUARDANDO_ENVIO_REVERSO)
    ensure_transition(TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.PRODUTO_RECEBIDO)
    ensure_transition(TicketStatus.PRODUTO_RECEBIDO, TicketStatus.FINALIZADO)


def test_declinio_aprovacao_direta_e_laterais() -> None:
    ensure_transition(TicketStatus.AGUARDANDO_ANALISE, TicketStatus.DECLINADO)
    ensure_transition(TicketStatus.APROVADO, TicketStatus.FINALIZADO)
    ensure_transition(TicketStatus.ABERTO, TicketStatus.AGUARDANDO_CLIENTE)
    ensure_transition(TicketStatus.AGUARDANDO_CLIENTE, TicketStatus.ABERTO)
    ensure_transition(TicketStatus.AGUARDANDO_CLIENTE, TicketStatus.AGUARDANDO_ANALISE)
    ensure_transition(TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.APROVADO)


def test_cancelado_a_partir_de_todo_nao_encerrado() -> None:
    for status in TicketStatus:
        if status in CLOSED_STATUSES:
            assert TicketStatus.CANCELADO not in VALID_TRANSITIONS[status]
        else:
            ensure_transition(status, TicketStatus.CANCELADO)


def test_reabertura_de_encerrados() -> None:
    for status in CLOSED_STATUSES:
        ensure_transition(status, TicketStatus.APROVADO)
        ensure_transition(status, TicketStatus.ABERTO)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TicketStatus.ABERTO, TicketStatus.APROVADO),
        (TicketStatus.ABERTO, TicketStatus.FINALIZADO),
        (TicketStatus.AGUARDANDO_ANALISE, TicketStatus.AGUARDANDO_ENVIO_REVERSO),
        (TicketStatus.APROVADO, TicketStatus.ABERTO),
        (TicketStatus.PRODUTO_RECEBIDO, TicketStatus.APROVADO),
        (TicketStatus.FINALIZADO, TicketStatus.FINALIZADO),
        (TicketStatus.FINALIZADO, TicketStatus.CANCELADO),
    ],
)
def test_transicoes_invalidas(current: TicketStatus, target: TicketStatus) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        ensure_transition(current, target)
    assert exc.value.code == "transicao_invalida"
    assert exc.value.details == {"de": current, "para": target}


def test_todo_status_tem_linha_na_tabela() -> None:
    assert set(VALID_TRANSITIONS.keys()) == set(TicketStatus)
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `backend/`): `uv run pytest tests/unit/domain/test_tickets.py -v`
Esperado: FAIL (ImportError: `sac.domain.tickets` não existe).

- [ ] **Step 3: Implementar**

Em `backend/src/sac/domain/errors.py`, ao final:

```python
class InvalidTransitionError(DomainError):
    code = "transicao_invalida"
```

Criar `backend/src/sac/domain/tickets.py`:

```python
from enum import StrEnum

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
    TicketStatus.PRODUTO_RECEBIDO: frozenset(
        {TicketStatus.FINALIZADO, TicketStatus.CANCELADO}
    ),
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
```

Em `backend/src/sac/interface/errors.py`, adicionar em `STATUS_BY_CODE`:

```python
    "transicao_invalida": 409,
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain/test_tickets.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações do backend (Global Constraints) e:

```bash
git add backend/src/sac/domain/tickets.py backend/src/sac/domain/errors.py backend/src/sac/interface/errors.py backend/tests/unit/domain/test_tickets.py
git commit -m "Adiciona maquina de estados do ticket no dominio"
```

---

### Task 2: Domínio — prioridade, SLA, completude e entidades

**Files:**
- Modify: `backend/src/sac/domain/tickets.py`
- Test: `backend/tests/unit/domain/test_tickets.py` (acrescentar)

**Interfaces:**
- Consumes: `ValidationError` não é usada aqui; apenas stdlib.
- Produces: `TicketPriority` (StrEnum: baixa/media/alta/urgente), `SlaPolicy(priority, hours, warn_hours=12)`, `DEFAULT_SLA_POLICIES: dict[TicketPriority, SlaPolicy]` (24/48/72/120), `SlaState` (StrEnum: no_prazo/vence_em_breve/atrasado/encerrado), `compute_due_at(opened_at: datetime, policy: SlaPolicy) -> datetime`, `sla_state(now: datetime, due_at: datetime, closed: bool, warn_hours: int = 12) -> SlaState`, `TimelineEventType` (StrEnum: criacao/transicao/prioridade_alterada/edicao/item_adicionado/item_alterado/item_removido/reverso_registrado/reverso_excluido/garantia_registrada), dataclasses `Ticket`, `TicketItem`, `TicketComment`, `TicketTimelineEvent`, `ReverseCode`, `missing_for_analysis(ticket: Ticket, items_count: int) -> list[str]`, `is_closed(ticket: Ticket) -> bool`.

- [ ] **Step 1: Acrescentar os testes que falham**

Em `backend/tests/unit/domain/test_tickets.py`, acrescentar:

```python
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    SlaPolicy,
    SlaState,
    Ticket,
    TicketPriority,
    compute_due_at,
    is_closed,
    missing_for_analysis,
    sla_state,
)


def _ticket(**overrides: object) -> Ticket:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "id": uuid4(),
        "number": 1,
        "brand_id": uuid4(),
        "status": TicketStatus.ABERTO,
        "priority": TicketPriority.MEDIA,
        "attendant_user_id": uuid4(),
        "opened_at": now,
        "due_at": now + timedelta(hours=72),
        "last_activity_at": now,
    }
    base.update(overrides)
    return Ticket(**base)  # type: ignore[arg-type]


def test_politicas_default_de_sla() -> None:
    assert DEFAULT_SLA_POLICIES[TicketPriority.URGENTE].hours == 24
    assert DEFAULT_SLA_POLICIES[TicketPriority.ALTA].hours == 48
    assert DEFAULT_SLA_POLICIES[TicketPriority.MEDIA].hours == 72
    assert DEFAULT_SLA_POLICIES[TicketPriority.BAIXA].hours == 120
    assert all(p.warn_hours == 12 for p in DEFAULT_SLA_POLICIES.values())


def test_compute_due_at() -> None:
    opened = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    policy = SlaPolicy(TicketPriority.URGENTE, hours=24)
    assert compute_due_at(opened, policy) == datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def test_sla_state_limites() -> None:
    due = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    assert sla_state(due - timedelta(hours=13), due, closed=False) is SlaState.NO_PRAZO
    assert sla_state(due - timedelta(hours=12), due, closed=False) is SlaState.VENCE_EM_BREVE
    assert sla_state(due - timedelta(minutes=1), due, closed=False) is SlaState.VENCE_EM_BREVE
    assert sla_state(due, due, closed=False) is SlaState.ATRASADO
    assert sla_state(due + timedelta(hours=1), due, closed=False) is SlaState.ATRASADO
    assert sla_state(due + timedelta(hours=1), due, closed=True) is SlaState.ENCERRADO


def test_missing_for_analysis() -> None:
    incompleto = _ticket()
    assert missing_for_analysis(incompleto, items_count=0) == ["cliente", "itens", "descricao"]
    completo = _ticket(customer_id=uuid4(), description="produto chegou quebrado")
    assert missing_for_analysis(completo, items_count=2) == []
    so_descricao_em_branco = _ticket(customer_id=uuid4(), description="   ")
    assert missing_for_analysis(so_descricao_em_branco, items_count=1) == ["descricao"]


def test_is_closed() -> None:
    assert not is_closed(_ticket())
    assert is_closed(_ticket(status=TicketStatus.CANCELADO))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/domain/test_tickets.py -v`
Esperado: FAIL (ImportError nos novos nomes).

- [ ] **Step 3: Implementar**

Acrescentar em `backend/src/sac/domain/tickets.py` (imports no topo: `from dataclasses import dataclass`, `from datetime import date, datetime, timedelta`, `from uuid import UUID`):

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain/test_tickets.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/domain/tickets.py backend/tests/unit/domain/test_tickets.py
git commit -m "Adiciona SLA, completude e entidades de ticket ao dominio"
```

---

### Task 3: Ports, fakes e use cases de criação/edição

**Files:**
- Create: `backend/src/sac/application/ports_tickets.py`
- Create: `backend/src/sac/application/use_cases/tickets_shared.py`
- Create: `backend/src/sac/application/use_cases/tickets_crud.py` (Create/Update nesta task)
- Create: `backend/tests/unit/fakes_tickets.py`
- Test: `backend/tests/unit/application/test_tickets_crud.py`

**Interfaces:**
- Consumes: entidades e funções de `sac.domain.tickets` (Tasks 1-2); `Customer`, `CustomerInput`, `CreateCustomerUseCase`, `UpdateCustomerUseCase` (`use_cases/customers.py`); `CustomerRepository` (`ports_cadastros.py`); `Role`, `Permission`, `has_permission`; `InMemoryCustomerRepository` (`tests/unit/fakes.py`).
- Produces (ports_tickets.py):
  - `TicketActor(user_id: UUID, role: Role)` (frozen dataclass)
  - `TicketFilters(status, brand_id, customer_id, customer, product_id, order_code, priority, overdue, attendant_user_id)` (frozen, todos opcionais, `overdue: bool = False`)
  - `TicketListRow(ticket: Ticket, customer_name: str | None, first_product_name: str | None, items_count: int, unread: bool, attendant_name: str | None = None)` (frozen)
  - `TicketItemView(item: TicketItem, product_name: str, defect_type_name: str)` (frozen)
  - `TicketDetail(ticket, sla: SlaState, customer: Customer | None, items: list[TicketItemView], comments: list[TicketComment], timeline: list[TicketTimelineEvent], reverses: list[ReverseCode], user_names: dict[UUID, str])` (frozen)
  - Protocolos: `TicketRepository` (`add(ticket) -> Ticket` devolve com `number` preenchido; `get(ticket_id) -> Ticket | None`; `update(ticket) -> None`; `list(filters, page, per_page, sort, order, unread_for: UUID) -> tuple[list[TicketListRow], int]`), `TicketItemRepository` (`list_by_ticket -> list[TicketItemView]`, `count`, `get`, `add`, `update`, `remove`), `TicketCommentRepository` (`list_by_ticket`, `get`, `add`), `TimelineRepository` (`list_by_ticket`, `add`), `ReverseCodeRepository` (`list_by_ticket`, `count`, `get`, `add`, `remove`), `TicketReadRepository` (`mark_read(ticket_id, user_id, at)`, `mark_unread(ticket_id, user_id)`, `last_read_at(ticket_id, user_id) -> datetime | None`), `SlaPolicyRepository` (`get(priority) -> SlaPolicy | None`), `UserDirectoryPort` (`names_by_ids(ids: set[UUID]) -> dict[UUID, str]`)
- Produces (tickets_shared.py): `EDITABLE_STATUSES = frozenset({ABERTO, AGUARDANDO_CLIENTE})`, `get_ticket_or_404(tickets, actor, ticket_id) -> Ticket` (aplica escopo de visão; atendente sem VER_TODOS só enxerga os seus — senão `NotFoundError`), `ensure_can_edit(actor, ticket)` (status editável + EDITAR_QUALQUER ou EDITAR_PROPRIO+dono), `ensure_can_operate(actor, ticket)` (OPERAR_LOGISTICA_TODOS ou _PROPRIOS+dono), `touch(ticket, now)`, `transition_event(ticket, old_status, title, actor, event_type=TimelineEventType.TRANSICAO) -> TicketTimelineEvent`.
- Produces (tickets_crud.py): `TicketItemInput(product_id, defect_type_id, quantity=1)`, `CreateTicketInput(brand_id, priority, customer: CustomerInput | None = None, customer_id: UUID | None = None, attendant_user_id: UUID | None = None, supervisor_user_id=None, purchase_channel_id=None, order_code=None, purchase_date=None, delivery_date=None, description=None, items: tuple[TicketItemInput, ...] = ())`, `CreateTicketUseCase(tickets, items, customers, sla_policies, timeline, reads).execute(actor, data) -> Ticket`, `UpdateTicketInput(brand_id, priority, customer_id=None, supervisor_user_id=None, purchase_channel_id=None, order_code=None, purchase_date=None, delivery_date=None, description=None)`, `UpdateTicketUseCase(tickets, customers, sla_policies, timeline).execute(actor, ticket_id, data) -> Ticket`.
- Produces (fakes_tickets.py): `InMemoryTicketRepository` (numera 1,2,3... em `add`), `InMemoryTicketItemRepository`, `InMemoryTicketCommentRepository`, `InMemoryTimelineRepository` (expõe `events: list[TicketTimelineEvent]`), `InMemoryReverseCodeRepository`, `InMemoryTicketReadRepository` (dict `reads: (ticket_id, user_id) -> datetime`), `InMemorySlaPolicyRepository` (usa `DEFAULT_SLA_POLICIES`, aceita overrides), `InMemoryUserDirectory` (dict `UUID -> str`).

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/unit/application/test_tickets_crud.py`:

```python
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
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
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
            CreateTicketInput(
                brand_id=uuid4(), priority=TicketPriority.MEDIA, customer_id=uuid4()
            ),
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


async def test_atendente_nao_cria_para_outro_admin_sim() -> None:
    use_case, _, _, _, _, _ = make_create_use_case()
    outro = uuid4()
    de_atendente = await use_case.execute(
        ATENDENTE,
        CreateTicketInput(
            brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=outro
        ),
    )
    assert de_atendente.attendant_user_id == ATENDENTE.user_id
    de_admin = await use_case.execute(
        ADMIN,
        CreateTicketInput(
            brand_id=uuid4(), priority=TicketPriority.MEDIA, attendant_user_id=outro
        ),
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
```

Observação: os testes async seguem o padrão dos testes de application existentes (o projeto já roda `pytest` com modo async automático via anyio/asyncio configurado; conferir `backend/pyproject.toml` e replicar o marcador usado em `test_customers_use_cases.py` se houver).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_tickets_crud.py -v`
Esperado: FAIL (imports inexistentes).

- [ ] **Step 3: Implementar ports_tickets.py**

`backend/src/sac/application/ports_tickets.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sac.domain.cadastros import Customer
from sac.domain.permissions import Role
from sac.domain.tickets import (
    ReverseCode,
    SlaPolicy,
    SlaState,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
)


@dataclass(frozen=True)
class TicketActor:
    user_id: UUID
    role: Role


@dataclass(frozen=True)
class TicketFilters:
    status: TicketStatus | None = None
    brand_id: UUID | None = None
    customer_id: UUID | None = None
    customer: str | None = None
    product_id: UUID | None = None
    order_code: str | None = None
    priority: TicketPriority | None = None
    overdue: bool = False
    attendant_user_id: UUID | None = None


@dataclass(frozen=True)
class TicketListRow:
    ticket: Ticket
    customer_name: str | None
    first_product_name: str | None
    items_count: int
    unread: bool
    attendant_name: str | None = None


@dataclass(frozen=True)
class TicketItemView:
    item: TicketItem
    product_name: str
    defect_type_name: str


@dataclass(frozen=True)
class TicketDetail:
    ticket: Ticket
    sla: SlaState
    customer: Customer | None
    items: list[TicketItemView]
    comments: list[TicketComment]
    timeline: list[TicketTimelineEvent]
    reverses: list[ReverseCode]
    user_names: dict[UUID, str]


class TicketRepository(Protocol):
    async def add(self, ticket: Ticket) -> Ticket: ...
    async def get(self, ticket_id: UUID) -> Ticket | None: ...
    async def update(self, ticket: Ticket) -> None: ...
    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]: ...


class TicketItemRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]: ...
    async def count(self, ticket_id: UUID) -> int: ...
    async def get(self, item_id: UUID) -> TicketItem | None: ...
    async def add(self, item: TicketItem) -> None: ...
    async def update(self, item: TicketItem) -> None: ...
    async def remove(self, item_id: UUID) -> None: ...


class TicketCommentRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]: ...
    async def get(self, comment_id: UUID) -> TicketComment | None: ...
    async def add(self, comment: TicketComment) -> None: ...


class TimelineRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]: ...
    async def add(self, event: TicketTimelineEvent) -> None: ...


class ReverseCodeRepository(Protocol):
    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]: ...
    async def count(self, ticket_id: UUID) -> int: ...
    async def get(self, reverse_id: UUID) -> ReverseCode | None: ...
    async def add(self, reverse: ReverseCode) -> None: ...
    async def remove(self, reverse_id: UUID) -> None: ...


class TicketReadRepository(Protocol):
    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None: ...
    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None: ...
    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None: ...


class SlaPolicyRepository(Protocol):
    async def get(self, priority: TicketPriority) -> SlaPolicy | None: ...


class UserDirectoryPort(Protocol):
    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]: ...
```

- [ ] **Step 4: Implementar tickets_shared.py**

`backend/src/sac/application/use_cases/tickets_shared.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4

from sac.application.ports_tickets import TicketActor, TicketRepository
from sac.domain.errors import ConflictError, NotFoundError, PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import (
    Ticket,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
)

EDITABLE_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.ABERTO, TicketStatus.AGUARDANDO_CLIENTE}
)


async def get_ticket_or_404(
    tickets: TicketRepository, actor: TicketActor, ticket_id: UUID
) -> Ticket:
    ticket = await tickets.get(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise NotFoundError("ticket nao encontrado")
    if has_permission(actor.role, Permission.VER_TODOS_TICKETS):
        return ticket
    if (
        has_permission(actor.role, Permission.VER_PROPRIOS_TICKETS)
        and ticket.attendant_user_id == actor.user_id
    ):
        return ticket
    raise NotFoundError("ticket nao encontrado")


def ensure_can_edit(actor: TicketActor, ticket: Ticket) -> None:
    if ticket.status not in EDITABLE_STATUSES:
        raise ConflictError(
            "ticket nao pode ser editado neste estado", details={"status": ticket.status}
        )
    if has_permission(actor.role, Permission.EDITAR_QUALQUER_TICKET):
        return
    if (
        has_permission(actor.role, Permission.EDITAR_PROPRIO_TICKET)
        and ticket.attendant_user_id == actor.user_id
    ):
        return
    raise PermissionDeniedError("sem permissao para editar este ticket")


def ensure_can_operate(actor: TicketActor, ticket: Ticket) -> None:
    if has_permission(actor.role, Permission.OPERAR_LOGISTICA_TODOS):
        return
    if (
        has_permission(actor.role, Permission.OPERAR_LOGISTICA_PROPRIOS)
        and ticket.attendant_user_id == actor.user_id
    ):
        return
    raise PermissionDeniedError("sem permissao para operar este ticket")


def touch(ticket: Ticket, now: datetime) -> None:
    ticket.last_activity_at = now


def transition_event(
    ticket: Ticket,
    old_status: TicketStatus,
    title: str,
    actor: TicketActor,
    event_type: TimelineEventType = TimelineEventType.TRANSICAO,
) -> TicketTimelineEvent:
    return TicketTimelineEvent(
        id=uuid4(),
        ticket_id=ticket.id,
        type=event_type,
        title=title,
        old_value=str(old_status),
        new_value=str(ticket.status),
        author_user_id=actor.user_id,
    )
```

- [ ] **Step 5: Implementar tickets_crud.py (Create/Update)**

`backend/src/sac/application/use_cases/tickets_crud.py`:

```python
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CustomerRepository
from sac.application.ports_tickets import (
    SlaPolicyRepository,
    TicketActor,
    TicketItemRepository,
    TicketReadRepository,
    TicketRepository,
    TimelineRepository,
)
from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    UpdateCustomerUseCase,
)
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    get_ticket_or_404,
    touch,
)
from sac.domain.documents import validate_document
from sac.domain.errors import ValidationError
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    SlaPolicy,
    Ticket,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
    compute_due_at,
)


@dataclass(frozen=True)
class TicketItemInput:
    product_id: UUID
    defect_type_id: UUID
    quantity: int = 1


@dataclass(frozen=True)
class CreateTicketInput:
    brand_id: UUID
    priority: TicketPriority
    customer: CustomerInput | None = None
    customer_id: UUID | None = None
    attendant_user_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = None
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None
    items: tuple[TicketItemInput, ...] = ()


@dataclass(frozen=True)
class UpdateTicketInput:
    brand_id: UUID
    priority: TicketPriority
    customer_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = None
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None


def _validate_quantity(quantity: int) -> None:
    if quantity < 1:
        raise ValidationError("quantidade minima e 1", details={"field": "quantity"})


async def _resolve_customer_id(
    customers: CustomerRepository,
    inline: CustomerInput | None,
    customer_id: UUID | None,
) -> UUID | None:
    if inline is not None and customer_id is not None:
        raise ValidationError("informe cliente inline ou customer_id, nao ambos")
    if inline is not None:
        document = validate_document(inline.document)
        existing = await customers.get_by_document(document)
        if existing is not None:
            updated = await UpdateCustomerUseCase(customers).execute(existing.id, inline)
            return updated.id
        created = await CreateCustomerUseCase(customers).execute(inline)
        return created.id
    if customer_id is not None:
        if await customers.get(customer_id) is None:
            raise ValidationError("cliente nao encontrado", details={"field": "customer_id"})
        return customer_id
    return None


async def _resolve_sla(policies: SlaPolicyRepository, priority: TicketPriority) -> SlaPolicy:
    return await policies.get(priority) or DEFAULT_SLA_POLICIES[priority]


class CreateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
        reads: TicketReadRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline
        self._reads = reads

    async def execute(self, actor: TicketActor, data: CreateTicketInput) -> Ticket:
        for item in data.items:
            _validate_quantity(item.quantity)
        customer_id = await _resolve_customer_id(self._customers, data.customer, data.customer_id)
        attendant = actor.user_id
        if data.attendant_user_id is not None and has_permission(
            actor.role, Permission.VER_TODOS_TICKETS
        ):
            attendant = data.attendant_user_id
        now = datetime.now(UTC)
        policy = await _resolve_sla(self._sla, data.priority)
        ticket = Ticket(
            id=uuid4(),
            number=0,
            brand_id=data.brand_id,
            status=TicketStatus.ABERTO,
            priority=data.priority,
            attendant_user_id=attendant,
            opened_at=now,
            due_at=compute_due_at(now, policy),
            last_activity_at=now,
            customer_id=customer_id,
            supervisor_user_id=data.supervisor_user_id,
            purchase_channel_id=data.purchase_channel_id,
            order_code=data.order_code,
            purchase_date=data.purchase_date,
            delivery_date=data.delivery_date,
            description=data.description,
        )
        ticket = await self._tickets.add(ticket)
        for item in data.items:
            await self._items.add(
                TicketItem(
                    id=uuid4(),
                    ticket_id=ticket.id,
                    product_id=item.product_id,
                    defect_type_id=item.defect_type_id,
                    quantity=item.quantity,
                )
            )
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.CRIACAO,
                title="Ticket criado",
                new_value=str(ticket.number),
                author_user_id=actor.user_id,
            )
        )
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return ticket


class UpdateTicketUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        customers: CustomerRepository,
        sla_policies: SlaPolicyRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._customers = customers
        self._sla = sla_policies
        self._timeline = timeline

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, data: UpdateTicketInput
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        if data.customer_id is not None and await self._customers.get(data.customer_id) is None:
            raise ValidationError("cliente nao encontrado", details={"field": "customer_id"})
        old_priority = ticket.priority
        ticket.brand_id = data.brand_id
        ticket.priority = data.priority
        ticket.customer_id = data.customer_id
        ticket.supervisor_user_id = data.supervisor_user_id
        ticket.purchase_channel_id = data.purchase_channel_id
        ticket.order_code = data.order_code
        ticket.purchase_date = data.purchase_date
        ticket.delivery_date = data.delivery_date
        ticket.description = data.description
        now = datetime.now(UTC)
        if data.priority != old_priority:
            policy = await _resolve_sla(self._sla, data.priority)
            ticket.due_at = compute_due_at(ticket.opened_at, policy)
            event = TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.PRIORIDADE_ALTERADA,
                title="Prioridade alterada",
                old_value=str(old_priority),
                new_value=str(data.priority),
                author_user_id=actor.user_id,
            )
        else:
            event = TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.EDICAO,
                title="Dados do ticket editados",
                author_user_id=actor.user_id,
            )
        await self._timeline.add(event)
        touch(ticket, now)
        await self._tickets.update(ticket)
        return ticket
```

- [ ] **Step 6: Implementar fakes_tickets.py**

`backend/tests/unit/fakes_tickets.py`:

```python
from datetime import datetime
from uuid import UUID

from sac.application.ports_tickets import TicketFilters, TicketItemView, TicketListRow
from sac.domain.tickets import (
    DEFAULT_SLA_POLICIES,
    ReverseCode,
    SlaPolicy,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketTimelineEvent,
)


class InMemoryTicketRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Ticket] = {}
        self._seq = 0

    async def add(self, ticket: Ticket) -> Ticket:
        self._seq += 1
        ticket.number = self._seq
        self.items[ticket.id] = ticket
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        return self.items.get(ticket_id)

    async def update(self, ticket: Ticket) -> None:
        self.items[ticket.id] = ticket

    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]:
        rows = [
            TicketListRow(
                ticket=t,
                customer_name=None,
                first_product_name=None,
                items_count=0,
                unread=False,
            )
            for t in self.items.values()
            if filters.attendant_user_id is None
            or t.attendant_user_id == filters.attendant_user_id
        ]
        return rows, len(rows)


class InMemoryTicketItemRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, TicketItem] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]:
        return [
            TicketItemView(item=i, product_name="Produto", defect_type_name="Defeito")
            for i in self.items.values()
            if i.ticket_id == ticket_id
        ]

    async def count(self, ticket_id: UUID) -> int:
        return sum(1 for i in self.items.values() if i.ticket_id == ticket_id)

    async def get(self, item_id: UUID) -> TicketItem | None:
        return self.items.get(item_id)

    async def add(self, item: TicketItem) -> None:
        self.items[item.id] = item

    async def update(self, item: TicketItem) -> None:
        self.items[item.id] = item

    async def remove(self, item_id: UUID) -> None:
        self.items.pop(item_id, None)


class InMemoryTicketCommentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, TicketComment] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]:
        return [c for c in self.items.values() if c.ticket_id == ticket_id]

    async def get(self, comment_id: UUID) -> TicketComment | None:
        return self.items.get(comment_id)

    async def add(self, comment: TicketComment) -> None:
        self.items[comment.id] = comment


class InMemoryTimelineRepository:
    def __init__(self) -> None:
        self.events: list[TicketTimelineEvent] = []

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]:
        return [e for e in self.events if e.ticket_id == ticket_id]

    async def add(self, event: TicketTimelineEvent) -> None:
        self.events.append(event)


class InMemoryReverseCodeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ReverseCode] = {}

    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]:
        return [r for r in self.items.values() if r.ticket_id == ticket_id]

    async def count(self, ticket_id: UUID) -> int:
        return sum(1 for r in self.items.values() if r.ticket_id == ticket_id)

    async def get(self, reverse_id: UUID) -> ReverseCode | None:
        return self.items.get(reverse_id)

    async def add(self, reverse: ReverseCode) -> None:
        self.items[reverse.id] = reverse

    async def remove(self, reverse_id: UUID) -> None:
        self.items.pop(reverse_id, None)


class InMemoryTicketReadRepository:
    def __init__(self) -> None:
        self.reads: dict[tuple[UUID, UUID], datetime] = {}

    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None:
        self.reads[(ticket_id, user_id)] = at

    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None:
        self.reads.pop((ticket_id, user_id), None)

    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None:
        return self.reads.get((ticket_id, user_id))


class InMemorySlaPolicyRepository:
    def __init__(self, overrides: dict[TicketPriority, SlaPolicy] | None = None) -> None:
        self.policies = dict(DEFAULT_SLA_POLICIES)
        if overrides:
            self.policies.update(overrides)

    async def get(self, priority: TicketPriority) -> SlaPolicy | None:
        return self.policies.get(priority)


class InMemoryUserDirectory:
    def __init__(self, names: dict[UUID, str] | None = None) -> None:
        self.names = names or {}

    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]:
        return {i: n for i, n in self.names.items() if i in ids}
```

- [ ] **Step 7: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_tickets_crud.py tests/unit/domain/test_tickets.py -v`
Esperado: PASS.

- [ ] **Step 8: Verificações completas e commit**

```bash
git add backend/src/sac/application/ports_tickets.py backend/src/sac/application/use_cases/tickets_shared.py backend/src/sac/application/use_cases/tickets_crud.py backend/tests/unit/fakes_tickets.py backend/tests/unit/application/test_tickets_crud.py
git commit -m "Adiciona ports e use cases de criacao e edicao de ticket"
```

---

### Task 4: Use cases de itens e comentário

**Files:**
- Modify: `backend/src/sac/application/use_cases/tickets_crud.py`
- Test: `backend/tests/unit/application/test_tickets_crud.py` (acrescentar)

**Interfaces:**
- Consumes: Task 3 (shared, ports, fakes).
- Produces: `AddTicketItemUseCase(tickets, items, timeline).execute(actor, ticket_id, data: TicketItemInput) -> TicketItem`; `UpdateTicketItemUseCase(tickets, items, timeline).execute(actor, ticket_id, item_id, data: TicketItemInput) -> TicketItem`; `RemoveTicketItemUseCase(tickets, items, timeline).execute(actor, ticket_id, item_id) -> None`; `AddCommentUseCase(tickets, comments, reads).execute(actor, ticket_id, body: str, reply_to_id: UUID | None = None) -> TicketComment`.

- [ ] **Step 1: Acrescentar os testes que falham**

Acrescentar em `backend/tests/unit/application/test_tickets_crud.py`:

```python
from sac.application.use_cases.tickets_crud import (
    AddCommentUseCase,
    AddTicketItemUseCase,
    RemoveTicketItemUseCase,
    UpdateTicketItemUseCase,
)
from tests.unit.fakes_tickets import InMemoryTicketCommentRepository


async def _ticket_aberto(tickets: InMemoryTicketRepository) -> Ticket:
    use_case = CreateTicketUseCase(
        tickets,
        InMemoryTicketItemRepository(),
        InMemoryCustomerRepository(),
        InMemorySlaPolicyRepository(),
        InMemoryTimelineRepository(),
        InMemoryTicketReadRepository(),
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
        TicketItemInput(
            product_id=item.product_id, defect_type_id=item.defect_type_id, quantity=5
        ),
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
    use_case = AddCommentUseCase(tickets, comments, reads)
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_tickets_crud.py -v`
Esperado: FAIL (imports).

- [ ] **Step 3: Implementar**

Acrescentar em `backend/src/sac/application/use_cases/tickets_crud.py` (imports adicionais: `TicketCommentRepository` de ports_tickets; `ConflictError`, `NotFoundError` de errors; `TicketComment`, `is_closed` de tickets):

```python
async def _record_item_event(
    tickets: TicketRepository,
    timeline: TimelineRepository,
    ticket: Ticket,
    actor: TicketActor,
    type_: TimelineEventType,
    title: str,
) -> None:
    await timeline.add(
        TicketTimelineEvent(
            id=uuid4(),
            ticket_id=ticket.id,
            type=type_,
            title=title,
            author_user_id=actor.user_id,
        )
    )
    touch(ticket, datetime.now(UTC))
    await tickets.update(ticket)


class AddTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, data: TicketItemInput
    ) -> TicketItem:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        _validate_quantity(data.quantity)
        item = TicketItem(
            id=uuid4(),
            ticket_id=ticket.id,
            product_id=data.product_id,
            defect_type_id=data.defect_type_id,
            quantity=data.quantity,
        )
        await self._items.add(item)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_ADICIONADO,
            "Item adicionado",
        )
        return item


class UpdateTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, item_id: UUID, data: TicketItemInput
    ) -> TicketItem:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        _validate_quantity(data.quantity)
        item = await self._items.get(item_id)
        if item is None or item.ticket_id != ticket.id:
            raise NotFoundError("item nao encontrado")
        item.product_id = data.product_id
        item.defect_type_id = data.defect_type_id
        item.quantity = data.quantity
        await self._items.update(item)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_ALTERADO,
            "Item alterado",
        )
        return item


class RemoveTicketItemUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._timeline = timeline

    async def execute(self, actor: TicketActor, ticket_id: UUID, item_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        item = await self._items.get(item_id)
        if item is None or item.ticket_id != ticket.id:
            raise NotFoundError("item nao encontrado")
        await self._items.remove(item.id)
        await _record_item_event(
            self._tickets,
            self._timeline,
            ticket,
            actor,
            TimelineEventType.ITEM_REMOVIDO,
            "Item removido",
        )


class AddCommentUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        comments: TicketCommentRepository,
        reads: TicketReadRepository,
    ) -> None:
        self._tickets = tickets
        self._comments = comments
        self._reads = reads

    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        body: str,
        reply_to_id: UUID | None = None,
    ) -> TicketComment:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita comentarios")
        text = body.strip()
        if not text:
            raise ValidationError("comentario vazio")
        if reply_to_id is not None:
            parent = await self._comments.get(reply_to_id)
            if parent is None or parent.ticket_id != ticket.id:
                raise ValidationError("comentario respondido nao pertence a este ticket")
        comment = TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=actor.user_id,
            body=text,
            reply_to_id=reply_to_id,
        )
        await self._comments.add(comment)
        now = datetime.now(UTC)
        touch(ticket, now)
        await self._tickets.update(ticket)
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return comment
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_tickets_crud.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/tickets_crud.py backend/tests/unit/application/test_tickets_crud.py
git commit -m "Adiciona use cases de itens e comentarios do ticket"
```

---

### Task 5: Use cases de transição — decisão e laterais

**Files:**
- Create: `backend/src/sac/application/use_cases/tickets_workflow.py`
- Test: `backend/tests/unit/application/test_tickets_workflow.py`

**Interfaces:**
- Consumes: Tasks 1-4 (`ensure_transition`, `missing_for_analysis`, shared helpers, fakes).
- Produces (todas com construtor `(tickets: TicketRepository, timeline: TimelineRepository)` salvo indicação):
  - `SubmitTicketUseCase(tickets, items, timeline).execute(actor, ticket_id) -> Ticket` — aberto/aguardando_cliente -> aguardando_analise; exige completude (`ValidationError` com `details={"faltando": [...]}`); seta `submitted_at`.
  - `ApproveTicketUseCase.execute(actor, ticket_id, notes: str | None = None) -> Ticket` — seta `approved_at`, `decision_notes` se `notes`.
  - `DeclineTicketUseCase.execute(actor, ticket_id, reason: str) -> Ticket` — motivo obrigatório (`ValidationError` se vazio); seta `declined_at`, `closed_at`, `decision_notes`.
  - `CancelTicketUseCase.execute(actor, ticket_id, reason: str | None = None) -> Ticket` — de qualquer não encerrado; seta `closed_at`; `decision_notes` recebe o motivo se enviado.
  - `HoldForCustomerUseCase.execute(actor, ticket_id) -> Ticket` — aberto -> aguardando_cliente; usa `ensure_can_edit`.
  - `ResumeTicketUseCase.execute(actor, ticket_id) -> Ticket` — aguardando_cliente -> aberto; usa `ensure_can_edit`.
  - `ReopenTicketUseCase.execute(actor, ticket_id) -> Ticket` — encerrado -> aprovado se `approved_at` senão aberto; limpa `closed_at`.
- Todas: `get_ticket_or_404` primeiro; `ensure_transition(status_antigo, alvo)`; `touch`; evento `transition_event` com título próprio; `tickets.update`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/unit/application/test_tickets_workflow.py`:

```python
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
        data = CreateTicketInput(
            brand_id=uuid4(),
            priority=TicketPriority.MEDIA,
            customer_id=None,
            description="descricao do problema",
            **kwargs,  # type: ignore[arg-type]
        )
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_tickets_workflow.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar**

`backend/src/sac/application/use_cases/tickets_workflow.py`:

```python
from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_tickets import (
    TicketActor,
    TicketItemRepository,
    TicketRepository,
    TimelineRepository,
)
from sac.application.use_cases.tickets_shared import (
    ensure_can_edit,
    get_ticket_or_404,
    touch,
    transition_event,
)
from sac.domain.errors import ValidationError
from sac.domain.tickets import (
    Ticket,
    TicketStatus,
    ensure_transition,
    missing_for_analysis,
)


class _TransitionUseCase:
    def __init__(self, tickets: TicketRepository, timeline: TimelineRepository) -> None:
        self._tickets = tickets
        self._timeline = timeline

    async def _apply(
        self,
        actor: TicketActor,
        ticket: Ticket,
        target: TicketStatus,
        title: str,
        now: datetime,
    ) -> None:
        old = ticket.status
        ensure_transition(old, target)
        ticket.status = target
        await self._timeline.add(transition_event(ticket, old, title, actor))
        touch(ticket, now)
        await self._tickets.update(ticket)


class SubmitTicketUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        timeline: TimelineRepository,
    ) -> None:
        super().__init__(tickets, timeline)
        self._items = items

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_transition(ticket.status, TicketStatus.AGUARDANDO_ANALISE)
        missing = missing_for_analysis(ticket, await self._items.count(ticket.id))
        if missing:
            raise ValidationError(
                "ticket incompleto para analise", details={"faltando": missing}
            )
        now = datetime.now(UTC)
        ticket.submitted_at = now
        await self._apply(
            actor, ticket, TicketStatus.AGUARDANDO_ANALISE, "Ticket enviado para analise", now
        )
        return ticket


class ApproveTicketUseCase(_TransitionUseCase):
    async def execute(
        self, actor: TicketActor, ticket_id: UUID, notes: str | None = None
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.approved_at = now
        if notes and notes.strip():
            ticket.decision_notes = notes.strip()
        await self._apply(actor, ticket, TicketStatus.APROVADO, "Ticket aprovado", now)
        return ticket


class DeclineTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID, reason: str) -> Ticket:
        if not reason.strip():
            raise ValidationError("motivo do declinio e obrigatorio")
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.declined_at = now
        ticket.closed_at = now
        ticket.decision_notes = reason.strip()
        await self._apply(actor, ticket, TicketStatus.DECLINADO, "Ticket declinado", now)
        return ticket


class CancelTicketUseCase(_TransitionUseCase):
    async def execute(
        self, actor: TicketActor, ticket_id: UUID, reason: str | None = None
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        ticket.closed_at = now
        if reason and reason.strip():
            ticket.decision_notes = reason.strip()
        await self._apply(actor, ticket, TicketStatus.CANCELADO, "Ticket cancelado", now)
        return ticket


class HoldForCustomerUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(
            actor, ticket, TicketStatus.AGUARDANDO_CLIENTE, "Aguardando retorno do cliente", now
        )
        return ticket


class ResumeTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_edit(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(actor, ticket, TicketStatus.ABERTO, "Atendimento retomado", now)
        return ticket


class ReopenTicketUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        target = TicketStatus.APROVADO if ticket.approved_at else TicketStatus.ABERTO
        now = datetime.now(UTC)
        ticket.closed_at = None
        await self._apply(actor, ticket, target, "Ticket reaberto", now)
        return ticket
```

Nota: `HoldForCustomerUseCase`/`ResumeTicketUseCase` chamam `ensure_can_edit` ANTES de `_apply` porque a matriz dá essas laterais a quem pode editar (atendente dono incluído); `ensure_can_edit` também garante estado editável, o que aqui coincide com as transições válidas.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_tickets_workflow.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/tickets_workflow.py backend/tests/unit/application/test_tickets_workflow.py
git commit -m "Adiciona use cases de decisao e transicoes laterais do ticket"
```

---

### Task 6: Use cases de logística — reverso, recebimento, finalização e garantia

**Files:**
- Modify: `backend/src/sac/application/use_cases/tickets_workflow.py`
- Test: `backend/tests/unit/application/test_tickets_logistics.py`

**Interfaces:**
- Consumes: Task 5 (`_TransitionUseCase`, helpers), `ReverseCodeRepository` (Task 3), `ensure_can_operate`.
- Produces:
  - `RegisterReverseUseCase(tickets, reverses, timeline).execute(actor, ticket_id, code: str) -> ReverseCode` — permitido em aprovado/aguardando_envio_reverso; de aprovado transiciona para aguardando_envio_reverso; código obrigatório.
  - `DeleteReverseUseCase(tickets, reverses, timeline).execute(actor, ticket_id, reverse_id) -> None` — permitido em aguardando_envio_reverso/produto_recebido; remover o último em aguardando_envio_reverso volta o status para aprovado.
  - `ReceiveProductUseCase(tickets, timeline).execute(actor, ticket_id) -> Ticket`.
  - `FinalizeTicketUseCase(tickets, timeline).execute(actor, ticket_id, solution_type_id: UUID, notes: str | None = None) -> Ticket` — seta `solution_type_id`, `final_notes`, `closed_at`.
  - `SetWarrantyUseCase(tickets, timeline).execute(actor, ticket_id, order_code: str, tracking_code: str | None = None) -> Ticket` — bloqueado em encerrado (`ConflictError`); não muda status; evento `garantia_registrada`.
- Todas aplicam `ensure_can_operate` após `get_ticket_or_404`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/unit/application/test_tickets_logistics.py`:

```python
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
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
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketItem, TicketPriority, TicketStatus
from tests.unit.fakes import InMemoryCustomerRepository
from tests.unit.fakes_tickets import (
    InMemoryReverseCodeRepository,
    InMemorySlaPolicyRepository,
    InMemoryTicketItemRepository,
    InMemoryTicketReadRepository,
    InMemoryTicketRepository,
    InMemoryTimelineRepository,
)

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)


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
        await SubmitTicketUseCase(self.tickets, self.items, self.timeline).execute(
            actor, ticket.id
        )
        return await ApproveTicketUseCase(self.tickets, self.timeline).execute(ADMIN, ticket.id)


async def test_reverso_move_e_excluir_ultimo_volta() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline)
    with pytest.raises(ValidationError):
        await register.execute(ADMIN, ticket.id, code="   ")
    reverse = await register.execute(ADMIN, ticket.id, code="BR123")
    assert ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
    second = await register.execute(ADMIN, ticket.id, code="BR456")
    assert ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
    delete = DeleteReverseUseCase(env.tickets, env.reverses, env.timeline)
    await delete.execute(ADMIN, ticket.id, second.id)
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.AGUARDANDO_ENVIO_REVERSO  # type: ignore[union-attr]
    await delete.execute(ADMIN, ticket.id, reverse.id)
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.APROVADO  # type: ignore[union-attr]


async def test_reverso_em_estado_errado_e_invalido() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    ticket.status = TicketStatus.ABERTO
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline)
    with pytest.raises(InvalidTransitionError):
        await register.execute(ADMIN, ticket.id, code="BR123")


async def test_recebimento_e_finalizacao_com_solucao() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    await RegisterReverseUseCase(env.tickets, env.reverses, env.timeline).execute(
        ADMIN, ticket.id, code="BR123"
    )
    ticket = await ReceiveProductUseCase(env.tickets, env.timeline).execute(ADMIN, ticket.id)
    assert ticket.status is TicketStatus.PRODUTO_RECEBIDO
    solution = uuid4()
    ticket = await FinalizeTicketUseCase(env.tickets, env.timeline).execute(
        ADMIN, ticket.id, solution_type_id=solution, notes="troca feita"
    )
    assert ticket.status is TicketStatus.FINALIZADO
    assert ticket.solution_type_id == solution
    assert ticket.final_notes == "troca feita"
    assert ticket.closed_at is not None


async def test_finalizacao_direta_de_aprovado() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    ticket = await FinalizeTicketUseCase(env.tickets, env.timeline).execute(
        ADMIN, ticket.id, solution_type_id=uuid4()
    )
    assert ticket.status is TicketStatus.FINALIZADO


async def test_garantia_nao_muda_status_e_bloqueia_encerrado() -> None:
    env = Env()
    ticket = await env.ticket_aprovado()
    warranty = SetWarrantyUseCase(env.tickets, env.timeline)
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
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline)
    # atendente nem enxerga ticket de outro atendente: 404
    from sac.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await register.execute(ATENDENTE, ticket.id, code="BR999")


async def test_atendente_opera_o_proprio() -> None:
    env = Env()
    ticket = await env.ticket_aprovado(actor=ATENDENTE)
    register = RegisterReverseUseCase(env.tickets, env.reverses, env.timeline)
    await register.execute(ATENDENTE, ticket.id, code="BR777")
    assert (await env.tickets.get(ticket.id)).status is TicketStatus.AGUARDANDO_ENVIO_REVERSO  # type: ignore[union-attr]
```

Nota: `PermissionDeniedError` importado fica sem uso se nenhum caso 403 puro existir aqui — remover o import se o ruff acusar (o caso 403 de logística com papel visualizador é coberto na integração).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_tickets_logistics.py -v`
Esperado: FAIL (imports).

- [ ] **Step 3: Implementar**

Acrescentar em `backend/src/sac/application/use_cases/tickets_workflow.py` (imports adicionais: `ReverseCodeRepository` de ports_tickets; `uuid4` de uuid; `ConflictError` de errors; `ReverseCode`, `TicketTimelineEvent`, `TimelineEventType`, `is_closed` de tickets; `ensure_can_operate` de tickets_shared):

```python
REVERSE_ALLOWED_STATUSES = frozenset(
    {TicketStatus.APROVADO, TicketStatus.AGUARDANDO_ENVIO_REVERSO}
)
REVERSE_DELETE_ALLOWED_STATUSES = frozenset(
    {TicketStatus.AGUARDANDO_ENVIO_REVERSO, TicketStatus.PRODUTO_RECEBIDO}
)


class RegisterReverseUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        reverses: ReverseCodeRepository,
        timeline: TimelineRepository,
    ) -> None:
        super().__init__(tickets, timeline)
        self._reverses = reverses

    async def execute(self, actor: TicketActor, ticket_id: UUID, code: str) -> ReverseCode:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        cleaned = code.strip()
        if not cleaned:
            raise ValidationError("codigo reverso e obrigatorio")
        if ticket.status not in REVERSE_ALLOWED_STATUSES:
            raise InvalidTransitionError(
                "codigo reverso nao permitido neste estado",
                details={"status": ticket.status},
            )
        now = datetime.now(UTC)
        if ticket.status is TicketStatus.APROVADO:
            await self._apply(
                actor,
                ticket,
                TicketStatus.AGUARDANDO_ENVIO_REVERSO,
                "Aguardando envio reverso",
                now,
            )
        reverse = ReverseCode(
            id=uuid4(), ticket_id=ticket.id, code=cleaned, author_user_id=actor.user_id
        )
        await self._reverses.add(reverse)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.REVERSO_REGISTRADO,
                title="Codigo reverso registrado",
                new_value=cleaned,
                author_user_id=actor.user_id,
            )
        )
        touch(ticket, now)
        await self._tickets.update(ticket)
        return reverse


class DeleteReverseUseCase(_TransitionUseCase):
    def __init__(
        self,
        tickets: TicketRepository,
        reverses: ReverseCodeRepository,
        timeline: TimelineRepository,
    ) -> None:
        super().__init__(tickets, timeline)
        self._reverses = reverses

    async def execute(self, actor: TicketActor, ticket_id: UUID, reverse_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        if ticket.status not in REVERSE_DELETE_ALLOWED_STATUSES:
            raise InvalidTransitionError(
                "exclusao de reverso nao permitida neste estado",
                details={"status": ticket.status},
            )
        reverse = await self._reverses.get(reverse_id)
        if reverse is None or reverse.ticket_id != ticket.id:
            raise NotFoundError("codigo reverso nao encontrado")
        await self._reverses.remove(reverse.id)
        now = datetime.now(UTC)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.REVERSO_EXCLUIDO,
                title="Codigo reverso excluido",
                old_value=reverse.code,
                author_user_id=actor.user_id,
            )
        )
        if (
            ticket.status is TicketStatus.AGUARDANDO_ENVIO_REVERSO
            and await self._reverses.count(ticket.id) == 0
        ):
            await self._apply(
                actor, ticket, TicketStatus.APROVADO, "Reversos removidos, ticket aprovado", now
            )
        else:
            touch(ticket, now)
            await self._tickets.update(ticket)


class ReceiveProductUseCase(_TransitionUseCase):
    async def execute(self, actor: TicketActor, ticket_id: UUID) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        now = datetime.now(UTC)
        await self._apply(actor, ticket, TicketStatus.PRODUTO_RECEBIDO, "Produto recebido", now)
        return ticket


class FinalizeTicketUseCase(_TransitionUseCase):
    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        solution_type_id: UUID,
        notes: str | None = None,
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        now = datetime.now(UTC)
        ticket.solution_type_id = solution_type_id
        if notes and notes.strip():
            ticket.final_notes = notes.strip()
        ticket.closed_at = now
        await self._apply(actor, ticket, TicketStatus.FINALIZADO, "Ticket finalizado", now)
        return ticket


class SetWarrantyUseCase(_TransitionUseCase):
    async def execute(
        self,
        actor: TicketActor,
        ticket_id: UUID,
        order_code: str,
        tracking_code: str | None = None,
    ) -> Ticket:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        ensure_can_operate(actor, ticket)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita garantia")
        cleaned = order_code.strip()
        if not cleaned:
            raise ValidationError("codigo do pedido de garantia e obrigatorio")
        ticket.warranty_order_code = cleaned
        ticket.warranty_tracking_code = (
            tracking_code.strip() if tracking_code and tracking_code.strip() else None
        )
        now = datetime.now(UTC)
        await self._timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.GARANTIA_REGISTRADA,
                title="Pedido de garantia registrado",
                new_value=cleaned,
                author_user_id=actor.user_id,
            )
        )
        touch(ticket, now)
        await self._tickets.update(ticket)
        return ticket
```

Imports adicionais necessários no topo do arquivo: `from sac.domain.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError` (consolidar com o existente) e `from sac.domain.tickets import ReverseCode, TicketTimelineEvent, TimelineEventType, is_closed` (consolidar), `from uuid import UUID, uuid4`, `from sac.application.use_cases.tickets_shared import ensure_can_operate` (consolidar).

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_tickets_logistics.py tests/unit/application/test_tickets_workflow.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/tickets_workflow.py backend/tests/unit/application/test_tickets_logistics.py
git commit -m "Adiciona use cases de logistica reversa, finalizacao e garantia"
```

---

### Task 7: Use cases de consulta — lista, detalhe e não lido

**Files:**
- Create: `backend/src/sac/application/use_cases/tickets_queries.py`
- Test: `backend/tests/unit/application/test_tickets_queries.py`

**Interfaces:**
- Consumes: Tasks 3-4 (ports, fakes), `clamp_page` (`use_cases/customers.py`), `sla_state`, `is_closed`, `CLOSED_STATUSES`.
- Produces:
  - `ALLOWED_SORTS = frozenset({"number", "opened_at", "due_at", "last_activity_at"})`
  - `ListTicketsUseCase(tickets, users).execute(actor, filters: TicketFilters, page=1, per_page=20, sort="last_activity_at", order="desc") -> tuple[list[TicketListRow], int]` — visualizador/admin/supervisor veem tudo; atendente é forçado a `attendant_user_id=actor.user_id`; papel sem permissão de ver -> `PermissionDeniedError`; sort fora da lista cai no default; preenche `attendant_name` via `UserDirectoryPort`.
  - `GetTicketDetailUseCase(tickets, items, comments, timeline, reverses, reads, customers, users).execute(actor, ticket_id) -> TicketDetail` — monta o agregado, calcula `sla` com `sla_state(now, due_at, is_closed(ticket))` e marca como lido.
  - `MarkTicketUnreadUseCase(tickets, reads).execute(actor, ticket_id) -> None`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/unit/application/test_tickets_queries.py`:

```python
from uuid import uuid4

from sac.application.ports_tickets import TicketActor, TicketFilters
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
        self.users = InMemoryUserDirectory(
            {ADMIN.user_id: "Admin", ATENDENTE.user_id: "Atendente"}
        )

    async def novo_ticket(self, actor: TicketActor) -> Ticket:
        create = CreateTicketUseCase(
            self.tickets,
            self.items,
            self.customers,
            InMemorySlaPolicyRepository(),
            self.timeline,
            self.reads,
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
    await AddCommentUseCase(env.tickets, env.comments, env.reads).execute(
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_tickets_queries.py -v`
Esperado: FAIL.

- [ ] **Step 3: Implementar**

`backend/src/sac/application/use_cases/tickets_queries.py`:

```python
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_cadastros import CustomerRepository
from sac.application.ports_tickets import (
    ReverseCodeRepository,
    TicketActor,
    TicketCommentRepository,
    TicketDetail,
    TicketFilters,
    TicketItemRepository,
    TicketListRow,
    TicketReadRepository,
    TicketRepository,
    TimelineRepository,
    UserDirectoryPort,
)
from sac.application.use_cases.customers import clamp_page
from sac.application.use_cases.tickets_shared import get_ticket_or_404
from sac.domain.errors import PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import is_closed, sla_state

ALLOWED_SORTS = frozenset({"number", "opened_at", "due_at", "last_activity_at"})


class ListTicketsUseCase:
    def __init__(self, tickets: TicketRepository, users: UserDirectoryPort) -> None:
        self._tickets = tickets
        self._users = users

    async def execute(
        self,
        actor: TicketActor,
        filters: TicketFilters,
        page: int = 1,
        per_page: int = 20,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[list[TicketListRow], int]:
        page, per_page = clamp_page(page, per_page)
        if not has_permission(actor.role, Permission.VER_TODOS_TICKETS):
            if not has_permission(actor.role, Permission.VER_PROPRIOS_TICKETS):
                raise PermissionDeniedError("sem permissao para listar tickets")
            filters = replace(filters, attendant_user_id=actor.user_id)
        if sort not in ALLOWED_SORTS:
            sort = "last_activity_at"
        if order not in {"asc", "desc"}:
            order = "desc"
        rows, total = await self._tickets.list(
            filters, page, per_page, sort, order, unread_for=actor.user_id
        )
        names = await self._users.names_by_ids(
            {row.ticket.attendant_user_id for row in rows}
        )
        rows = [
            replace(row, attendant_name=names.get(row.ticket.attendant_user_id))
            for row in rows
        ]
        return rows, total


class GetTicketDetailUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        items: TicketItemRepository,
        comments: TicketCommentRepository,
        timeline: TimelineRepository,
        reverses: ReverseCodeRepository,
        reads: TicketReadRepository,
        customers: CustomerRepository,
        users: UserDirectoryPort,
    ) -> None:
        self._tickets = tickets
        self._items = items
        self._comments = comments
        self._timeline = timeline
        self._reverses = reverses
        self._reads = reads
        self._customers = customers
        self._users = users

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> TicketDetail:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        now = datetime.now(UTC)
        items = await self._items.list_by_ticket(ticket.id)
        comments = await self._comments.list_by_ticket(ticket.id)
        timeline = await self._timeline.list_by_ticket(ticket.id)
        reverses = await self._reverses.list_by_ticket(ticket.id)
        customer = (
            await self._customers.get(ticket.customer_id)
            if ticket.customer_id is not None
            else None
        )
        ids: set[UUID] = {ticket.attendant_user_id}
        if ticket.supervisor_user_id is not None:
            ids.add(ticket.supervisor_user_id)
        ids.update(c.author_user_id for c in comments)
        ids.update(e.author_user_id for e in timeline if e.author_user_id is not None)
        ids.update(r.author_user_id for r in reverses if r.author_user_id is not None)
        names = await self._users.names_by_ids(ids)
        await self._reads.mark_read(ticket.id, actor.user_id, now)
        return TicketDetail(
            ticket=ticket,
            sla=sla_state(now, ticket.due_at, is_closed(ticket)),
            customer=customer,
            items=items,
            comments=comments,
            timeline=timeline,
            reverses=reverses,
            user_names=names,
        )


class MarkTicketUnreadUseCase:
    def __init__(self, tickets: TicketRepository, reads: TicketReadRepository) -> None:
        self._tickets = tickets
        self._reads = reads

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        await self._reads.mark_unread(ticket.id, actor.user_id)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/application -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/tickets_queries.py backend/tests/unit/application/test_tickets_queries.py
git commit -m "Adiciona use cases de listagem, detalhe e nao lido de tickets"
```

---

### Task 8: Models, sequence, migration 0003 e seeds de SLA

**Files:**
- Modify: `backend/src/sac/infrastructure/models_tenant.py`
- Create: `backend/migrations/tenant/versions/0003_tickets.py`
- Modify: `backend/src/sac/infrastructure/tenant_seeds.py`
- Test: `backend/tests/integration/test_tickets_schema.py`

**Interfaces:**
- Consumes: `TenantBase`, `TenantTableMixin` (models_tenant.py), `seed_tenant_defaults` (tenant_seeds.py), fixtures de integração (`engine`, `session`) e `seed_provisioned_tenant` (helpers.py).
- Produces (models_tenant.py): `TICKET_NUMBER_SEQ = Sequence("ticket_number_seq", schema="tenant")`, `TicketModel` (tabela `tickets`, sem coluna `active`), `TicketItemModel`, `TicketCommentModel`, `TicketTimelineEventModel`, `TicketReadModel` (PK composta), `ReverseCodeModel`, `SlaPolicyModel` (tabela `sla_policies`). Constraints NOMEADAS (usadas pela Task 9): `uq_tickets_number`, `fk_tickets_brand_id`, `fk_tickets_customer_id`, `fk_tickets_purchase_channel_id`, `fk_tickets_solution_type_id`, `fk_ticket_items_ticket_id`, `fk_ticket_items_product_id`, `fk_ticket_items_defect_type_id`, `ck_ticket_items_quantity`, `fk_ticket_comments_ticket_id`, `fk_ticket_comments_reply_to_id`, `fk_ticket_timeline_events_ticket_id`, `fk_ticket_reads_ticket_id`, `fk_reverse_codes_ticket_id`, `uq_sla_policies_priority`.
- Produces (tenant_seeds.py): `DEFAULT_SLA_POLICIES_ROWS` semeadas por `seed_tenant_defaults` (idempotente por priority).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_tickets_schema.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.infrastructure.models_tenant import BrandModel, SlaPolicyModel, TicketModel
from tests.integration.helpers import seed_provisioned_tenant


def _tenant_factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


def _ticket_model(brand_id: UUID) -> TicketModel:
    return TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=uuid4(),
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )


async def test_sequence_numera_sem_reuso(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="seqtest")
    factory = _tenant_factory(engine, tenant.schema_name)
    async with factory() as ts:
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        first = _ticket_model(brand_id)
        second = _ticket_model(brand_id)
        ts.add(first)
        await ts.flush()
        ts.add(second)
        await ts.flush()
        assert first.number == 1
        assert second.number == 2
        await ts.commit()


async def test_provisionamento_semeia_sla_policies(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="slatest")
    factory = _tenant_factory(engine, tenant.schema_name)
    async with factory() as ts:
        rows = (await ts.scalars(select(SlaPolicyModel))).all()
        by_priority = {r.priority: r for r in rows}
        assert by_priority["urgente"].hours == 24
        assert by_priority["alta"].hours == 48
        assert by_priority["media"].hours == 72
        assert by_priority["baixa"].hours == 120
        assert all(r.warn_hours == 12 for r in rows)


async def test_sequences_isoladas_por_tenant(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant_a = await seed_provisioned_tenant(session, engine, slug="seqa")
    tenant_b = await seed_provisioned_tenant(session, engine, slug="seqb")
    for schema in (tenant_a.schema_name, tenant_b.schema_name):
        factory = _tenant_factory(engine, schema)
        async with factory() as ts:
            brand_id = (await ts.scalars(select(BrandModel.id))).first()
            assert brand_id is not None
            ticket = _ticket_model(brand_id)
            ts.add(ticket)
            await ts.flush()
            assert ticket.number == 1
            await ts.commit()
```

Nota: `opened_at` e `last_activity_at` têm `server_default=func.now()` no model (Step 3); `due_at` é `nullable=False` sem default e por isso `_ticket_model` o preenche explicitamente.

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_tickets_schema.py -v` (com o Postgres de pé)
Esperado: FAIL (models/migration inexistentes).

- [ ] **Step 3: Implementar models**

Acrescentar em `backend/src/sac/infrastructure/models_tenant.py` (imports adicionais: `BigInteger`, `CheckConstraint`, `Date`, `ForeignKey`, `Integer`, `PrimaryKeyConstraint`, `Sequence`, `UniqueConstraint` de sqlalchemy; `date` de datetime):

```python
TICKET_NUMBER_SEQ = Sequence("ticket_number_seq", schema="tenant")


class TicketModel(TenantBase):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("number", name="uq_tickets_number"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    number: Mapped[int] = mapped_column(BigInteger, TICKET_NUMBER_SEQ, nullable=False)
    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.brands.id", name="fk_tickets_brand_id"), nullable=False
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.customers.id", name="fk_tickets_customer_id"), nullable=True
    )
    attendant_user_id: Mapped[UUID] = mapped_column(nullable=False)
    supervisor_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    purchase_channel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.purchase_channels.id", name="fk_tickets_purchase_channel_id"),
        nullable=True,
    )
    order_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.solution_types.id", name="fk_tickets_solution_type_id"),
        nullable=True,
    )
    warranty_order_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    warranty_tracking_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketItemModel(TenantBase):
    __tablename__ = "ticket_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_ticket_items_quantity"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_items_ticket_id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.products.id", name="fk_ticket_items_product_id"), nullable=False
    )
    defect_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.defect_types.id", name="fk_ticket_items_defect_type_id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TicketCommentModel(TenantBase):
    __tablename__ = "ticket_comments"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_comments_ticket_id"), nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(nullable=False)
    reply_to_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.ticket_comments.id", name="fk_ticket_comments_reply_to_id"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketTimelineEventModel(TenantBase):
    __tablename__ = "ticket_timeline_events"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_timeline_events_ticket_id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketReadModel(TenantBase):
    __tablename__ = "ticket_reads"
    __table_args__ = (
        PrimaryKeyConstraint("ticket_id", "user_id", name="pk_ticket_reads"),
        {"schema": "tenant"},
    )

    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_reads_ticket_id")
    )
    user_id: Mapped[UUID] = mapped_column()
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReverseCodeModel(TenantBase):
    __tablename__ = "reverse_codes"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_reverse_codes_ticket_id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    author_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SlaPolicyModel(TenantBase):
    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("priority", name="uq_sla_policies_priority"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

O `number` usa `Sequence` do SQLAlchemy: em runtime o `schema_translate_map` traduz `tenant.ticket_number_seq` para `t_<slug>.ticket_number_seq`, e o ORM busca `nextval` no flush — numeração sem race condition e por tenant.

- [ ] **Step 4: Implementar a migration**

`backend/migrations/tenant/versions/0003_tickets.py`:

```python
"""tickets do tenant

Revision ID: 0003_tickets
Revises: 0002_cadastros
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSequence, DropSequence

revision = "0003_tickets"
down_revision = "0002_cadastros"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(CreateSequence(sa.Sequence("ticket_number_seq", schema="tenant")))
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("number", sa.BigInteger(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("attendant_user_id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("purchase_channel_id", sa.Uuid(), nullable=True),
        sa.Column("order_code", sa.String(60), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("final_notes", sa.Text(), nullable=True),
        sa.Column("solution_type_id", sa.Uuid(), nullable=True),
        sa.Column("warranty_order_code", sa.String(60), nullable=True),
        sa.Column("warranty_tracking_code", sa.String(60), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("number", name="uq_tickets_number"),
        sa.ForeignKeyConstraint(["brand_id"], ["tenant.brands.id"], name="fk_tickets_brand_id"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["tenant.customers.id"], name="fk_tickets_customer_id"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_channel_id"],
            ["tenant.purchase_channels.id"],
            name="fk_tickets_purchase_channel_id",
        ),
        sa.ForeignKeyConstraint(
            ["solution_type_id"],
            ["tenant.solution_types.id"],
            name="fk_tickets_solution_type_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("defect_type_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity >= 1", name="ck_ticket_items_quantity"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_items_ticket_id"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["tenant.products.id"], name="fk_ticket_items_product_id"
        ),
        sa.ForeignKeyConstraint(
            ["defect_type_id"],
            ["tenant.defect_types.id"],
            name="fk_ticket_items_defect_type_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_comments_ticket_id"
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["tenant.ticket_comments.id"],
            name="fk_ticket_comments_reply_to_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_timeline_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_timeline_events_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_reads",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticket_id", "user_id", name="pk_ticket_reads"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_reads_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "reverse_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_reverse_codes_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("warn_hours", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("priority", name="uq_sla_policies_priority"),
        schema="tenant",
    )
    op.create_index("ix_tickets_status", "tickets", ["status"], schema="tenant")
    op.create_index(
        "ix_tickets_last_activity_at", "tickets", ["last_activity_at"], schema="tenant"
    )
    op.create_index("ix_tickets_due_at", "tickets", ["due_at"], schema="tenant")
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"], schema="tenant")
    op.create_index(
        "ix_tickets_attendant_user_id", "tickets", ["attendant_user_id"], schema="tenant"
    )
    op.create_index("ix_ticket_items_ticket_id", "ticket_items", ["ticket_id"], schema="tenant")
    op.create_index(
        "ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"], schema="tenant"
    )
    op.create_index(
        "ix_ticket_timeline_events_ticket_id",
        "ticket_timeline_events",
        ["ticket_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_reverse_codes_ticket_id", "reverse_codes", ["ticket_id"], schema="tenant"
    )


def downgrade() -> None:
    for table in (
        "sla_policies",
        "reverse_codes",
        "ticket_reads",
        "ticket_timeline_events",
        "ticket_comments",
        "ticket_items",
        "tickets",
    ):
        op.drop_table(table, schema="tenant")
    op.execute(DropSequence(sa.Sequence("ticket_number_seq", schema="tenant")))
```

- [ ] **Step 5: Semear sla_policies**

Em `backend/src/sac/infrastructure/tenant_seeds.py`, acrescentar ao final da lista de defaults e dentro de `seed_tenant_defaults` (seguir a estrutura existente do arquivo — a função retorna o número de itens criados):

```python
DEFAULT_SLA_POLICIES_ROWS: list[tuple[str, int, int]] = [
    ("urgente", 24, 12),
    ("alta", 48, 12),
    ("media", 72, 12),
    ("baixa", 120, 12),
]
```

E dentro de `seed_tenant_defaults(session)`, após os loops de catálogo existentes (import de `SlaPolicyModel` e `select` no topo):

```python
    existing_priorities = set(
        (await session.scalars(select(SlaPolicyModel.priority))).all()
    )
    for priority, hours, warn_hours in DEFAULT_SLA_POLICIES_ROWS:
        if priority in existing_priorities:
            continue
        session.add(
            SlaPolicyModel(
                id=uuid4(), priority=priority, hours=hours, warn_hours=warn_hours
            )
        )
        created += 1
```

Ajustar à variável de contagem real usada na função (ler o arquivo antes; hoje ela acumula um contador e o retorno é esse contador).

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_tickets_schema.py tests/integration/test_tenant_seeds.py tests/integration/test_provisioning.py -v`
Esperado: PASS (provisionamento roda a 0003 e semeia SLA; testes antigos de seeds continuam passando).

- [ ] **Step 7: Verificações completas e commit**

```bash
git add backend/src/sac/infrastructure/models_tenant.py backend/migrations/tenant/versions/0003_tickets.py backend/src/sac/infrastructure/tenant_seeds.py backend/tests/integration/test_tickets_schema.py
git commit -m "Adiciona tabelas de tickets, sequence de numeracao e seeds de SLA"
```

---

### Task 9: Repositórios SQL de tickets com erro por constraint

**Files:**
- Create: `backend/src/sac/infrastructure/repositories_tickets.py`
- Test: `backend/tests/integration/test_repositories_tickets.py`

**Interfaces:**
- Consumes: models da Task 8, ports da Task 3, `UserModel` (`infrastructure/models.py`), `normalize_digits` (`domain/documents.py`), `CLOSED_STATUSES`.
- Produces:
  - `SqlTicketRepository(session)`, `SqlTicketItemRepository(session)`, `SqlTicketCommentRepository(session)`, `SqlTimelineRepository(session)`, `SqlReverseCodeRepository(session)`, `SqlTicketReadRepository(session)`, `SqlSlaPolicyRepository(session)`, `SqlUserDirectory(session)` — implementam os protocolos da Task 3.
  - `TicketRepos` (dataclass bundle: `tickets`, `items`, `comments`, `timeline`, `reverses`, `reads`, `sla`, `customers: SqlCustomerRepository`, `users`) e `build_ticket_repos(session) -> TicketRepos`.
  - `flush_tickets(session)` — dívida da Fase 1: traduz `IntegrityError` pelo NOME da constraint: FKs conhecidas -> `ValidationError("registro relacionado inexistente", details={"field": ...})` (422); `uq_tickets_number`/`uq_sla_policies_priority` -> `ConflictError`; `ck_ticket_items_quantity` -> `ValidationError`; desconhecida -> re-raise.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/integration/test_repositories_tickets.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_tickets import TicketFilters
from sac.domain.errors import ValidationError
from sac.domain.tickets import (
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
)
from sac.infrastructure.models_tenant import BrandModel, DefectTypeModel, ProductModel
from sac.infrastructure.repositories_cadastros import SqlProductRepository
from sac.infrastructure.repositories_tickets import build_ticket_repos
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


def _novo_ticket(brand_id: UUID, attendant: UUID, **overrides: object) -> Ticket:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "id": uuid4(),
        "number": 0,
        "brand_id": brand_id,
        "status": TicketStatus.ABERTO,
        "priority": TicketPriority.MEDIA,
        "attendant_user_id": attendant,
        "opened_at": now,
        "due_at": now + timedelta(hours=72),
        "last_activity_at": now,
    }
    base.update(overrides)
    return Ticket(**base)  # type: ignore[arg-type]


async def test_roundtrip_add_get_update_e_numero(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repot")
    user = await seed_user(session, email="repot@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        ticket = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        assert ticket.number >= 1
        loaded = await repos.tickets.get(ticket.id)
        assert loaded is not None and loaded.number == ticket.number
        loaded.status = TicketStatus.AGUARDANDO_ANALISE
        loaded.description = "atualizado"
        await repos.tickets.update(loaded)
        again = await repos.tickets.get(ticket.id)
        assert again is not None
        assert again.status is TicketStatus.AGUARDANDO_ANALISE
        assert again.description == "atualizado"
        await ts.commit()


async def test_fk_invalida_vira_validation_error_422(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repofk")
    user = await seed_user(session, email="repofk@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        with pytest.raises(ValidationError) as exc:
            await repos.tickets.add(_novo_ticket(uuid4(), user.id))
        assert exc.value.details.get("field") == "brand_id"


async def test_list_filtros_unread_e_overdue(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repolist")
    user = await seed_user(session, email="repolist@t.com")
    leitor = await seed_user(session, email="leitor@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        defect_id = (await ts.scalars(select(DefectTypeModel.id))).first()
        assert defect_id is not None
        ts.add(ProductModel(id=uuid4(), name="Alicate X", sku="ALX-1"))
        await ts.flush()
        product_id = (
            await ts.scalars(select(ProductModel.id).where(ProductModel.sku == "ALX-1"))
        ).first()
        assert product_id is not None
        atrasado = await repos.tickets.add(
            _novo_ticket(
                brand_id,
                user.id,
                due_at=datetime.now(UTC) - timedelta(hours=1),
                order_code="PED-1",
            )
        )
        no_prazo = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        await repos.items.add(
            TicketItem(
                id=uuid4(),
                ticket_id=atrasado.id,
                product_id=product_id,
                defect_type_id=defect_id,
                quantity=2,
            )
        )
        await ts.flush()

        rows, total = await repos.tickets.list(
            TicketFilters(), 1, 20, "last_activity_at", "desc", unread_for=leitor.id
        )
        assert total == 2
        assert all(row.unread for row in rows)

        rows, total = await repos.tickets.list(
            TicketFilters(overdue=True), 1, 20, "last_activity_at", "desc", unread_for=leitor.id
        )
        assert total == 1 and rows[0].ticket.id == atrasado.id
        assert rows[0].items_count == 1
        assert rows[0].first_product_name == "Alicate X"

        rows, total = await repos.tickets.list(
            TicketFilters(product_id=product_id),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=leitor.id,
        )
        assert total == 1

        rows, total = await repos.tickets.list(
            TicketFilters(order_code="PED-1"),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=leitor.id,
        )
        assert total == 1

        await repos.reads.mark_read(no_prazo.id, leitor.id, datetime.now(UTC))
        await ts.flush()
        rows, _ = await repos.tickets.list(
            TicketFilters(), 1, 20, "number", "asc", unread_for=leitor.id
        )
        by_id = {row.ticket.id: row for row in rows}
        assert by_id[atrasado.id].unread is True
        assert by_id[no_prazo.id].unread is False
        await ts.commit()


async def test_busca_por_cliente_nome_ou_documento(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repocli")
    user = await seed_user(session, email="repocli@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        from sac.domain.cadastros import Customer

        customer = Customer(id=uuid4(), name="Joana Prado", document="39053344705")
        await repos.customers.add(customer)
        com_cliente = await repos.tickets.add(
            _novo_ticket(brand_id, user.id, customer_id=customer.id)
        )
        await repos.tickets.add(_novo_ticket(brand_id, user.id))
        for termo in ("joana", "390.533.447-05", "39053344705"):
            rows, total = await repos.tickets.list(
                TicketFilters(customer=termo),
                1,
                20,
                "last_activity_at",
                "desc",
                unread_for=user.id,
            )
            assert total == 1, termo
            assert rows[0].ticket.id == com_cliente.id
            assert rows[0].customer_name == "Joana Prado"
        await ts.commit()


async def test_satelites_comentario_timeline_reverso_read_sla(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="reposat")
    user = await seed_user(session, email="reposat@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        ticket = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        comment = TicketComment(
            id=uuid4(), ticket_id=ticket.id, author_user_id=user.id, body="oi"
        )
        await repos.comments.add(comment)
        reply = TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=user.id,
            body="resposta",
            reply_to_id=comment.id,
        )
        await repos.comments.add(reply)
        listed = await repos.comments.list_by_ticket(ticket.id)
        assert [c.body for c in listed] == ["oi", "resposta"]

        from sac.domain.tickets import ReverseCode, TicketTimelineEvent, TimelineEventType

        await repos.timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.CRIACAO,
                title="Ticket criado",
                author_user_id=user.id,
            )
        )
        events = await repos.timeline.list_by_ticket(ticket.id)
        assert events[0].type is TimelineEventType.CRIACAO

        reverse = ReverseCode(id=uuid4(), ticket_id=ticket.id, code="BR1", author_user_id=user.id)
        await repos.reverses.add(reverse)
        assert await repos.reverses.count(ticket.id) == 1
        await repos.reverses.remove(reverse.id)
        assert await repos.reverses.count(ticket.id) == 0

        now = datetime.now(UTC)
        await repos.reads.mark_read(ticket.id, user.id, now)
        await repos.reads.mark_read(ticket.id, user.id, now + timedelta(minutes=1))
        stored = await repos.reads.last_read_at(ticket.id, user.id)
        assert stored is not None
        await repos.reads.mark_unread(ticket.id, user.id)
        assert await repos.reads.last_read_at(ticket.id, user.id) is None

        from sac.domain.tickets import TicketPriority as TP

        policy = await repos.sla.get(TP.URGENTE)
        assert policy is not None and policy.hours == 24

        names = await repos.users.names_by_ids({user.id})
        assert names[user.id] == user.name
        await ts.commit()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_repositories_tickets.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar**

`backend/src/sac/infrastructure/repositories_tickets.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_tickets import TicketFilters, TicketItemView, TicketListRow
from sac.domain.documents import normalize_digits
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.tickets import (
    CLOSED_STATUSES,
    ReverseCode,
    SlaPolicy,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
)
from sac.infrastructure.models import UserModel
from sac.infrastructure.models_tenant import (
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    ReverseCodeModel,
    SlaPolicyModel,
    TicketCommentModel,
    TicketItemModel,
    TicketModel,
    TicketReadModel,
    TicketTimelineEventModel,
)
from sac.infrastructure.repositories_cadastros import SqlCustomerRepository

_FK_FIELDS: dict[str, str] = {
    "fk_tickets_brand_id": "brand_id",
    "fk_tickets_customer_id": "customer_id",
    "fk_tickets_purchase_channel_id": "purchase_channel_id",
    "fk_tickets_solution_type_id": "solution_type_id",
    "fk_ticket_items_ticket_id": "ticket_id",
    "fk_ticket_items_product_id": "product_id",
    "fk_ticket_items_defect_type_id": "defect_type_id",
    "fk_ticket_comments_ticket_id": "ticket_id",
    "fk_ticket_comments_reply_to_id": "reply_to_id",
    "fk_ticket_timeline_events_ticket_id": "ticket_id",
    "fk_ticket_reads_ticket_id": "ticket_id",
    "fk_reverse_codes_ticket_id": "ticket_id",
}
_UNIQUE_CONSTRAINTS: dict[str, str] = {
    "uq_tickets_number": "numero de ticket ja utilizado",
    "uq_sla_policies_priority": "prioridade de SLA ja cadastrada",
}
_CHECK_CONSTRAINTS: dict[str, str] = {
    "ck_ticket_items_quantity": "quantidade minima e 1",
}


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = exc.orig
    name = getattr(orig, "constraint_name", None)
    if name:
        return str(name)
    cause = getattr(orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return str(name) if name else None


async def flush_tickets(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        name = _constraint_name(exc)
        if name in _FK_FIELDS:
            raise ValidationError(
                "registro relacionado inexistente", details={"field": _FK_FIELDS[name]}
            ) from exc
        if name in _UNIQUE_CONSTRAINTS:
            raise ConflictError(_UNIQUE_CONSTRAINTS[name]) from exc
        if name in _CHECK_CONSTRAINTS:
            raise ValidationError(_CHECK_CONSTRAINTS[name]) from exc
        raise


def _ticket_entity(m: TicketModel) -> Ticket:
    return Ticket(
        id=m.id,
        number=m.number,
        brand_id=m.brand_id,
        status=TicketStatus(m.status),
        priority=TicketPriority(m.priority),
        attendant_user_id=m.attendant_user_id,
        opened_at=m.opened_at,
        due_at=m.due_at,
        last_activity_at=m.last_activity_at,
        customer_id=m.customer_id,
        supervisor_user_id=m.supervisor_user_id,
        purchase_channel_id=m.purchase_channel_id,
        order_code=m.order_code,
        purchase_date=m.purchase_date,
        delivery_date=m.delivery_date,
        description=m.description,
        decision_notes=m.decision_notes,
        final_notes=m.final_notes,
        solution_type_id=m.solution_type_id,
        warranty_order_code=m.warranty_order_code,
        warranty_tracking_code=m.warranty_tracking_code,
        submitted_at=m.submitted_at,
        approved_at=m.approved_at,
        declined_at=m.declined_at,
        closed_at=m.closed_at,
        deleted_at=m.deleted_at,
    )


_TICKET_FIELDS = (
    "brand_id",
    "customer_id",
    "attendant_user_id",
    "supervisor_user_id",
    "purchase_channel_id",
    "order_code",
    "purchase_date",
    "delivery_date",
    "description",
    "decision_notes",
    "final_notes",
    "solution_type_id",
    "warranty_order_code",
    "warranty_tracking_code",
    "opened_at",
    "submitted_at",
    "approved_at",
    "declined_at",
    "closed_at",
    "last_activity_at",
    "due_at",
    "deleted_at",
)

_SORT_COLUMNS = {
    "number": TicketModel.number,
    "opened_at": TicketModel.opened_at,
    "due_at": TicketModel.due_at,
    "last_activity_at": TicketModel.last_activity_at,
}


class SqlTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, ticket: Ticket) -> Ticket:
        model = TicketModel(id=ticket.id, status=str(ticket.status), priority=str(ticket.priority))
        for field in _TICKET_FIELDS:
            setattr(model, field, getattr(ticket, field))
        self._session.add(model)
        await flush_tickets(self._session)
        await self._session.refresh(model, attribute_names=["number"])
        ticket.number = model.number
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        m = await self._session.get(TicketModel, ticket_id)
        return _ticket_entity(m) if m and m.deleted_at is None else None

    async def update(self, ticket: Ticket) -> None:
        m = await self._session.get(TicketModel, ticket.id)
        if m is None:
            raise NotFoundError("ticket nao encontrado")
        m.status = str(ticket.status)
        m.priority = str(ticket.priority)
        for field in _TICKET_FIELDS:
            setattr(m, field, getattr(ticket, field))
        await flush_tickets(self._session)

    def _base_stmt(self, filters: TicketFilters) -> Select[tuple[TicketModel]]:
        stmt = select(TicketModel).where(TicketModel.deleted_at.is_(None))
        if filters.status is not None:
            stmt = stmt.where(TicketModel.status == str(filters.status))
        if filters.brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == filters.brand_id)
        if filters.customer_id is not None:
            stmt = stmt.where(TicketModel.customer_id == filters.customer_id)
        if filters.priority is not None:
            stmt = stmt.where(TicketModel.priority == str(filters.priority))
        if filters.attendant_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == filters.attendant_user_id)
        if filters.order_code:
            stmt = stmt.where(TicketModel.order_code.ilike(f"%{filters.order_code}%"))
        if filters.overdue:
            stmt = stmt.where(
                TicketModel.due_at < func.now(),
                TicketModel.status.not_in([str(s) for s in CLOSED_STATUSES]),
            )
        if filters.customer:
            digits = normalize_digits(filters.customer)
            customer_match = (
                or_(
                    CustomerModel.name.ilike(f"%{filters.customer}%"),
                    CustomerModel.document.like(f"%{digits}%"),
                )
                if digits
                else CustomerModel.name.ilike(f"%{filters.customer}%")
            )
            stmt = stmt.where(
                TicketModel.customer_id.in_(
                    select(CustomerModel.id).where(customer_match)
                )
            )
        if filters.product_id is not None:
            stmt = stmt.where(
                exists(
                    select(TicketItemModel.id).where(
                        TicketItemModel.ticket_id == TicketModel.id,
                        TicketItemModel.product_id == filters.product_id,
                    )
                )
            )
        return stmt

    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]:
        stmt = self._base_stmt(filters)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        column = _SORT_COLUMNS.get(sort, TicketModel.last_activity_at)
        rows_stmt = (
            self._base_stmt(filters)
            .add_columns(CustomerModel.name, TicketReadModel.last_read_at)
            .outerjoin(CustomerModel, TicketModel.customer_id == CustomerModel.id)
            .outerjoin(
                TicketReadModel,
                (TicketReadModel.ticket_id == TicketModel.id)
                & (TicketReadModel.user_id == unread_for),
            )
            .order_by(column.desc() if order == "desc" else column.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(rows_stmt)
        models: list[tuple[TicketModel, str | None, datetime | None]] = [
            (row[0], row[1], row[2]) for row in result.all()
        ]
        ticket_ids = [m.id for m, _, _ in models]
        counts: dict[UUID, int] = {}
        first_products: dict[UUID, str] = {}
        if ticket_ids:
            count_rows = await self._session.execute(
                select(TicketItemModel.ticket_id, func.count())
                .where(TicketItemModel.ticket_id.in_(ticket_ids))
                .group_by(TicketItemModel.ticket_id)
            )
            counts = {row[0]: int(row[1]) for row in count_rows.all()}
            first_rows = await self._session.execute(
                select(TicketItemModel.ticket_id, ProductModel.name)
                .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
                .where(TicketItemModel.ticket_id.in_(ticket_ids))
                .order_by(TicketItemModel.ticket_id, TicketItemModel.created_at)
                .distinct(TicketItemModel.ticket_id)
            )
            first_products = {row[0]: row[1] for row in first_rows.all()}
        rows = [
            TicketListRow(
                ticket=_ticket_entity(m),
                customer_name=customer_name,
                first_product_name=first_products.get(m.id),
                items_count=counts.get(m.id, 0),
                unread=last_read is None or last_read < m.last_activity_at,
            )
            for m, customer_name, last_read in models
        ]
        return rows, int(total or 0)
```

Nota: o `distinct(TicketItemModel.ticket_id)` usa `DISTINCT ON` do PostgreSQL, que exige o `order_by` iniciando pela mesma coluna (já garantido acima).

Continuação do arquivo:

```python
class SqlTicketItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]:
        result = await self._session.execute(
            select(TicketItemModel, ProductModel.name, DefectTypeModel.name)
            .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
            .join(DefectTypeModel, TicketItemModel.defect_type_id == DefectTypeModel.id)
            .where(TicketItemModel.ticket_id == ticket_id)
            .order_by(TicketItemModel.created_at)
        )
        return [
            TicketItemView(
                item=TicketItem(
                    id=m.id,
                    ticket_id=m.ticket_id,
                    product_id=m.product_id,
                    defect_type_id=m.defect_type_id,
                    quantity=m.quantity,
                ),
                product_name=product_name,
                defect_type_name=defect_name,
            )
            for m, product_name, defect_name in result.all()
        ]

    async def count(self, ticket_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(TicketItemModel.ticket_id == ticket_id)
        )
        return int(total or 0)

    async def get(self, item_id: UUID) -> TicketItem | None:
        m = await self._session.get(TicketItemModel, item_id)
        if m is None:
            return None
        return TicketItem(
            id=m.id,
            ticket_id=m.ticket_id,
            product_id=m.product_id,
            defect_type_id=m.defect_type_id,
            quantity=m.quantity,
        )

    async def add(self, item: TicketItem) -> None:
        self._session.add(
            TicketItemModel(
                id=item.id,
                ticket_id=item.ticket_id,
                product_id=item.product_id,
                defect_type_id=item.defect_type_id,
                quantity=item.quantity,
            )
        )
        await flush_tickets(self._session)

    async def update(self, item: TicketItem) -> None:
        m = await self._session.get(TicketItemModel, item.id)
        if m is None:
            raise NotFoundError("item nao encontrado")
        m.product_id = item.product_id
        m.defect_type_id = item.defect_type_id
        m.quantity = item.quantity
        await flush_tickets(self._session)

    async def remove(self, item_id: UUID) -> None:
        m = await self._session.get(TicketItemModel, item_id)
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)


class SqlTicketCommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]:
        result = await self._session.scalars(
            select(TicketCommentModel)
            .where(TicketCommentModel.ticket_id == ticket_id)
            .order_by(TicketCommentModel.created_at)
        )
        return [
            TicketComment(
                id=m.id,
                ticket_id=m.ticket_id,
                author_user_id=m.author_user_id,
                body=m.body,
                reply_to_id=m.reply_to_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def get(self, comment_id: UUID) -> TicketComment | None:
        m = await self._session.get(TicketCommentModel, comment_id)
        if m is None:
            return None
        return TicketComment(
            id=m.id,
            ticket_id=m.ticket_id,
            author_user_id=m.author_user_id,
            body=m.body,
            reply_to_id=m.reply_to_id,
            created_at=m.created_at,
        )

    async def add(self, comment: TicketComment) -> None:
        self._session.add(
            TicketCommentModel(
                id=comment.id,
                ticket_id=comment.ticket_id,
                author_user_id=comment.author_user_id,
                body=comment.body,
                reply_to_id=comment.reply_to_id,
            )
        )
        await flush_tickets(self._session)


class SqlTimelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]:
        result = await self._session.scalars(
            select(TicketTimelineEventModel)
            .where(TicketTimelineEventModel.ticket_id == ticket_id)
            .order_by(TicketTimelineEventModel.created_at)
        )
        return [
            TicketTimelineEvent(
                id=m.id,
                ticket_id=m.ticket_id,
                type=TimelineEventType(m.type),
                title=m.title,
                old_value=m.old_value,
                new_value=m.new_value,
                author_user_id=m.author_user_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def add(self, event: TicketTimelineEvent) -> None:
        self._session.add(
            TicketTimelineEventModel(
                id=event.id,
                ticket_id=event.ticket_id,
                type=str(event.type),
                title=event.title,
                old_value=event.old_value,
                new_value=event.new_value,
                author_user_id=event.author_user_id,
            )
        )
        await flush_tickets(self._session)


class SqlReverseCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]:
        result = await self._session.scalars(
            select(ReverseCodeModel)
            .where(ReverseCodeModel.ticket_id == ticket_id)
            .order_by(ReverseCodeModel.created_at)
        )
        return [
            ReverseCode(
                id=m.id,
                ticket_id=m.ticket_id,
                code=m.code,
                author_user_id=m.author_user_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def count(self, ticket_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(ReverseCodeModel.ticket_id == ticket_id)
        )
        return int(total or 0)

    async def get(self, reverse_id: UUID) -> ReverseCode | None:
        m = await self._session.get(ReverseCodeModel, reverse_id)
        if m is None:
            return None
        return ReverseCode(
            id=m.id,
            ticket_id=m.ticket_id,
            code=m.code,
            author_user_id=m.author_user_id,
            created_at=m.created_at,
        )

    async def add(self, reverse: ReverseCode) -> None:
        self._session.add(
            ReverseCodeModel(
                id=reverse.id,
                ticket_id=reverse.ticket_id,
                code=reverse.code,
                author_user_id=reverse.author_user_id,
            )
        )
        await flush_tickets(self._session)

    async def remove(self, reverse_id: UUID) -> None:
        m = await self._session.get(ReverseCodeModel, reverse_id)
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)


class SqlTicketReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None:
        stmt = (
            pg_insert(TicketReadModel)
            .values(ticket_id=ticket_id, user_id=user_id, last_read_at=at)
            .on_conflict_do_update(
                index_elements=["ticket_id", "user_id"], set_={"last_read_at": at}
            )
        )
        await self._session.execute(stmt)

    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None:
        m = await self._session.get(TicketReadModel, (ticket_id, user_id))
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)

    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None:
        m = await self._session.get(TicketReadModel, (ticket_id, user_id))
        return m.last_read_at if m else None


class SqlSlaPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, priority: TicketPriority) -> SlaPolicy | None:
        m = await self._session.scalar(
            select(SlaPolicyModel).where(SlaPolicyModel.priority == str(priority))
        )
        if m is None:
            return None
        return SlaPolicy(
            priority=TicketPriority(m.priority), hours=m.hours, warn_hours=m.warn_hours
        )


class SqlUserDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        result = await self._session.execute(
            select(UserModel.id, UserModel.name).where(UserModel.id.in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}


@dataclass
class TicketRepos:
    tickets: SqlTicketRepository
    items: SqlTicketItemRepository
    comments: SqlTicketCommentRepository
    timeline: SqlTimelineRepository
    reverses: SqlReverseCodeRepository
    reads: SqlTicketReadRepository
    sla: SqlSlaPolicyRepository
    customers: SqlCustomerRepository
    users: SqlUserDirectory


def build_ticket_repos(session: AsyncSession) -> TicketRepos:
    return TicketRepos(
        tickets=SqlTicketRepository(session),
        items=SqlTicketItemRepository(session),
        comments=SqlTicketCommentRepository(session),
        timeline=SqlTimelineRepository(session),
        reverses=SqlReverseCodeRepository(session),
        reads=SqlTicketReadRepository(session),
        sla=SqlSlaPolicyRepository(session),
        customers=SqlCustomerRepository(session),
        users=SqlUserDirectory(session),
    )
```

Notas de implementação:
- Se `await self._session.refresh(model, attribute_names=["number"])` falhar por objeto não persistido, alternativa: `ticket.number = (await self._session.execute(select(TicketModel.number).where(TicketModel.id == ticket.id))).scalar_one()`.
- Se o `asyncpg` não expuser `constraint_name` direto em `exc.orig`, o fallback via `__cause__` cobre (o wrapper do SQLAlchemy encadeia a exceção original do asyncpg, que tem `constraint_name`). Validar com o teste de FK.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_repositories_tickets.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/infrastructure/repositories_tickets.py backend/tests/integration/test_repositories_tickets.py
git commit -m "Adiciona repositorios SQL de tickets com erros por constraint"
```

---

### Task 10: Schemas, deps e router — CRUD e itens

**Files:**
- Modify: `backend/src/sac/interface/schemas.py`
- Modify: `backend/src/sac/interface/deps.py`
- Create: `backend/src/sac/interface/routers/tickets.py`
- Modify: `backend/src/sac/interface/app.py`
- Test: `backend/tests/integration/test_tickets_api.py`

**Interfaces:**
- Consumes: use cases das Tasks 3-7, `build_ticket_repos`/`TicketRepos` (Task 9), `get_tenant_session`, `require_permission`, `get_current_identity`, `CustomerIn`/`CustomerOut`/`customer_out` (schemas.py), `sla_state`/`is_closed` (domain).
- Produces (schemas.py):
  - `TicketItemIn(product_id: UUID, defect_type_id: UUID, quantity: int = Field(default=1, ge=1))`
  - `TicketIn(brand_id, priority: TicketPriority, customer: CustomerIn | None = None, customer_id: UUID | None = None, attendant_user_id: UUID | None = None, supervisor_user_id: UUID | None = None, purchase_channel_id: UUID | None = None, order_code: str | None (max 60), purchase_date: date | None, delivery_date: date | None, description: str | None, items: list[TicketItemIn] = [])`
  - `TicketUpdateIn` (mesmos campos gerais, sem `customer`/`items`/`attendant_user_id`)
  - `TicketOut` (todos os campos do ticket + `number` + `sla: SlaState`), builder `ticket_out(ticket: Ticket) -> TicketOut` (calcula `sla` internamente com `datetime.now(UTC)`)
  - `TicketListItemOut(id, number, status, priority, sla, due_at, customer_name, first_product_name, items_count, attendant_name, opened_at, last_activity_at, unread)`, `TicketsPageOut(items, total, page, per_page)`, builder `ticket_list_item_out(row: TicketListRow) -> TicketListItemOut`
  - `TicketItemOut(id, product_id, product_name, defect_type_id, defect_type_name, quantity)`, `TicketCommentOut(id, author_user_id, author_name, body, reply_to_id, created_at)`, `TimelineEventOut(id, type, title, old_value, new_value, author_user_id, author_name, created_at)`, `ReverseCodeOut(id, code, author_user_id, author_name, created_at)`, `TicketDetailOut(ticket: TicketOut, customer: CustomerOut | None, attendant_name, supervisor_name, items, comments, timeline, reverses)`, builder `ticket_detail_out(detail: TicketDetail) -> TicketDetailOut`
- Produces (deps.py): `get_ticket_repos(session=Depends(get_tenant_session)) -> TicketRepos`.
- Produces (routers/tickets.py): router `prefix="/tickets"`, `tags=["tickets"]`, helper `_actor(identity: TokenPayload) -> TicketActor`; rotas desta task: `POST ""` (201, CRIAR_TICKET), `GET ""` (VER_PROPRIOS_TICKETS — todo papel de tenant tem VER_TODOS ou VER_PROPRIOS; usar VER_PROPRIOS como permissão mínima e deixar o use case ampliar/estreitar), `GET "/{ticket_id}"` (VER_PROPRIOS_TICKETS), `PUT "/{ticket_id}"` (EDITAR_PROPRIO_TICKET), `POST "/{ticket_id}/itens"` (201), `PUT "/{ticket_id}/itens/{item_id}"`, `DELETE "/{ticket_id}/itens/{item_id}"` (204) — os três com EDITAR_PROPRIO_TICKET.

ATENÇÃO: `Permission.VER_PROPRIOS_TICKETS` NÃO está no conjunto do VISUALIZADOR (que tem `VER_TODOS_TICKETS`); a permissão mínima da listagem/detalhe deve aceitar qualquer uma das duas. Criar em deps.py uma variação `require_any_permission(*permissions)`:

```python
def require_any_permission(*permissions: Permission) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
    ) -> TokenPayload:
        if identity.role is None or not any(
            has_permission(identity.role, p) for p in permissions
        ):
            raise PermissionDeniedError("permissao insuficiente")
        return identity

    return dependency
```

Rotas de leitura usam `require_any_permission(Permission.VER_TODOS_TICKETS, Permission.VER_PROPRIOS_TICKETS)`; edição usa `require_any_permission(Permission.EDITAR_QUALQUER_TICKET, Permission.EDITAR_PROPRIO_TICKET)`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/integration/test_tickets_api.py`:

```python
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

VALID_CPF = "39053344705"


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str) -> dict[str, object]:
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin Um")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return {
        "tenant": tenant,
        "admin": admin,
        "headers": token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN),
    }


async def _brand_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/marcas", headers=headers)
    assert res.status_code == 200
    return str(res.json()[0]["id"])


async def _defect_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/defeitos", headers=headers)
    return str(res.json()[0]["id"])


async def _product_id(client: AsyncClient, headers: dict[str, str], sku: str) -> str:
    res = await client.post(
        "/api/cadastros/produtos",
        json={"name": f"Produto {sku}", "sku": sku},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_criacao_parcial_e_detalhe(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi1")
    headers = env["headers"]
    brand = await _brand_id(client, headers)
    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=headers
    )
    assert res.status_code == 201
    body = res.json()
    assert body["number"] >= 1
    assert body["status"] == "aberto"
    assert body["sla"] == "no_prazo"

    detail = await client.get(f"/api/tickets/{body['id']}", headers=headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["ticket"]["id"] == body["id"]
    assert data["attendant_name"] == "Admin Um"
    assert data["items"] == []
    assert data["timeline"][0]["type"] == "criacao"


async def test_criacao_completa_com_cliente_inline_e_itens(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi2")
    headers = env["headers"]
    brand = await _brand_id(client, headers)
    defect = await _defect_id(client, headers)
    product = await _product_id(client, headers, "SKU-T2")
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": brand,
            "priority": "urgente",
            "customer": {"name": "Joana", "document": VALID_CPF},
            "description": "chegou quebrado",
            "items": [
                {"product_id": product, "defect_type_id": defect, "quantity": 2}
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201
    ticket = res.json()
    assert ticket["customer_id"] is not None

    detail = await client.get(f"/api/tickets/{ticket['id']}", headers=headers)
    data = detail.json()
    assert data["customer"]["document"] == VALID_CPF
    assert data["items"][0]["quantity"] == 2
    assert data["items"][0]["product_name"] == "Produto SKU-T2"

    clientes = await client.get(
        "/api/cadastros/clientes", params={"search": VALID_CPF}, headers=headers
    )
    assert clientes.json()["total"] == 1


async def test_fk_invalida_da_422_nao_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi3")
    headers = env["headers"]
    res = await client.post(
        "/api/tickets",
        json={"brand_id": str(uuid4()), "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "brand_id"


async def test_lista_com_filtros_e_paginacao(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi4")
    headers = env["headers"]
    brand = await _brand_id(client, headers)
    for priority in ("media", "urgente", "baixa"):
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": priority}, headers=headers
        )
    res = await client.get("/api/tickets", headers=headers)
    body = res.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["items"][0]["unread"] is False  # criador marcou como lido

    res = await client.get("/api/tickets", params={"priority": "urgente"}, headers=headers)
    assert res.json()["total"] == 1

    res = await client.get(
        "/api/tickets", params={"page": 1, "per_page": 2}, headers=headers
    )
    assert len(res.json()["items"]) == 2

    res = await client.get(
        "/api/tickets", params={"sort": "number", "order": "asc"}, headers=headers
    )
    numbers = [item["number"] for item in res.json()["items"]]
    assert numbers == sorted(numbers)


async def test_update_recalcula_sla_e_edita_itens(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi5")
    headers = env["headers"]
    brand = await _brand_id(client, headers)
    defect = await _defect_id(client, headers)
    product = await _product_id(client, headers, "SKU-T5")
    created = (
        await client.post(
            "/api/tickets", json={"brand_id": brand, "priority": "baixa"}, headers=headers
        )
    ).json()
    ticket_id = created["id"]

    res = await client.put(
        f"/api/tickets/{ticket_id}",
        json={"brand_id": brand, "priority": "urgente", "description": "editado"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["due_at"] < created["due_at"]

    res = await client.post(
        f"/api/tickets/{ticket_id}/itens",
        json={"product_id": product, "defect_type_id": defect},
        headers=headers,
    )
    assert res.status_code == 201
    item_id = res.json()["id"]

    res = await client.put(
        f"/api/tickets/{ticket_id}/itens/{item_id}",
        json={"product_id": product, "defect_type_id": defect, "quantity": 3},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["quantity"] == 3

    res = await client.delete(
        f"/api/tickets/{ticket_id}/itens/{item_id}", headers=headers
    )
    assert res.status_code == 204


async def test_visualizador_nao_cria_mas_lista(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    env = await _setup(session, engine, "tapi6")
    tenant = env["tenant"]
    viewer = await seed_user(session, email="viewer@tapi6.com")
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)  # type: ignore[arg-type]
    viewer_headers = token_for(viewer, tenant_slug=tenant.slug, role=Role.VISUALIZADOR)  # type: ignore[attr-defined]
    brand = await _brand_id(client, env["headers"])
    res = await client.post(
        "/api/tickets", json={"brand_id": brand, "priority": "media"}, headers=viewer_headers
    )
    assert res.status_code == 403
    res = await client.get("/api/tickets", headers=viewer_headers)
    assert res.status_code == 200


async def test_sem_token_401(client: AsyncClient) -> None:
    res = await client.get("/api/tickets")
    assert res.status_code == 401
```

Nota: os `# type: ignore` de acesso a `env["tenant"]` podem ser evitados tipando `_setup` com um `NamedTuple`/dataclass local — escolha do implementador, mantendo os cenários.

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_tickets_api.py -v`
Esperado: FAIL (rotas inexistentes, 404).

- [ ] **Step 3: Implementar schemas**

Acrescentar em `backend/src/sac/interface/schemas.py` (imports: `date`, `datetime`, `SlaState`, `TicketPriority`, `TicketStatus`, `TimelineEventType`, `Ticket`, `TicketDetail`, `TicketListRow`, `TicketItemView`, `TicketComment`, `TicketTimelineEvent`, `ReverseCode`, `sla_state`, `is_closed`, `UTC`):

```python
class TicketItemIn(BaseModel):
    product_id: UUID
    defect_type_id: UUID
    quantity: int = Field(default=1, ge=1)


class TicketIn(BaseModel):
    brand_id: UUID
    priority: TicketPriority
    customer: CustomerIn | None = None
    customer_id: UUID | None = None
    attendant_user_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = Field(default=None, max_length=60)
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None
    items: list[TicketItemIn] = Field(default_factory=list)


class TicketUpdateIn(BaseModel):
    brand_id: UUID
    priority: TicketPriority
    customer_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = Field(default=None, max_length=60)
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None


class TicketOut(BaseModel):
    id: UUID
    number: int
    status: TicketStatus
    priority: TicketPriority
    sla: SlaState
    brand_id: UUID
    customer_id: UUID | None
    attendant_user_id: UUID
    supervisor_user_id: UUID | None
    purchase_channel_id: UUID | None
    order_code: str | None
    purchase_date: date | None
    delivery_date: date | None
    description: str | None
    decision_notes: str | None
    final_notes: str | None
    solution_type_id: UUID | None
    warranty_order_code: str | None
    warranty_tracking_code: str | None
    opened_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    declined_at: datetime | None
    closed_at: datetime | None
    last_activity_at: datetime
    due_at: datetime


def ticket_out(ticket: Ticket) -> TicketOut:
    now = datetime.now(UTC)
    return TicketOut(
        sla=sla_state(now, ticket.due_at, is_closed(ticket)),
        **{f: getattr(ticket, f) for f in TicketOut.model_fields if f != "sla"},
    )


class TicketListItemOut(BaseModel):
    id: UUID
    number: int
    status: TicketStatus
    priority: TicketPriority
    sla: SlaState
    due_at: datetime
    customer_name: str | None
    first_product_name: str | None
    items_count: int
    attendant_name: str | None
    opened_at: datetime
    last_activity_at: datetime
    unread: bool


class TicketsPageOut(BaseModel):
    items: list[TicketListItemOut]
    total: int
    page: int
    per_page: int


def ticket_list_item_out(row: TicketListRow) -> TicketListItemOut:
    t = row.ticket
    now = datetime.now(UTC)
    return TicketListItemOut(
        id=t.id,
        number=t.number,
        status=t.status,
        priority=t.priority,
        sla=sla_state(now, t.due_at, is_closed(t)),
        due_at=t.due_at,
        customer_name=row.customer_name,
        first_product_name=row.first_product_name,
        items_count=row.items_count,
        attendant_name=row.attendant_name,
        opened_at=t.opened_at,
        last_activity_at=t.last_activity_at,
        unread=row.unread,
    )


class TicketItemOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    defect_type_id: UUID
    defect_type_name: str
    quantity: int


def ticket_item_out(view: TicketItemView) -> TicketItemOut:
    return TicketItemOut(
        id=view.item.id,
        product_id=view.item.product_id,
        product_name=view.product_name,
        defect_type_id=view.item.defect_type_id,
        defect_type_name=view.defect_type_name,
        quantity=view.item.quantity,
    )


class TicketCommentOut(BaseModel):
    id: UUID
    author_user_id: UUID
    author_name: str | None
    body: str
    reply_to_id: UUID | None
    created_at: datetime | None


class TimelineEventOut(BaseModel):
    id: UUID
    type: TimelineEventType
    title: str
    old_value: str | None
    new_value: str | None
    author_user_id: UUID | None
    author_name: str | None
    created_at: datetime | None


class ReverseCodeOut(BaseModel):
    id: UUID
    code: str
    author_user_id: UUID | None
    author_name: str | None
    created_at: datetime | None


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    customer: CustomerOut | None
    attendant_name: str | None
    supervisor_name: str | None
    items: list[TicketItemOut]
    comments: list[TicketCommentOut]
    timeline: list[TimelineEventOut]
    reverses: list[ReverseCodeOut]


def ticket_detail_out(detail: TicketDetail) -> TicketDetailOut:
    names = detail.user_names
    t = detail.ticket
    return TicketDetailOut(
        ticket=ticket_out(t),
        customer=customer_out(detail.customer) if detail.customer else None,
        attendant_name=names.get(t.attendant_user_id),
        supervisor_name=(
            names.get(t.supervisor_user_id) if t.supervisor_user_id else None
        ),
        items=[ticket_item_out(i) for i in detail.items],
        comments=[
            TicketCommentOut(
                id=c.id,
                author_user_id=c.author_user_id,
                author_name=names.get(c.author_user_id),
                body=c.body,
                reply_to_id=c.reply_to_id,
                created_at=c.created_at,
            )
            for c in detail.comments
        ],
        timeline=[
            TimelineEventOut(
                id=e.id,
                type=e.type,
                title=e.title,
                old_value=e.old_value,
                new_value=e.new_value,
                author_user_id=e.author_user_id,
                author_name=names.get(e.author_user_id) if e.author_user_id else None,
                created_at=e.created_at,
            )
            for e in detail.timeline
        ],
        reverses=[
            ReverseCodeOut(
                id=r.id,
                code=r.code,
                author_user_id=r.author_user_id,
                author_name=names.get(r.author_user_id) if r.author_user_id else None,
                created_at=r.created_at,
            )
            for r in detail.reverses
        ],
    )
```

Nota sobre `ticket_out`: o dict-comprehension sobre `model_fields` exige que todos os campos de `TicketOut` (exceto `sla`) existam na entidade `Ticket` com o mesmo nome — é o caso. Se o mypy reclamar do unpacking, trocar por construção explícita campo a campo.

- [ ] **Step 4: Implementar deps e o router**

Em `backend/src/sac/interface/deps.py`:

```python
from sac.infrastructure.repositories_tickets import TicketRepos, build_ticket_repos


def get_ticket_repos(session: AsyncSession = Depends(get_tenant_session)) -> TicketRepos:
    return build_ticket_repos(session)
```

E a `require_any_permission` mostrada no cabeçalho da task.

Criar `backend/src/sac/interface/routers/tickets.py` (parte 1):

```python
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from sac.application.ports_tickets import TicketActor, TicketFilters
from sac.application.ports import TokenPayload
from sac.application.use_cases.customers import CustomerInput
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
from sac.application.use_cases.tickets_queries import (
    GetTicketDetailUseCase,
    ListTicketsUseCase,
    MarkTicketUnreadUseCase,
)
from sac.domain.permissions import Permission
from sac.domain.tickets import TicketPriority, TicketStatus
from sac.infrastructure.repositories_tickets import TicketRepos
from sac.interface.deps import (
    get_ticket_repos,
    require_any_permission,
    require_permission,
)
from sac.interface.schemas import (
    TicketDetailOut,
    TicketIn,
    TicketItemIn,
    TicketItemOut,
    TicketListItemOut,
    TicketOut,
    TicketUpdateIn,
    TicketsPageOut,
    ticket_detail_out,
    ticket_item_out,
    ticket_list_item_out,
    ticket_out,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

_read = require_any_permission(
    Permission.VER_TODOS_TICKETS, Permission.VER_PROPRIOS_TICKETS
)
_edit = require_any_permission(
    Permission.EDITAR_QUALQUER_TICKET, Permission.EDITAR_PROPRIO_TICKET
)


def _actor(identity: TokenPayload) -> TicketActor:
    assert identity.role is not None  # garantido pelas dependencies de permissao
    return TicketActor(user_id=identity.user_id, role=identity.role)


def _item_input(body: TicketItemIn) -> TicketItemInput:
    return TicketItemInput(
        product_id=body.product_id,
        defect_type_id=body.defect_type_id,
        quantity=body.quantity,
    )


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketIn,
    identity: TokenPayload = Depends(require_permission(Permission.CRIAR_TICKET)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    customer_input = (
        CustomerInput(
            name=body.customer.name,
            document=body.customer.document,
            phone=body.customer.phone,
            email=body.customer.email,
            cep=body.customer.cep,
            street=body.customer.street,
            number=body.customer.number,
            complement=body.customer.complement,
            neighborhood=body.customer.neighborhood,
            city=body.customer.city,
            state=body.customer.state,
        )
        if body.customer is not None
        else None
    )
    data = CreateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer=customer_input,
        customer_id=body.customer_id,
        attendant_user_id=body.attendant_user_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
        items=tuple(_item_input(i) for i in body.items),
    )
    use_case = CreateTicketUseCase(
        repos.tickets, repos.items, repos.customers, repos.sla, repos.timeline, repos.reads
    )
    return ticket_out(await use_case.execute(_actor(identity), data))


@router.get("", response_model=TicketsPageOut)
async def list_tickets(
    status: TicketStatus | None = None,
    brand_id: UUID | None = None,
    customer: str | None = None,
    customer_id: UUID | None = None,
    product_id: UUID | None = None,
    order_code: str | None = None,
    priority: TicketPriority | None = None,
    overdue: bool = False,
    page: int = 1,
    per_page: int = 20,
    sort: str = "last_activity_at",
    order: str = "desc",
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketsPageOut:
    filters = TicketFilters(
        status=status,
        brand_id=brand_id,
        customer=customer,
        customer_id=customer_id,
        product_id=product_id,
        order_code=order_code,
        priority=priority,
        overdue=overdue,
    )
    rows, total = await ListTicketsUseCase(repos.tickets, repos.users).execute(
        _actor(identity), filters, page, per_page, sort, order
    )
    return TicketsPageOut(
        items=[ticket_list_item_out(r) for r in rows],
        total=total,
        page=max(page, 1),
        per_page=min(max(per_page, 1), 100),
    )


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket_detail(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketDetailOut:
    use_case = GetTicketDetailUseCase(
        repos.tickets,
        repos.items,
        repos.comments,
        repos.timeline,
        repos.reverses,
        repos.reads,
        repos.customers,
        repos.users,
    )
    return ticket_detail_out(await use_case.execute(_actor(identity), ticket_id))


@router.put("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    body: TicketUpdateIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    data = UpdateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer_id=body.customer_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
    )
    use_case = UpdateTicketUseCase(repos.tickets, repos.customers, repos.sla, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, data))


@router.post("/{ticket_id}/itens", response_model=TicketItemOut, status_code=201)
async def add_ticket_item(
    ticket_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await AddTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, _item_input(body)
    )
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.put("/{ticket_id}/itens/{item_id}", response_model=TicketItemOut)
async def update_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await UpdateTicketItemUseCase(
        repos.tickets, repos.items, repos.timeline
    ).execute(_actor(identity), ticket_id, item_id, _item_input(body))
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.delete("/{ticket_id}/itens/{item_id}", status_code=204)
async def remove_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    await RemoveTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, item_id
    )
    return Response(status_code=204)
```

Em `backend/src/sac/interface/app.py`: importar `tickets` no bloco de routers e acrescentar `app.include_router(tickets.router, prefix="/api")` após os cadastros.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_tickets_api.py -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

```bash
git add backend/src/sac/interface/schemas.py backend/src/sac/interface/deps.py backend/src/sac/interface/routers/tickets.py backend/src/sac/interface/app.py backend/tests/integration/test_tickets_api.py
git commit -m "Adiciona rotas de criacao, lista, detalhe, edicao e itens de tickets"
```

---

### Task 11: Router — transições, reversos, garantia, comentários e não lido

**Files:**
- Modify: `backend/src/sac/interface/routers/tickets.py`
- Modify: `backend/src/sac/interface/schemas.py`
- Test: `backend/tests/integration/test_tickets_workflow_api.py`

**Interfaces:**
- Consumes: use cases das Tasks 5-7, router da Task 10.
- Produces (schemas.py): `ApproveIn(notes: str | None = None)`, `DeclineIn(reason: str = Field(min_length=1))`, `CancelIn(reason: str | None = None)`, `FinalizeIn(solution_type_id: UUID, notes: str | None = None)`, `ReverseIn(code: str = Field(min_length=1, max_length=60))`, `WarrantyIn(order_code: str = Field(min_length=1, max_length=60), tracking_code: str | None = Field(default=None, max_length=60))`, `CommentIn(body: str = Field(min_length=1), reply_to_id: UUID | None = None)`.
- Produces (rotas, todas `POST` exceto garantia, retornando `TicketOut` salvo indicação):
  - `POST /{id}/enviar-analise` — `require_permission(ENVIAR_PARA_ANALISE)`
  - `POST /{id}/aprovar`, `/{id}/declinar`, `/{id}/cancelar`, `/{id}/reabrir` — `require_permission(DECIDIR_TICKET)`
  - `POST /{id}/aguardar-cliente`, `/{id}/retomar` — `_edit`
  - `POST /{id}/produto-recebido`, `POST /{id}/reversos` (201, `ReverseCodeOut`), `DELETE /{id}/reversos/{reverso_id}` (204), `PUT /{id}/garantia` — `require_any_permission(OPERAR_LOGISTICA_TODOS, OPERAR_LOGISTICA_PROPRIOS)` (nomear `_operate`)
  - `POST /{id}/finalizar` — `_operate`
  - `POST /{id}/comentarios` (201, `TicketCommentOut`) — `require_permission(COMENTAR_ANEXAR)`
  - `POST /{id}/nao-lido` (204) — `_read`

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/integration/test_tickets_workflow_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)

VALID_CPF = "39053344705"


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, admin, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def _ticket_completo(client: AsyncClient, headers: dict[str, str]) -> str:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    defeitos = (await client.get("/api/cadastros/defeitos", headers=headers)).json()
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "Produto W", "sku": f"SKU-{len(defeitos)}-W"},
            headers=headers,
        )
    ).json()
    res = await client.post(
        "/api/tickets",
        json={
            "brand_id": marcas[0]["id"],
            "priority": "media",
            "customer": {"name": "Cliente W", "document": VALID_CPF},
            "description": "produto com defeito",
            "items": [
                {"product_id": produto["id"], "defect_type_id": defeitos[0]["id"]}
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def _solution_id(client: AsyncClient, headers: dict[str, str]) -> str:
    res = await client.get("/api/cadastros/solucoes", headers=headers)
    return str(res.json()[0]["id"])


async def test_fluxo_completo_com_reverso(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf1")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "aguardando_analise"

    res = await client.post(
        f"/api/tickets/{ticket_id}/aprovar", json={"notes": "aprovado ok"}, headers=headers
    )
    assert res.json()["status"] == "aprovado"

    res = await client.post(
        f"/api/tickets/{ticket_id}/reversos", json={"code": "BR123BR"}, headers=headers
    )
    assert res.status_code == 201
    reverso_id = res.json()["id"]
    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    assert detail["ticket"]["status"] == "aguardando_envio_reverso"

    res = await client.post(f"/api/tickets/{ticket_id}/produto-recebido", headers=headers)
    assert res.json()["status"] == "produto_recebido"

    solution = await _solution_id(client, headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/finalizar",
        json={"solution_type_id": solution, "notes": "trocado"},
        headers=headers,
    )
    assert res.json()["status"] == "finalizado"
    assert res.json()["closed_at"] is not None

    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    types = [e["type"] for e in detail["timeline"]]
    # enviar-analise, aprovar, aprovado->aguardando_envio_reverso (via reverso),
    # produto-recebido e finalizar
    assert types.count("transicao") == 5
    assert "reverso_registrado" in types
    assert detail["reverses"][0]["id"] == reverso_id


async def test_declinar_exige_motivo_e_transicao_invalida_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf2")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(
        f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers
    )
    assert res.status_code == 409
    assert res.json()["code"] == "transicao_invalida"

    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/declinar", json={"reason": ""}, headers=headers
    )
    assert res.status_code == 422

    res = await client.post(
        f"/api/tickets/{ticket_id}/declinar",
        json={"reason": "sem cobertura"},
        headers=headers,
    )
    assert res.json()["status"] == "declinado"

    res = await client.post(f"/api/tickets/{ticket_id}/reabrir", headers=headers)
    assert res.json()["status"] == "aberto"


async def test_excluir_ultimo_reverso_volta_para_aprovado(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf3")
    ticket_id = await _ticket_completo(client, headers)
    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    await client.post(f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers)
    reverso = (
        await client.post(
            f"/api/tickets/{ticket_id}/reversos", json={"code": "BR1"}, headers=headers
        )
    ).json()
    res = await client.delete(
        f"/api/tickets/{ticket_id}/reversos/{reverso['id']}", headers=headers
    )
    assert res.status_code == 204
    detail = (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()
    assert detail["ticket"]["status"] == "aprovado"


async def test_enviar_analise_incompleto_422_com_faltantes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf4")
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    parcial = (
        await client.post(
            "/api/tickets",
            json={"brand_id": marcas[0]["id"], "priority": "media"},
            headers=headers,
        )
    ).json()
    res = await client.post(f"/api/tickets/{parcial['id']}/enviar-analise", headers=headers)
    assert res.status_code == 422
    assert set(res.json()["details"]["faltando"]) == {"cliente", "itens", "descricao"}


async def test_garantia_e_aguardar_cliente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "twf5")
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(f"/api/tickets/{ticket_id}/aguardar-cliente", headers=headers)
    assert res.json()["status"] == "aguardando_cliente"
    res = await client.post(f"/api/tickets/{ticket_id}/retomar", headers=headers)
    assert res.json()["status"] == "aberto"

    await client.post(f"/api/tickets/{ticket_id}/enviar-analise", headers=headers)
    await client.post(f"/api/tickets/{ticket_id}/aprovar", json={}, headers=headers)
    res = await client.put(
        f"/api/tickets/{ticket_id}/garantia",
        json={"order_code": "TINY-9", "tracking_code": "RA99"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "aprovado"
    assert res.json()["warranty_order_code"] == "TINY-9"


async def test_comentarios_e_nao_lido(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, admin, headers = await _setup(session, engine, "twf6")
    supervisor = await seed_user(session, email="sup@twf6.com", name="Sup")
    await seed_link(session, user=supervisor, tenant=tenant, role=Role.SUPERVISOR)
    sup_headers = token_for(supervisor, tenant_slug=tenant.slug, role=Role.SUPERVISOR)
    ticket_id = await _ticket_completo(client, headers)

    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios", json={"body": "primeira"}, headers=headers
    )
    assert res.status_code == 201
    first_id = res.json()["id"]
    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios",
        json={"body": "resposta", "reply_to_id": first_id},
        headers=sup_headers,
    )
    assert res.json()["reply_to_id"] == first_id

    # comentario do supervisor tornou o ticket nao lido para o admin
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is True
    # abrir o detalhe marca como lido
    await client.get(f"/api/tickets/{ticket_id}", headers=headers)
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is False
    # marcar como nao lido de novo
    res = await client.post(f"/api/tickets/{ticket_id}/nao-lido", headers=headers)
    assert res.status_code == 204
    lista = (await client.get("/api/tickets", headers=headers)).json()
    assert lista["items"][0]["unread"] is True

    # encerrar e tentar comentar -> 409
    await client.post(f"/api/tickets/{ticket_id}/cancelar", json={}, headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/comentarios", json={"body": "tarde"}, headers=headers
    )
    assert res.status_code == 409
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_tickets_workflow_api.py -v`
Esperado: FAIL (rotas inexistentes).

- [ ] **Step 3: Implementar schemas dos payloads**

Acrescentar em `backend/src/sac/interface/schemas.py`:

```python
class ApproveIn(BaseModel):
    notes: str | None = None


class DeclineIn(BaseModel):
    reason: str = Field(min_length=1)


class CancelIn(BaseModel):
    reason: str | None = None


class FinalizeIn(BaseModel):
    solution_type_id: UUID
    notes: str | None = None


class ReverseIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)


class WarrantyIn(BaseModel):
    order_code: str = Field(min_length=1, max_length=60)
    tracking_code: str | None = Field(default=None, max_length=60)


class CommentIn(BaseModel):
    body: str = Field(min_length=1)
    reply_to_id: UUID | None = None
```

- [ ] **Step 4: Implementar as rotas**

Acrescentar em `backend/src/sac/interface/routers/tickets.py` (imports dos novos use cases e schemas; `_operate = require_any_permission(Permission.OPERAR_LOGISTICA_TODOS, Permission.OPERAR_LOGISTICA_PROPRIOS)`):

```python
@router.post("/{ticket_id}/enviar-analise", response_model=TicketOut)
async def submit_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(require_permission(Permission.ENVIAR_PARA_ANALISE)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = SubmitTicketUseCase(repos.tickets, repos.items, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/aprovar", response_model=TicketOut)
async def approve_ticket(
    ticket_id: UUID,
    body: ApproveIn,
    identity: TokenPayload = Depends(require_permission(Permission.DECIDIR_TICKET)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ApproveTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, notes=body.notes))


@router.post("/{ticket_id}/declinar", response_model=TicketOut)
async def decline_ticket(
    ticket_id: UUID,
    body: DeclineIn,
    identity: TokenPayload = Depends(require_permission(Permission.DECIDIR_TICKET)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = DeclineTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, reason=body.reason))


@router.post("/{ticket_id}/cancelar", response_model=TicketOut)
async def cancel_ticket(
    ticket_id: UUID,
    body: CancelIn,
    identity: TokenPayload = Depends(require_permission(Permission.DECIDIR_TICKET)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = CancelTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, reason=body.reason))


@router.post("/{ticket_id}/reabrir", response_model=TicketOut)
async def reopen_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(require_permission(Permission.DECIDIR_TICKET)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ReopenTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/aguardar-cliente", response_model=TicketOut)
async def hold_for_customer(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = HoldForCustomerUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/retomar", response_model=TicketOut)
async def resume_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ResumeTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/produto-recebido", response_model=TicketOut)
async def receive_product(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ReceiveProductUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/finalizar", response_model=TicketOut)
async def finalize_ticket(
    ticket_id: UUID,
    body: FinalizeIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = FinalizeTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(
        await use_case.execute(
            _actor(identity), ticket_id, solution_type_id=body.solution_type_id, notes=body.notes
        )
    )


@router.post("/{ticket_id}/reversos", response_model=ReverseCodeOut, status_code=201)
async def register_reverse(
    ticket_id: UUID,
    body: ReverseIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> ReverseCodeOut:
    use_case = RegisterReverseUseCase(repos.tickets, repos.reverses, repos.timeline)
    reverse = await use_case.execute(_actor(identity), ticket_id, code=body.code)
    names = await repos.users.names_by_ids(
        {reverse.author_user_id} if reverse.author_user_id else set()
    )
    return ReverseCodeOut(
        id=reverse.id,
        code=reverse.code,
        author_user_id=reverse.author_user_id,
        author_name=names.get(reverse.author_user_id) if reverse.author_user_id else None,
        created_at=reverse.created_at,
    )


@router.delete("/{ticket_id}/reversos/{reverso_id}", status_code=204)
async def delete_reverse(
    ticket_id: UUID,
    reverso_id: UUID,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    use_case = DeleteReverseUseCase(repos.tickets, repos.reverses, repos.timeline)
    await use_case.execute(_actor(identity), ticket_id, reverso_id)
    return Response(status_code=204)


@router.put("/{ticket_id}/garantia", response_model=TicketOut)
async def set_warranty(
    ticket_id: UUID,
    body: WarrantyIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = SetWarrantyUseCase(repos.tickets, repos.timeline)
    return ticket_out(
        await use_case.execute(
            _actor(identity),
            ticket_id,
            order_code=body.order_code,
            tracking_code=body.tracking_code,
        )
    )


@router.post("/{ticket_id}/comentarios", response_model=TicketCommentOut, status_code=201)
async def add_comment(
    ticket_id: UUID,
    body: CommentIn,
    identity: TokenPayload = Depends(require_permission(Permission.COMENTAR_ANEXAR)),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketCommentOut:
    use_case = AddCommentUseCase(repos.tickets, repos.comments, repos.reads)
    comment = await use_case.execute(
        _actor(identity), ticket_id, body=body.body, reply_to_id=body.reply_to_id
    )
    names = await repos.users.names_by_ids({comment.author_user_id})
    return TicketCommentOut(
        id=comment.id,
        author_user_id=comment.author_user_id,
        author_name=names.get(comment.author_user_id),
        body=comment.body,
        reply_to_id=comment.reply_to_id,
        created_at=comment.created_at,
    )


@router.post("/{ticket_id}/nao-lido", status_code=204)
async def mark_unread(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    use_case = MarkTicketUnreadUseCase(repos.tickets, repos.reads)
    await use_case.execute(_actor(identity), ticket_id)
    return Response(status_code=204)
```

Imports adicionais no topo do router: `from sac.application.use_cases.tickets_workflow import (ApproveTicketUseCase, CancelTicketUseCase, DeclineTicketUseCase, DeleteReverseUseCase, FinalizeTicketUseCase, HoldForCustomerUseCase, ReceiveProductUseCase, RegisterReverseUseCase, ReopenTicketUseCase, ResumeTicketUseCase, SetWarrantyUseCase, SubmitTicketUseCase)` e os novos schemas (`ApproveIn`, `CancelIn`, `CommentIn`, `DeclineIn`, `FinalizeIn`, `ReverseIn`, `TicketCommentOut`, `ReverseCodeOut`, `WarrantyIn`).

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_tickets_workflow_api.py -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

```bash
git add backend/src/sac/interface/routers/tickets.py backend/src/sac/interface/schemas.py backend/tests/integration/test_tickets_workflow_api.py
git commit -m "Adiciona rotas de transicoes, reversos, garantia e comentarios"
```

---

### Task 12: Integração fim a fim — permissões por papel, isolamento e numeração

**Files:**
- Test: `backend/tests/integration/test_tickets_flow.py`

**Interfaces:**
- Consumes: tudo das Tasks 1-11. Task somente de testes (a implementação já existe; qualquer falha aqui é bug a corrigir na hora, com a correção comitada junto).

- [ ] **Step 1: Escrever os testes**

`backend/tests/integration/test_tickets_flow.py`:

```python
import asyncio

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


async def _setup_full(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    users = {}
    for role in (Role.ADMIN, Role.SUPERVISOR, Role.ATENDENTE, Role.VISUALIZADOR):
        user = await seed_user(
            session, email=f"{role.value}@{slug}.com", name=role.value.title()
        )
        await seed_link(session, user=user, tenant=tenant, role=role)
        users[role] = (user, token_for(user, tenant_slug=tenant.slug, role=role))
    return tenant, users


async def _criar_ticket(client: AsyncClient, headers: dict[str, str]) -> dict:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets", json={"brand_id": marcas[0]["id"], "priority": "media"}, headers=headers
    )
    assert res.status_code == 201
    return res.json()


async def test_atendente_so_ve_e_opera_os_seus(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flow1")
    _, admin_headers = users[Role.ADMIN]
    _, atendente_headers = users[Role.ATENDENTE]

    do_admin = await _criar_ticket(client, admin_headers)
    do_atendente = await _criar_ticket(client, atendente_headers)

    lista = (await client.get("/api/tickets", headers=atendente_headers)).json()
    assert lista["total"] == 1
    assert lista["items"][0]["id"] == do_atendente["id"]

    res = await client.get(f"/api/tickets/{do_admin['id']}", headers=atendente_headers)
    assert res.status_code == 404

    res = await client.post(
        f"/api/tickets/{do_admin['id']}/enviar-analise", headers=atendente_headers
    )
    assert res.status_code == 404

    lista_admin = (await client.get("/api/tickets", headers=admin_headers)).json()
    assert lista_admin["total"] == 2


async def test_papeis_decisao_e_logistica(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flow2")
    admin, admin_headers = users[Role.ADMIN]
    _, atendente_headers = users[Role.ATENDENTE]
    _, viewer_headers = users[Role.VISUALIZADOR]

    defeitos = (await client.get("/api/cadastros/defeitos", headers=admin_headers)).json()
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "P Flow", "sku": "SKU-FLOW2"},
            headers=admin_headers,
        )
    ).json()
    marcas = (await client.get("/api/cadastros/marcas", headers=admin_headers)).json()
    ticket = (
        await client.post(
            "/api/tickets",
            json={
                "brand_id": marcas[0]["id"],
                "priority": "alta",
                "customer": {"name": "C Flow", "document": "39053344705"},
                "description": "quebrou a ponta",
                "items": [
                    {"product_id": produto["id"], "defect_type_id": defeitos[0]["id"]}
                ],
            },
            headers=atendente_headers,
        )
    ).json()
    tid = ticket["id"]

    # atendente envia o proprio ticket para analise
    res = await client.post(f"/api/tickets/{tid}/enviar-analise", headers=atendente_headers)
    assert res.status_code == 200

    # atendente NAO decide (403), visualizador NAO decide (403)
    res = await client.post(
        f"/api/tickets/{tid}/aprovar", json={}, headers=atendente_headers
    )
    assert res.status_code == 403
    res = await client.post(f"/api/tickets/{tid}/aprovar", json={}, headers=viewer_headers)
    assert res.status_code == 403

    # admin aprova; atendente opera logistica do proprio ticket
    res = await client.post(f"/api/tickets/{tid}/aprovar", json={}, headers=admin_headers)
    assert res.status_code == 200
    res = await client.post(
        f"/api/tickets/{tid}/reversos", json={"code": "BRX"}, headers=atendente_headers
    )
    assert res.status_code == 201

    # visualizador nao comenta nem opera
    res = await client.post(
        f"/api/tickets/{tid}/comentarios", json={"body": "oi"}, headers=viewer_headers
    )
    assert res.status_code == 403
    res = await client.post(
        f"/api/tickets/{tid}/produto-recebido", headers=viewer_headers
    )
    assert res.status_code == 403

    # visualizador le o detalhe
    res = await client.get(f"/api/tickets/{tid}", headers=viewer_headers)
    assert res.status_code == 200


async def test_isolamento_entre_tenants(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users_a = await _setup_full(session, engine, "flowa")
    _, users_b = await _setup_full(session, engine, "flowb")
    _, headers_a = users_a[Role.ADMIN]
    _, headers_b = users_b[Role.ADMIN]

    ticket_a = await _criar_ticket(client, headers_a)

    lista_b = (await client.get("/api/tickets", headers=headers_b)).json()
    assert lista_b["total"] == 0
    res = await client.get(f"/api/tickets/{ticket_a['id']}", headers=headers_b)
    assert res.status_code == 404

    ticket_b = await _criar_ticket(client, headers_b)
    assert ticket_b["number"] == 1  # sequence propria por tenant


async def test_numeracao_concorrente_unica_e_crescente(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flowseq")
    _, headers = users[Role.ADMIN]
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()

    async def criar() -> int:
        res = await client.post(
            "/api/tickets",
            json={"brand_id": marcas[0]["id"], "priority": "media"},
            headers=headers,
        )
        assert res.status_code == 201
        return int(res.json()["number"])

    numbers = await asyncio.gather(*(criar() for _ in range(5)))
    assert len(set(numbers)) == 5
    assert sorted(numbers) == list(range(1, 6))


async def test_historico_do_cliente_via_customer_id(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, users = await _setup_full(session, engine, "flowcli")
    _, headers = users[Role.ADMIN]
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    primeiro = (
        await client.post(
            "/api/tickets",
            json={
                "brand_id": marcas[0]["id"],
                "priority": "media",
                "customer": {"name": "Historico", "document": "39053344705"},
            },
            headers=headers,
        )
    ).json()
    await _criar_ticket(client, headers)
    res = await client.get(
        "/api/tickets", params={"customer_id": primeiro["customer_id"]}, headers=headers
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == primeiro["id"]
```

- [ ] **Step 2: Rodar**

Run: `uv run pytest tests/integration/test_tickets_flow.py -v`
Esperado: PASS. Se algo falhar, corrigir a implementação (bug real) e manter o teste.

- [ ] **Step 3: Suite completa e commit**

Run: `uv run pytest` (suite inteira) e as demais verificações.

```bash
git add backend/tests/integration/test_tickets_flow.py
git commit -m "Adiciona testes fim a fim de permissoes, isolamento e numeracao"
```

---

### Task 13: Front — lib de tickets, badges, trilha de status e utilitários

INVOCAR o skill `frontend-design` antes de escrever qualquer UI desta task e das seguintes; seguir `docs/identidade-visual.md`.

**Files:**
- Create: `frontend/src/lib/tickets.ts`
- Create: `frontend/src/lib/useDebounce.ts`
- Create: `frontend/src/components/ui/textarea.tsx`
- Create: `frontend/src/components/tickets/badges.tsx`
- Create: `frontend/src/components/tickets/StatusTrail.tsx`

**Interfaces:**
- Consumes: `api` (`lib/api.ts`), `Page`, `Customer`, `CustomerInput` (`lib/cadastros.ts`), `cn` (`lib/utils.ts`).
- Produces (lib/tickets.ts): tipos `TicketStatus`, `TicketPriority`, `SlaState`, `Ticket`, `TicketListItem`, `TicketDetail`, `TicketItemView`, `TicketComment`, `TimelineEvent`, `ReverseCode`, `TicketItemInput`, `TicketCreateInput`, `TicketUpdateInput`, `ListTicketsParams`; constantes `STATUS_LABELS`, `PRIORITY_LABELS`, `SLA_LABELS`, `MAIN_FLOW`; funções de API (`listTickets`, `getTicket`, `createTicket`, `updateTicket`, `addTicketItem`, `updateTicketItem`, `removeTicketItem`, `submitTicket`, `approveTicket`, `declineTicket`, `cancelTicket`, `holdTicket`, `resumeTicket`, `reopenTicket`, `receiveProduct`, `finalizeTicket`, `registerReverse`, `deleteReverse`, `setWarranty`, `addComment`, `markUnread`); helpers de papel (`canCreateTicket`, `canDecide`, `canOperate`, `canEditTicket`, `canComment`, `isClosed`) e `primaryActionFor(ticket, role, userId)`.
- Produces (useDebounce.ts): `useDebounce<T>(value: T, delay?: number): T`.
- Produces (badges.tsx): `StatusBadge({status})`, `PriorityBadge({priority})`, `SlaBadge({sla, dueAt})`.
- Produces (StatusTrail.tsx): `StatusTrail({status, sla})` — barra segmentada da identidade visual.

- [ ] **Step 1: Invocar o skill frontend-design e escrever lib/tickets.ts**

`frontend/src/lib/tickets.ts`:

```ts
import { api } from "@/lib/api"
import type { Customer, CustomerInput, Page } from "@/lib/cadastros"

export type TicketStatus =
  | "aberto"
  | "aguardando_cliente"
  | "aguardando_analise"
  | "aprovado"
  | "aguardando_envio_reverso"
  | "produto_recebido"
  | "finalizado"
  | "declinado"
  | "cancelado"

export type TicketPriority = "baixa" | "media" | "alta" | "urgente"
export type SlaState = "no_prazo" | "vence_em_breve" | "atrasado" | "encerrado"

export const STATUS_LABELS: Record<TicketStatus, string> = {
  aberto: "Aberto",
  aguardando_cliente: "Aguardando cliente",
  aguardando_analise: "Aguardando analise",
  aprovado: "Aprovado",
  aguardando_envio_reverso: "Aguardando envio reverso",
  produto_recebido: "Produto recebido",
  finalizado: "Finalizado",
  declinado: "Declinado",
  cancelado: "Cancelado",
}

export const PRIORITY_LABELS: Record<TicketPriority, string> = {
  baixa: "Baixa",
  media: "Media",
  alta: "Alta",
  urgente: "Urgente",
}

export const SLA_LABELS: Record<SlaState, string> = {
  no_prazo: "No prazo",
  vence_em_breve: "Vence em breve",
  atrasado: "Atrasado",
  encerrado: "Encerrado",
}

export const MAIN_FLOW: TicketStatus[] = [
  "aberto",
  "aguardando_analise",
  "aprovado",
  "aguardando_envio_reverso",
  "produto_recebido",
  "finalizado",
]

const CLOSED: TicketStatus[] = ["finalizado", "declinado", "cancelado"]

export const isClosed = (status: TicketStatus) => CLOSED.includes(status)

export type Ticket = {
  id: string
  number: number
  status: TicketStatus
  priority: TicketPriority
  sla: SlaState
  brand_id: string
  customer_id: string | null
  attendant_user_id: string
  supervisor_user_id: string | null
  purchase_channel_id: string | null
  order_code: string | null
  purchase_date: string | null
  delivery_date: string | null
  description: string | null
  decision_notes: string | null
  final_notes: string | null
  solution_type_id: string | null
  warranty_order_code: string | null
  warranty_tracking_code: string | null
  opened_at: string
  submitted_at: string | null
  approved_at: string | null
  declined_at: string | null
  closed_at: string | null
  last_activity_at: string
  due_at: string
}

export type TicketListItem = {
  id: string
  number: number
  status: TicketStatus
  priority: TicketPriority
  sla: SlaState
  due_at: string
  customer_name: string | null
  first_product_name: string | null
  items_count: number
  attendant_name: string | null
  opened_at: string
  last_activity_at: string
  unread: boolean
}

export type TicketItemView = {
  id: string
  product_id: string
  product_name: string
  defect_type_id: string
  defect_type_name: string
  quantity: number
}

export type TicketComment = {
  id: string
  author_user_id: string
  author_name: string | null
  body: string
  reply_to_id: string | null
  created_at: string | null
}

export type TimelineEvent = {
  id: string
  type: string
  title: string
  old_value: string | null
  new_value: string | null
  author_user_id: string | null
  author_name: string | null
  created_at: string | null
}

export type ReverseCode = {
  id: string
  code: string
  author_user_id: string | null
  author_name: string | null
  created_at: string | null
}

export type TicketDetail = {
  ticket: Ticket
  customer: Customer | null
  attendant_name: string | null
  supervisor_name: string | null
  items: TicketItemView[]
  comments: TicketComment[]
  timeline: TimelineEvent[]
  reverses: ReverseCode[]
}

export type TicketItemInput = {
  product_id: string
  defect_type_id: string
  quantity: number
}

export type TicketCreateInput = {
  brand_id: string
  priority: TicketPriority
  customer?: CustomerInput | null
  customer_id?: string | null
  supervisor_user_id?: string | null
  purchase_channel_id?: string | null
  order_code?: string | null
  purchase_date?: string | null
  delivery_date?: string | null
  description?: string | null
  items?: TicketItemInput[]
}

export type TicketUpdateInput = Omit<TicketCreateInput, "customer" | "items">

export type ListTicketsParams = {
  status?: TicketStatus
  brandId?: string
  customer?: string
  customerId?: string
  productId?: string
  orderCode?: string
  priority?: TicketPriority
  overdue?: boolean
  page?: number
  perPage?: number
  sort?: string
  order?: "asc" | "desc"
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}

export const listTickets = (params: ListTicketsParams = {}) =>
  api<Page<TicketListItem>>(
    `/tickets${query({
      status: params.status,
      brand_id: params.brandId,
      customer: params.customer,
      customer_id: params.customerId,
      product_id: params.productId,
      order_code: params.orderCode,
      priority: params.priority,
      overdue: params.overdue,
      page: params.page,
      per_page: params.perPage,
      sort: params.sort,
      order: params.order,
    })}`,
  )

export const getTicket = (id: string) => api<TicketDetail>(`/tickets/${id}`)

export const createTicket = (input: TicketCreateInput) =>
  api<Ticket>("/tickets", { method: "POST", body: input })

export const updateTicket = (id: string, input: TicketUpdateInput) =>
  api<Ticket>(`/tickets/${id}`, { method: "PUT", body: input })

export const addTicketItem = (ticketId: string, input: TicketItemInput) =>
  api<TicketItemView>(`/tickets/${ticketId}/itens`, { method: "POST", body: input })

export const updateTicketItem = (ticketId: string, itemId: string, input: TicketItemInput) =>
  api<TicketItemView>(`/tickets/${ticketId}/itens/${itemId}`, { method: "PUT", body: input })

export const removeTicketItem = (ticketId: string, itemId: string) =>
  api<void>(`/tickets/${ticketId}/itens/${itemId}`, { method: "DELETE" })

export const submitTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/enviar-analise`, { method: "POST" })

export const approveTicket = (id: string, notes?: string) =>
  api<Ticket>(`/tickets/${id}/aprovar`, { method: "POST", body: { notes: notes ?? null } })

export const declineTicket = (id: string, reason: string) =>
  api<Ticket>(`/tickets/${id}/declinar`, { method: "POST", body: { reason } })

export const cancelTicket = (id: string, reason?: string) =>
  api<Ticket>(`/tickets/${id}/cancelar`, { method: "POST", body: { reason: reason ?? null } })

export const holdTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/aguardar-cliente`, { method: "POST" })

export const resumeTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/retomar`, { method: "POST" })

export const reopenTicket = (id: string) =>
  api<Ticket>(`/tickets/${id}/reabrir`, { method: "POST" })

export const receiveProduct = (id: string) =>
  api<Ticket>(`/tickets/${id}/produto-recebido`, { method: "POST" })

export const finalizeTicket = (id: string, solutionTypeId: string, notes?: string) =>
  api<Ticket>(`/tickets/${id}/finalizar`, {
    method: "POST",
    body: { solution_type_id: solutionTypeId, notes: notes ?? null },
  })

export const registerReverse = (id: string, code: string) =>
  api<ReverseCode>(`/tickets/${id}/reversos`, { method: "POST", body: { code } })

export const deleteReverse = (id: string, reverseId: string) =>
  api<void>(`/tickets/${id}/reversos/${reverseId}`, { method: "DELETE" })

export const setWarranty = (id: string, orderCode: string, trackingCode?: string) =>
  api<Ticket>(`/tickets/${id}/garantia`, {
    method: "PUT",
    body: { order_code: orderCode, tracking_code: trackingCode ?? null },
  })

export const addComment = (id: string, body: string, replyToId?: string) =>
  api<TicketComment>(`/tickets/${id}/comentarios`, {
    method: "POST",
    body: { body, reply_to_id: replyToId ?? null },
  })

export const markUnread = (id: string) =>
  api<void>(`/tickets/${id}/nao-lido`, { method: "POST" })

export const canCreateTicket = (role: string | null) =>
  role !== null && role !== "visualizador"

export const canDecide = (role: string | null) => role === "admin" || role === "supervisor"

export const canOperate = (role: string | null, isOwner: boolean) =>
  role === "admin" || role === "supervisor" || (role === "atendente" && isOwner)

export const canEditTicket = (
  role: string | null,
  isOwner: boolean,
  status: TicketStatus,
) => {
  if (status !== "aberto" && status !== "aguardando_cliente") return false
  if (role === "admin" || role === "supervisor") return true
  return role === "atendente" && isOwner
}

export const canComment = (role: string | null) =>
  role !== null && role !== "visualizador"

export type TicketAction =
  | "enviar_analise"
  | "aprovar"
  | "declinar"
  | "cancelar"
  | "aguardar_cliente"
  | "retomar"
  | "registrar_reverso"
  | "produto_recebido"
  | "finalizar"
  | "reabrir"

export type PrimaryAction = { action: TicketAction; label: string } | null

export function primaryActionFor(
  ticket: Pick<Ticket, "status" | "attendant_user_id">,
  role: string | null,
  userId: string | undefined,
): PrimaryAction {
  const owner = ticket.attendant_user_id === userId
  switch (ticket.status) {
    case "aberto":
      return canEditTicket(role, owner, ticket.status) || canOperate(role, owner)
        ? { action: "enviar_analise", label: "Enviar para analise" }
        : null
    case "aguardando_cliente":
      return canEditTicket(role, owner, ticket.status)
        ? { action: "retomar", label: "Retomar atendimento" }
        : null
    case "aguardando_analise":
      return canDecide(role) ? { action: "aprovar", label: "Aprovar" } : null
    case "aprovado":
      return canOperate(role, owner)
        ? { action: "registrar_reverso", label: "Registrar reverso" }
        : null
    case "aguardando_envio_reverso":
      return canOperate(role, owner)
        ? { action: "produto_recebido", label: "Produto recebido" }
        : null
    case "produto_recebido":
      return canOperate(role, owner) ? { action: "finalizar", label: "Finalizar" } : null
    case "finalizado":
    case "declinado":
    case "cancelado":
      return canDecide(role) ? { action: "reabrir", label: "Reabrir" } : null
  }
}
```

- [ ] **Step 2: Escrever useDebounce e textarea**

`frontend/src/lib/useDebounce.ts`:

```ts
import { useEffect, useState } from "react"

export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
```

`frontend/src/components/ui/textarea.tsx` (shadcn padrão, ajustado aos tokens do projeto):

```tsx
import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-ring",
        "flex min-h-16 w-full rounded-md border bg-transparent px-3 py-2 text-sm",
        "focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
```

- [ ] **Step 3: Escrever badges e trilha de status**

`frontend/src/components/tickets/badges.tsx` (cores semânticas mapeadas na paleta da identidade — neutros Silver, alerta em Paprika apenas para SLA crítico/urgente):

```tsx
import { cn } from "@/lib/utils"
import {
  PRIORITY_LABELS,
  SLA_LABELS,
  STATUS_LABELS,
  type SlaState,
  type TicketPriority,
  type TicketStatus,
} from "@/lib/tickets"

export const STATUS_ACCENTS: Record<TicketStatus, string> = {
  aberto: "border-l-sky-600",
  aguardando_cliente: "border-l-amber-500",
  aguardando_analise: "border-l-violet-500",
  aprovado: "border-l-emerald-600",
  aguardando_envio_reverso: "border-l-indigo-500",
  produto_recebido: "border-l-teal-600",
  finalizado: "border-l-emerald-700",
  declinado: "border-l-rose-600",
  cancelado: "border-l-zinc-400",
}

const STATUS_BADGE: Record<TicketStatus, string> = {
  aberto: "bg-sky-50 text-sky-800 ring-sky-200",
  aguardando_cliente: "bg-amber-50 text-amber-800 ring-amber-200",
  aguardando_analise: "bg-violet-50 text-violet-800 ring-violet-200",
  aprovado: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  aguardando_envio_reverso: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  produto_recebido: "bg-teal-50 text-teal-800 ring-teal-200",
  finalizado: "bg-emerald-50 text-emerald-900 ring-emerald-200",
  declinado: "bg-rose-50 text-rose-800 ring-rose-200",
  cancelado: "bg-zinc-100 text-zinc-600 ring-zinc-200",
}

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        STATUS_BADGE[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

const PRIORITY_DOTS: Record<TicketPriority, string> = {
  baixa: "bg-zinc-400",
  media: "bg-sky-500",
  alta: "bg-amber-500",
  urgente: "bg-[#eb5e28]",
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cn("size-2 rounded-full", PRIORITY_DOTS[priority])} />
      {PRIORITY_LABELS[priority]}
    </span>
  )
}

function relativeDue(dueAt: string): string {
  const diffMs = new Date(dueAt).getTime() - Date.now()
  const hours = Math.round(Math.abs(diffMs) / 3_600_000)
  const spec = hours >= 48 ? `${Math.round(hours / 24)}d` : `${hours}h`
  return diffMs >= 0 ? `em ${spec}` : `ha ${spec}`
}

const SLA_STYLES: Record<SlaState, string> = {
  no_prazo: "text-emerald-700",
  vence_em_breve: "text-[#eb5e28] font-medium",
  atrasado: "text-[#eb5e28] font-semibold",
  encerrado: "text-zinc-500",
}

export function SlaBadge({ sla, dueAt }: { sla: SlaState; dueAt: string }) {
  return (
    <span className={cn("text-xs", SLA_STYLES[sla])}>
      {SLA_LABELS[sla]}
      {sla !== "encerrado" ? ` (${relativeDue(dueAt)})` : ""}
    </span>
  )
}
```

`frontend/src/components/tickets/StatusTrail.tsx` — o elemento-assinatura da identidade: barra segmentada, preenchida em Charcoal Brown até o estado atual, segmento ativo pulsando em Paprika só com SLA apertado; nos estados fora do fluxo principal (aguardando_cliente, declinado, cancelado) mostra o rótulo do desvio:

```tsx
import { cn } from "@/lib/utils"
import {
  MAIN_FLOW,
  STATUS_LABELS,
  type SlaState,
  type TicketStatus,
} from "@/lib/tickets"

export function StatusTrail({ status, sla }: { status: TicketStatus; sla: SlaState }) {
  const lateral = !MAIN_FLOW.includes(status)
  const effective: TicketStatus = lateral
    ? status === "aguardando_cliente"
      ? "aberto"
      : "aguardando_analise"
    : status
  const currentIndex = MAIN_FLOW.indexOf(effective)
  const atRisk = sla === "vence_em_breve" || sla === "atrasado"
  return (
    <div>
      <div className="flex gap-1" role="img" aria-label={`Status: ${STATUS_LABELS[status]}`}>
        {MAIN_FLOW.map((step, index) => (
          <div
            key={step}
            className={cn(
              "h-1.5 flex-1 rounded-sm bg-[#ccc5b9]/40",
              index < currentIndex && "bg-[#403d39]",
              index === currentIndex &&
                (atRisk && !lateral ? "animate-pulse bg-[#eb5e28]" : "bg-[#403d39]"),
            )}
          />
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-[#403d39]/70">
        <span>{STATUS_LABELS[status]}</span>
        {lateral && status !== "aguardando_cliente" ? (
          <span className="font-medium text-rose-700">{STATUS_LABELS[status]}</span>
        ) : null}
      </div>
    </div>
  )
}
```

Nota: usar os tokens de cor do tema (`index.css`) quando existirem em vez de hex hardcoded — conferir como as cores da identidade foram registradas na Fase 1 (procurar por `eb5e28`/`--primary` em `frontend/src/index.css`) e usar as classes/tokens equivalentes.

- [ ] **Step 4: Verificar e commitar**

Run (em `frontend/`): `pnpm lint && pnpm build`
Esperado: sucesso (componentes ainda não usados — se o eslint reclamar de exports não usados, está ok pois são módulos exportados; nenhuma tela usa ainda).

```bash
git add frontend/src/lib/tickets.ts frontend/src/lib/useDebounce.ts frontend/src/components/ui/textarea.tsx frontend/src/components/tickets/badges.tsx frontend/src/components/tickets/StatusTrail.tsx
git commit -m "Adiciona lib de tickets, badges e trilha de status no front"
```

---

### Task 14: Front — lista de tickets

INVOCAR o skill `frontend-design`; seguir `docs/identidade-visual.md` (tabela densa, número em mono, borda esquerda 3px na cor do status, indicador de não lido discreto, Paprika apenas no CTA "Novo ticket").

**Files:**
- Create: `frontend/src/pages/tickets/TicketsListPage.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (grupo "Operacao" com item Tickets acima de Cadastros)
- Modify: `frontend/src/main.tsx` (rota `/tickets`)

**Interfaces:**
- Consumes: `listTickets`, tipos e labels (Task 13), `useDebounce`, badges, `useAuth` (`lib/auth.tsx` expõe `session` com `role` e `user.id` — conferir shape em `lib/api.ts:Session`), componentes ui existentes (`Card`, `Table`, `Input`, `Select`, `Button`, `Checkbox`), `listCatalog` (marcas para o filtro).
- Produces: rota `/tickets` funcional; linhas são `<Link>` reais para `/tickets/:id`.

- [ ] **Step 1: Implementar a página**

`frontend/src/pages/tickets/TicketsListPage.tsx` — estrutura obrigatória (o implementador segue o padrão visual de `ClientesPage.tsx` e a identidade):

```tsx
import { useQuery } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"

import { PriorityBadge, SlaBadge, StatusBadge, STATUS_ACCENTS } from "@/components/tickets/badges"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/lib/auth"
import { listCatalog } from "@/lib/cadastros"
import {
  canCreateTicket,
  listTickets,
  PRIORITY_LABELS,
  STATUS_LABELS,
  type TicketPriority,
  type TicketStatus,
} from "@/lib/tickets"
import { useDebounce } from "@/lib/useDebounce"
import { cn } from "@/lib/utils"

const PER_PAGE = 20

export default function TicketsListPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<TicketStatus | "">(
    (searchParams.get("status") as TicketStatus) ?? "",
  )
  const [brandId, setBrandId] = useState("")
  const [customer, setCustomer] = useState(searchParams.get("customer") ?? "")
  const [orderCode, setOrderCode] = useState("")
  const [priority, setPriority] = useState<TicketPriority | "">("")
  const [overdue, setOverdue] = useState(searchParams.get("overdue") === "1")
  const [page, setPage] = useState(1)
  const customerId = searchParams.get("customer_id") ?? undefined

  const debouncedCustomer = useDebounce(customer)
  const debouncedOrder = useDebounce(orderCode)

  const { data: brands } = useQuery({
    queryKey: ["marcas"],
    queryFn: () => listCatalog("marcas"),
  })
  const { data, isLoading } = useQuery({
    queryKey: [
      "tickets",
      { status, brandId, debouncedCustomer, debouncedOrder, priority, overdue, page, customerId },
    ],
    queryFn: () =>
      listTickets({
        status: status || undefined,
        brandId: brandId || undefined,
        customer: debouncedCustomer || undefined,
        orderCode: debouncedOrder || undefined,
        priority: priority || undefined,
        overdue: overdue || undefined,
        customerId,
        page,
        perPage: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1

  return (
    <div className="space-y-6">
      {/* Card de filtros: status, marca, cliente (nome/documento), pedido,
          prioridade, checkbox "somente atrasados"; botao Limpar reseta estado.
          Inputs de texto ja tem debounce via useDebounce. */}
      {/* Card da tabela:
          - header com titulo "Tickets" + total e botao "Novo ticket"
            (visivel se canCreateTicket(session?.role ?? null)) -> navigate("/tickets/novo")
          - colunas: Numero (font-mono, prefixo #), Cliente, Produto (first_product_name
            + "+N" quando items_count > 1), Prioridade (PriorityBadge), Status (StatusBadge),
            SLA (SlaBadge), Atendente, Abertura (data local)
          - cada linha: borda esquerda 3px STATUS_ACCENTS[status]; nao lida = fundo
            levemente destacado + dot; primeira celula envolve <Link to={`/tickets/${id}`}>
            cobrindo a linha via CSS (linha inteira clicavel com link real)
          - empty state de texto direto: "Nenhum ticket para este filtro."
          - paginacao identica a ClientesPage (Anterior / Proxima + "pagina X de Y") */}
    </div>
  )
}
```

O esqueleto acima fixa contratos (estado, queries, params, colunas); o corpo JSX dos dois cards segue EXATAMENTE o padrão visual já existente em `frontend/src/pages/cadastros/ClientesPage.tsx` (Cards, Table, selects com item "Todos", botão Limpar) — replicar aquele JSX adaptando às colunas e badges descritas nos comentários, que são requisitos, não sugestões.

- [ ] **Step 2: Sidebar e rota**

Em `frontend/src/components/layout/Sidebar.tsx`, antes do grupo Cadastros (dentro do `if (session?.tenantSlug)`):

```tsx
    groups.push({
      label: "Operacao",
      items: [{ to: "/tickets", label: "Tickets", icon: Ticket }],
    })
```

(import `Ticket` de lucide-react.)

Em `frontend/src/main.tsx`, dentro do bloco `RequireTenant`, antes das rotas de cadastros:

```tsx
              { path: "/tickets", element: <TicketsListPage /> },
```

(import `TicketsListPage from "@/pages/tickets/TicketsListPage"`.)

- [ ] **Step 3: Verificar manualmente e commitar**

Run: `pnpm lint && pnpm build` (em `frontend/`).
Com o ambiente dev de pé (`./dev.ps1` na raiz), abrir `/tickets`, conferir filtros com debounce, badges e link das linhas. Criar tickets via API se necessário para ver dados.

```bash
git add frontend/src/pages/tickets/TicketsListPage.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/main.tsx
git commit -m "Adiciona pagina de lista de tickets com filtros e indicador de nao lido"
```

---

### Task 15: Front — detalhe do ticket (leitura, chat, timeline)

INVOCAR o skill `frontend-design`; seguir `docs/identidade-visual.md` (2/3 + 1/3; número do ticket em mono e destaque; trilha de status no topo da coluna direita; timeline com conector visual; chat em bolhas com reply citável; placeholder de anexos como card desabilitado).

**Files:**
- Create: `frontend/src/pages/tickets/TicketDetailPage.tsx`
- Modify: `frontend/src/main.tsx` (rota `/tickets/:id`)

**Interfaces:**
- Consumes: `getTicket`, `addComment`, `markUnread`, tipos/labels/badges/StatusTrail (Task 13), `Textarea`, `useAuth`, `formatDocument`/`formatPhone`/`formatCep` (`lib/format.ts`), `toast` (sonner).
- Produces: rota `/tickets/:id`; a coluna direita reserva um slot `<ActionPanel detail={data} onChanged={refetch} />` que a Task 16 implementa — nesta task, renderizar o painel apenas com a StatusTrail, reversos e garantia em leitura.

- [ ] **Step 1: Implementar a página**

`frontend/src/pages/tickets/TicketDetailPage.tsx` — estrutura obrigatória:

```tsx
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
// demais imports: badges, StatusTrail, ui, lib/tickets, lib/format, useAuth, sonner

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => getTicket(id!),
    enabled: Boolean(id),
  })
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["ticket", id] })
    void queryClient.invalidateQueries({ queryKey: ["tickets"] })
  }
  // ... skeleton de loading; data ausente -> "Ticket nao encontrado."
}
```

Layout (grid `lg:grid-cols-3`, coluna esquerda `lg:col-span-2 space-y-6`):

Hero (acima do grid): numero `#<number>` em `font-mono` + `StatusBadge` + `PriorityBadge` + `SlaBadge`; subtitulo com marca e abertura.

Coluna esquerda, cards nesta ordem:
1. **Informacoes gerais** — atendente (`attendant_name`), supervisor (`supervisor_name` ou "—"), prioridade, abertura, prazo SLA (`due_at` formatado), descricao. Notas de decisao (`decision_notes`) e notas finais (`final_notes`) aparecem SOMENTE quando preenchidas.
2. **Cliente** — nome, documento formatado (`formatDocument`, mono), telefone (`formatPhone`), email, cidade/UF; link "Ver historico" -> `/tickets?customer_id=<id>`; sem cliente -> texto "Nenhum cliente vinculado." (sem ilustracao).
3. **Compra** — canal (id resolvido? NAO: o backend nao devolve nome do canal no detalhe; exibir `order_code` (mono), datas de compra/entrega; canal exibido na Task 16 via edicao. Se quiser o nome do canal, buscar `listCatalog("canais")` com useQuery e mapear por id — fazer isso, é barato e completa o card).
4. **Itens** — tabela produto / defeito / quantidade (dados de `items`, ja com nomes); vazio -> "Nenhum item registrado."
5. **Anexos** — card com borda tracejada e texto "Anexos chegam na Fase 2B (armazenamento Wasabi)." SEM botao de upload.
6. **Comentarios internos** — chat: bolhas alinhadas a direita quando `author_user_id === session.user.id`; autor + hora; reply mostra citacao compacta do comentario referenciado (lookup por `reply_to_id` na propria lista); botao "Responder" em cada bolha define o estado `replyTo`; form com `Textarea` + botao enviar (Enter envia, Shift+Enter quebra linha); apos enviar com sucesso, `invalidate()`; se o ticket esta encerrado (`isClosed(status)`), form substituido por "Ticket encerrado — chat somente leitura."

Coluna direita (`space-y-6`):
1. Card **Status** — `<StatusTrail status sla />` + slot do painel de acoes (Task 16).
2. Card **Reversos** — lista `reverses` (codigo mono + autor + data); vazio -> "Nenhum codigo reverso."
3. Card **Garantia** — `warranty_order_code`/`warranty_tracking_code` em mono ou "Nao registrada."
4. Card **Timeline** — lista vertical com conector: cada evento com dot alinhado a uma linha vertical continua (`border-l` na coluna dos dots), titulo, `old_value -> new_value` quando ambos existem (rotulados via STATUS_LABELS quando forem status), autor e data/hora. Ordem cronologica decrescente (mais novo no topo).

- [ ] **Step 2: Rota**

Em `frontend/src/main.tsx`: `{ path: "/tickets/:id", element: <TicketDetailPage /> }` (apos a rota da lista).

- [ ] **Step 3: Verificar manualmente e commitar**

Run: `pnpm lint && pnpm build`. No dev: abrir um ticket, comentar, responder, conferir timeline/trilha/nao-lido (abrir o detalhe zera o indicador na lista).

```bash
git add frontend/src/pages/tickets/TicketDetailPage.tsx frontend/src/main.tsx
git commit -m "Adiciona pagina de detalhe do ticket com chat e timeline"
```

---

### Task 16: Front — painel de ações contextuais do detalhe

INVOCAR o skill `frontend-design`. UMA ação primária contextual por estado (Paprika), demais ações em menu; formulários com input em Dialog (nunca confirm/alert nativos).

**Files:**
- Create: `frontend/src/components/tickets/ActionPanel.tsx`
- Modify: `frontend/src/pages/tickets/TicketDetailPage.tsx` (usar o painel)

**Interfaces:**
- Consumes: `primaryActionFor`, todas as funções de ação da lib (Task 13), `canDecide`/`canOperate`/`canEditTicket`/`isClosed`, `listCatalog` (soluções para finalizar, marcas/canais para editar), `updateTicket`, `markUnread`, ui (`Dialog`, `DropdownMenu`, `Select`, `Textarea`, `Button`), sonner.
- Produces: `ActionPanel({ detail, onChanged }: { detail: TicketDetail; onChanged: () => void })`.

- [ ] **Step 1: Implementar o painel**

`frontend/src/components/tickets/ActionPanel.tsx` — contratos:

```tsx
type DialogKind =
  | "aprovar"
  | "declinar"
  | "cancelar"
  | "finalizar"
  | "reverso"
  | "garantia"
  | "editar"
  | null
```

Comportamento obrigatório:
- Ação primária: `primaryActionFor(ticket, role, userId)`; botão largo, Paprika (variant default do design system já é o quase-preto; usar a classe primária Paprika definida na Fase 1 — conferir o botão primário de `LoginPage`/`ClientesPage`). Ações imediatas (enviar_analise, retomar, produto_recebido, reabrir) executam direto com toast de sucesso/erro e `onChanged()`; ações com formulário (aprovar -> notas opcionais; registrar_reverso -> código; finalizar -> solução obrigatória + notas) abrem o Dialog correspondente.
- Caso especial `aguardando_analise` para quem decide: primária "Aprovar" (dialog com notas opcionais) e botão secundário "Declinar" visível ao lado (motivo obrigatório em dialog). Para quem não decide: texto "Aguardando decisao do supervisor."
- Menu (DropdownMenu, ícone kebab no header do card Status) com ações secundárias condicionais:
  - "Aguardar cliente" (status aberto + canEditTicket)
  - "Finalizar direto" (status aprovado + canOperate)
  - "Registrar garantia" (não encerrado + canOperate) -> dialog order_code obrigatório + tracking opcional
  - "Editar dados" (canEditTicket) -> dialog com marca (select de `listCatalog("marcas")`), canal (select de canais), prioridade, pedido, datas, descrição — submit chama `updateTicket` com os campos atuais + editados (o `TicketUpdateInput` exige `brand_id` e `priority` sempre; preencher com os valores correntes; IMPORTANTE: enviar também `customer_id` e `supervisor_user_id` atuais, senão o PUT os anula)
  - "Cancelar ticket" (não encerrado + canDecide) -> dialog com motivo opcional e aviso de irreversibilidade textual
  - "Marcar como nao lido" (sempre) -> `markUnread` + toast + navegação de volta? NÃO: apenas toast "Marcado como nao lido" e `onChanged()`.
- Excluir reverso: no card Reversos (Task 15), adicionar botão de remover por linha quando `canOperate` e status permite (aguardando_envio_reverso/produto_recebido) — confirmação via Dialog simples, chama `deleteReverse` + `onChanged()`. Implementar movendo o card Reversos para dentro do ActionPanel OU expondo um subcomponente `ReversesCard` neste arquivo e usando-o na página (preferido: `ReversesCard` exportado daqui, importado pela página).
- Todos os dialogs: fechar ao concluir, `onChanged()` para refetch, erros da API via `toast.error(message)` (usar `ApiError.message`).

- [ ] **Step 2: Integrar na página**

Em `TicketDetailPage.tsx`: renderizar `<ActionPanel detail={data} onChanged={invalidate} />` no card Status (coluna direita) e substituir o card Reversos estático pelo `ReversesCard`.

- [ ] **Step 3: Verificar manualmente e commitar**

Run: `pnpm lint && pnpm build`. No dev, percorrer o fluxo inteiro pela UI: criar (via API ou Task 17 depois) -> enviar para análise -> aprovar -> reverso -> recebido -> finalizar; declinar exige motivo; reabrir; cancelar; garantia; marcar não lido. Conferir que visualizador não vê nenhuma ação.

```bash
git add frontend/src/components/tickets/ActionPanel.tsx frontend/src/pages/tickets/TicketDetailPage.tsx
git commit -m "Adiciona painel de acoes contextuais no detalhe do ticket"
```

---

### Task 17: Front — criação de ticket

INVOCAR o skill `frontend-design`. Página única em seções (padrão do legado melhorado): Cliente, Compra, Caso. Lookup de cliente por documento com autofill; CEP com autofill; autocomplete de canal; itens repetíveis.

**Files:**
- Create: `frontend/src/pages/tickets/TicketCreatePage.tsx`
- Modify: `frontend/src/main.tsx` (rota `/tickets/novo` ANTES de `/tickets/:id`)

**Interfaces:**
- Consumes: `createTicket` (Task 13), `listCustomers`, `lookupCep`, `listCatalog`, `listProducts` (`lib/cadastros.ts`), `formatDocument`/`formatCep`/`formatPhone`/`onlyDigits` (`lib/format.ts`), `useDebounce`, ui + `Textarea`, `useAuth`, sonner.
- Produces: rota `/tickets/novo`; submit navega para `/tickets/:id` do criado.

- [ ] **Step 1: Implementar a página**

Estado principal:

```tsx
type ItemRow = { key: string; productId: string; defectTypeId: string; quantity: number }

const [document, setDocument] = useState("")
const [linkedCustomerId, setLinkedCustomerId] = useState<string | null>(null)
const [customerFields, setCustomerFields] = useState({
  name: "", phone: "", email: "", cep: "", street: "", number: "",
  complement: "", neighborhood: "", city: "", state: "",
})
const [brandId, setBrandId] = useState("")
const [priority, setPriority] = useState<TicketPriority>("media")
const [channelId, setChannelId] = useState("")
const [orderCode, setOrderCode] = useState("")
const [purchaseDate, setPurchaseDate] = useState("")
const [deliveryDate, setDeliveryDate] = useState("")
const [description, setDescription] = useState("")
const [items, setItems] = useState<ItemRow[]>([])
```

Comportamentos obrigatórios:
1. **Seção Cliente**: input CPF/CNPJ com máscara (`formatDocument` na exibição, `onlyDigits` no estado). Quando os dígitos atingem 11 ou 14, dispara lookup `listCustomers({ search: digits })`; se um cliente com documento exatamente igual existe: autofill de todos os campos, `setLinkedCustomerId(id)` e banner discreto "Cliente ja cadastrado — dados carregados; alteracoes atualizam o cadastro."; senão `setLinkedCustomerId(null)` e campos liberados para cadastro inline. CEP: ao completar 8 dígitos chama `lookupCep`; sucesso preenche rua/bairro/cidade/UF; erro -> toast informativo e preenchimento manual (padrão da ClientesPage — reutilizar o mesmo tratamento).
2. **Seção Compra**: canal com autocomplete — input de texto com dropdown de sugestões de `listCatalog("canais", { search })` (debounced), navegável por teclado (setas + Enter), seleção grava `channelId`; pedido; datas (inputs `type="date"`).
3. **Seção Caso**: marca (select obrigatório), prioridade (select com indicação do SLA: "Urgente — 24h", "Alta — 48h", "Media — 72h", "Baixa — 120h"), descrição (`Textarea`), itens repetíveis: cada linha tem autocomplete de produto (busca `listProducts({ search })` debounced, mostra nome + SKU), select de defeito (`listCatalog("defeitos")`), quantidade (number min 1), botão remover linha; botão "Adicionar item".
4. **Submit**: monta `TicketCreateInput` — se `linkedCustomerId && camposNaoEditados` enviar `customer_id`; caso contrário, se documento preenchido, enviar `customer` inline (o backend vincula/atualiza/cria por documento — na prática, enviar SEMPRE `customer` inline quando houver documento digitado é mais simples e correto; `customer_id` só quando o usuário não tocou em nada: decisão fixa — enviar `customer` inline sempre que houver documento, nunca `customer_id`); campos vazios viram `null`/omitidos; itens sem produto/defeito são descartados com aviso. Sucesso: toast + `navigate(`/tickets/${ticket.id}`)`. Erros 422/409 da API: `toast.error(message)`.
5. Criação parcial é válida: apenas marca + prioridade preenchidos já permitem salvar (o backend aceita; a completude é cobrada no envio para análise). Deixar isso visível: texto auxiliar "Voce pode salvar parcialmente e completar depois; o envio para analise exige cliente, item e descricao."
6. Botão primário "Criar ticket" (Paprika) + "Cancelar" (volta para `/tickets`).

Rota em `main.tsx`: `{ path: "/tickets/novo", element: <TicketCreatePage /> }` declarada ANTES de `/tickets/:id`.

- [ ] **Step 2: Verificar manualmente e commitar**

Run: `pnpm lint && pnpm build`. No dev: criar ticket completo com cliente novo (documento inexistente), depois outro com o mesmo documento (deve vincular e atualizar), CEP autofill, itens múltiplos, parcial só com marca+prioridade.

```bash
git add frontend/src/pages/tickets/TicketCreatePage.tsx frontend/src/main.tsx
git commit -m "Adiciona pagina de criacao de ticket com lookup de cliente e itens"
```

---

### Task 18: Verificação final e documentação

**Files:**
- Modify: `README.md` (seção da Fase 2A no histórico de fases, seguindo o formato existente)

**Interfaces:**
- Consumes: tudo.

- [ ] **Step 1: Suite completa**

Em `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest` (Postgres de pé).
Em `frontend/`: `pnpm lint`, `pnpm build`.
Esperado: tudo verde. Corrigir qualquer regressão antes de seguir.

- [ ] **Step 2: Smoke manual no dev**

`./dev.ps1`; fluxo completo pela UI com dois usuários (admin e atendente): criar como atendente, enviar para análise, aprovar como admin, reverso, recebido, finalizar; conferir não-lido entre os dois usuários e o escopo do atendente (não vê ticket do admin).

- [ ] **Step 3: Atualizar README e commitar**

Acrescentar ao `README.md` a seção da Fase 2A no mesmo formato das fases anteriores (o que foi entregue: máquina de estados com use case por transição, numeração por sequence, itens, SLA, comentários, timeline, não-lido, reversos, garantia; rotas; telas lista/detalhe/criação; anexos ficam para a 2B).

```bash
git add README.md
git commit -m "Documenta a Fase 2A no README"
```

- [ ] **Step 4: Encerramento**

Invocar o skill `superpowers:finishing-a-development-branch` se o trabalho estiver em branch/worktree; caso contrário, confirmar que `main` está limpa e a suite verde.
