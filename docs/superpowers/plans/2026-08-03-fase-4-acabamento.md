# Fase 4 (Acabamento) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a ultima fase do PRD: notificacoes in-app com SSE, busca global, preferencias de usuario (tema + notificacoes), reatribuicao de atendente e o hardening pendente (membros por tenant, rate limit fino, orfaos no Wasabi, residuais de a11y).

**Architecture:** Notificacoes em tabela por schema de tenant, fan-out chamado pelos use cases existentes na mesma transacao, `pg_notify` transacional e um listener asyncpg unico por instancia alimentando as conexoes SSE; busca global agregando tickets/clientes/produtos com trgm; preferencias no schema public; hardening sem infra nova (sem Redis — decisao fechada no spec).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, asyncpg, PostgreSQL (LISTEN/NOTIFY, pg_trgm), pytest, React + TypeScript + Vite, react-query v5, next-themes, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-03-sac-b2pro-fase-4-acabamento-design.md`

## Global Constraints

- PROIBIDO usar emojis em codigo, comentarios, commits, UI e documentacao.
- Clean Architecture: dominio sem framework; ports (Protocol) na application; SQL/boto3/asyncpg na infrastructure; routers na interface. Dependencias apontam para dentro.
- TDD no backend: escrever o teste, ver falhar, implementar o minimo, ver passar, commitar.
- Antes de CADA commit de backend (em `backend/`): `ruff check .`, `ruff format --check .`, `mypy` (**sem path** — `mypy .` da erro falso em `migrations/tenant/env.py`), `./.venv/Scripts/python.exe -m pytest -q` (venv do projeto, NUNCA o Python global). Integracao exige `docker compose up -d` na raiz — conferir antes que `copilot-postgres` esta parado (briga pela 5432).
- O backend do docker monta o codigo por volume mas NAO recarrega sozinho: apos mudar codigo, `docker compose restart backend worker` antes de testar manualmente ou rodar e2e.
- Antes de CADA commit de frontend (em `frontend/`): `pnpm build` e `pnpm lint`. Gerenciador e **pnpm**.
- Nunca rodar verificacoes ou e2e em background; e2e com `E2E_PORT=5188`.
- Copy da UI em portugues sem acentos; identificadores de codigo em ingles; rotas de API em portugues (`/notificacoes`, `/busca`, `/preferencias`, `/membros`).
- Todo trabalho de UI usa o skill `frontend-design` e segue `docs/identidade-visual.md`.
- Tenant manual de teste: `e2e` / `e2e-admin@b2pro.com` / `senha-e2e-12345`. Performance nunca se mede no tenant e2e (massa de 100k em `docs/medicao-indices-tenant.md`).
- FlowHub: a sessao de execucao cria a task "Fase 4 - Acabamento" no board SAC-B2PRO com uma subtask por task deste plano (Emmanuel assignee), e atualiza status via API a cada task concluida. Key em `flowhub/.flowhub.env`; auth `Authorization: Bearer`; so curl (Cloudflare bloqueia urllib/requests); uma chamada por vez, sempre conferindo a resposta; export de env var na MESMA linha do curl.
- Branch de trabalho: `fase-4-acabamento` a partir da `main`.

## Notas de arquitetura que valem para varias tasks

- `get_tenant_session` (interface/deps.py:192) traduz `schema_translate_map={"tenant": f"t_{slug}"}`; modelos de tenant usam `__table_args__ = {"schema": "tenant"}` (ver `models_tenant.py`). Repositorios de tenant recebem `AsyncSession` no construtor.
- O commit da sessao de request acontece no proprio `get_tenant_session`/`get_session` (yield + commit). Tudo que o use case grava (notificacao inclusive) entra nessa transacao; `pg_notify` executado na mesma sessao e entregue somente no commit — e exatamente o que o design quer.
- Padrao de teste: `backend/tests/unit/` espelha camadas e usa fakes de `tests/unit/fakes*.py`; `backend/tests/integration/` usa Postgres real com `conftest.py`/`helpers.py` existentes (ler antes de escrever). Migrations novas se provam em `tests/integration/test_migrations.py`.
- Migrations: chain public em `backend/migrations/public/versions/` (ultima: `0003_pg_trgm`), chain tenant em `backend/migrations/tenant/versions/` (ultima: `0008_indices_busca`). Aplicar com `./.venv/Scripts/python.exe -m sac.infrastructure.migrate all`. Indices GIN em migration de tenant precisam de opclass qualificada `public.gin_trgm_ops`.

---

### Task 1: Migration, model e repositorio de notificacoes

**Files:**
- Create: `backend/src/sac/domain/notifications.py`
- Create: `backend/src/sac/application/ports_notifications.py`
- Create: `backend/src/sac/infrastructure/repositories_notifications.py`
- Create: `backend/migrations/tenant/versions/0009_notifications.py`
- Modify: `backend/src/sac/infrastructure/models_tenant.py` (adicionar `NotificationModel`)
- Test: `backend/tests/integration/test_repositories_notifications.py`, `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Consumes: padroes de `models_tenant.py` (`{"schema": "tenant"}`), sessao de tenant dos testes de integracao existentes.
- Produces:

```python
# domain/notifications.py
class NotificationType(StrEnum):
    ATRIBUICAO = "atribuicao"
    TRANSICAO = "transicao"
    COMENTARIO = "comentario"

@dataclass
class Notification:
    id: UUID
    user_id: UUID
    ticket_id: UUID
    ticket_number: int
    type: NotificationType
    title: str
    snippet: str | None = None
    actor_user_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None

# ports_notifications.py
class NotificationRepository(Protocol):
    async def add_many(self, notifications: list[Notification]) -> None: ...
    async def list_for_user(
        self, user_id: UUID, only_unread: bool, page: int, per_page: int
    ) -> tuple[list[Notification], int]: ...
    async def unread_count(self, user_id: UUID) -> int: ...
    async def mark_read(self, user_id: UUID, ids: list[UUID], at: datetime) -> None: ...
    async def mark_all_read(self, user_id: UUID, at: datetime) -> None: ...

class NotificationPublisher(Protocol):
    async def publish(self, tenant_slug: str, user_ids: list[UUID]) -> None: ...
```

`ticket_number` gravado na notificacao (desnormalizado) para o dropdown nao precisar de join; e imutavel no ticket.

- [ ] **Step 1: Escrever os testes que falham**

Em `test_repositories_notifications.py` (seguir o setup de tenant dos testes de integracao existentes, ex. `test_repositories_tickets.py`): criar 3 notificacoes para o usuario A (uma lida) e 1 para B; asserts: `unread_count(A) == 2`; `list_for_user(A, only_unread=False, page=1, per_page=10)` retorna 3 ordenadas por `created_at` desc com total 3; `mark_read(A, [id1], now)` zera so aquela; `mark_all_read(A, now)` zera o resto; nada disso toca as de B. Em `test_migrations.py`, seguir o estilo existente: tabela `notifications` existe no schema do tenant com os indices `ix_notifications_user_unread` e `ix_notifications_user_created`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_notifications.py -v`
Expected: FAIL (tabela/modulo nao existem).

- [ ] **Step 3: Implementar**

`NotificationModel` em `models_tenant.py` (espelhar o estilo de `TicketReadModel`/`TicketTimelineEventModel`):

```python
class NotificationModel(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id"), nullable=False
    )
    ticket_number: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    snippet: Mapped[str | None] = mapped_column(String(200))
    actor_user_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Migration `0009_notifications.py` (`down_revision = "0008_indices_busca"`) criando a tabela e os dois indices (o parcial com `postgresql_where=sa.text("read_at IS NULL")`). `SqlNotificationRepository` em `repositories_notifications.py` seguindo o estilo de `SqlTicketReadRepository` (`repositories_tickets.py:609`): `add_many` com `session.add_all`, `mark_read`/`mark_all_read` com `update(...).where(NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None))`, `list_for_user` com `order_by(created_at.desc())` + `limit/offset` + count separado.

- [ ] **Step 4: Rodar e ver passar**

```bash
./.venv/Scripts/python.exe -m sac.infrastructure.migrate all
./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_notifications.py tests/integration/test_migrations.py -v
```
Expected: PASS, incluindo provisionamento de tenant novo.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src migrations tests
git commit -m "Adiciona tabela e repositorio de notificacoes por tenant"
```

---

### Task 2: Fan-out de notificacoes (regras de destinatario)

**Files:**
- Create: `backend/src/sac/application/use_cases/notifications_fanout.py`
- Create: `backend/tests/unit/application/test_notifications_fanout.py`
- Modify: `backend/tests/unit/fakes_tickets.py` (fake de `NotificationRepository` e `NotificationPublisher` se nao couber em arquivo novo `fakes_notifications.py` — seguir a organizacao existente dos fakes)

**Interfaces:**
- Consumes: `Notification`, `NotificationType`, `NotificationRepository`, `NotificationPublisher` (Task 1); `TicketCommentRepository.list_by_ticket` (ports_tickets.py:107); `Ticket` (domain), `TicketActor`.
- Produces:

```python
class NotificationFanout:
    def __init__(
        self,
        notifications: NotificationRepository,
        comments: TicketCommentRepository,
        publisher: NotificationPublisher,
        tenant_slug: str,
    ) -> None: ...

    async def notify(
        self,
        actor: TicketActor,
        ticket: Ticket,
        type_: NotificationType,
        title: str,
        snippet: str | None = None,
        extra_recipient: UUID | None = None,
    ) -> None: ...
```

`extra_recipient` cobre a atribuicao: o novo atendente ja esta em `ticket.attendant_user_id` quando o notify roda, mas o parametro deixa o chamador explicito e cobre o caso de notificar o atendente anterior no futuro (nao fazer isso agora — YAGNI; o parametro existe porque a criacao precisa notificar o atendente quando `ticket.attendant_user_id != actor.user_id` sem depender de comentarios).

- [ ] **Step 1: Escrever os testes unitarios que falham**

Com fakes em memoria (seguir `tests/unit/fakes_tickets.py`):

```python
async def test_notifica_atribuido_e_comentaristas_excluindo_ator(): ...
# ticket.attendant_user_id=A; comentarios de B e C; actor=B
# espera notificacoes para {A, C}, publisher chamado com esses ids

async def test_ator_unico_envolvido_nao_gera_nada(): ...
# attendant=A, sem comentarios, actor=A -> add_many nao chamado, publish nao chamado

async def test_destinatarios_deduplicados(): ...
# attendant=A, A tambem comentou -> uma notificacao so para A (actor=B)

async def test_snippet_e_titulo_propagados(): ...
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/application/test_notifications_fanout.py -v`
Expected: FAIL (modulo nao existe).

- [ ] **Step 3: Implementar**

```python
async def notify(self, actor, ticket, type_, title, snippet=None, extra_recipient=None):
    recipients: set[UUID] = {ticket.attendant_user_id}
    if extra_recipient is not None:
        recipients.add(extra_recipient)
    for comment in await self._comments.list_by_ticket(ticket.id):
        recipients.add(comment.author_user_id)
    recipients.discard(actor.user_id)
    if not recipients:
        return
    now = datetime.now(UTC)
    await self._notifications.add_many(
        [
            Notification(
                id=uuid4(), user_id=uid, ticket_id=ticket.id,
                ticket_number=ticket.number, type=type_, title=title,
                snippet=snippet, actor_user_id=actor.user_id, created_at=now,
            )
            for uid in sorted(recipients)
        ]
    )
    await self._publisher.publish(self._tenant_slug, sorted(recipients))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit -v -k fanout`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Adiciona fan-out de notificacoes com regras de destinatario"
```

---

### Task 3: Emissao nos use cases + reatribuicao de atendente

**Files:**
- Modify: `backend/src/sac/domain/tickets.py` (adicionar `TimelineEventType.ATRIBUICAO = "atribuicao"`)
- Modify: `backend/src/sac/application/use_cases/tickets_workflow.py`
- Modify: `backend/src/sac/application/use_cases/tickets_crud.py`
- Modify: `backend/src/sac/interface/routers/tickets.py`, `backend/src/sac/interface/schemas.py`, `backend/src/sac/interface/deps.py`
- Test: `backend/tests/unit/application/test_tickets_workflow.py` (existente — estender), `backend/tests/unit/application/test_tickets_crud.py` (existente — estender), `backend/tests/integration/test_tickets_workflow_api.py` (estender)

**Interfaces:**
- Consumes: `NotificationFanout` (Task 2), `_TransitionUseCase._apply` (tickets_workflow.py:41), `CreateTicketUseCase`/`UpdateTicketUseCase`/`AddCommentUseCase` (tickets_crud.py), `transition_event` (tickets_shared.py:80).
- Produces:
  - `_TransitionUseCase.__init__(tickets, timeline, fanout: NotificationFanout | None = None)` — todos os use cases de workflow repassam; `_apply` chama `await self._fanout.notify(actor, ticket, NotificationType.TRANSICAO, title)` quando fanout nao e None (default None mantem os testes unitarios existentes intactos ate serem atualizados; o router SEMPRE injeta).
  - `CreateTicketUseCase` ganha `fanout` e, apos criar, se `ticket.attendant_user_id != actor.user_id`: timeline `ATRIBUICAO` ("Ticket atribuido") + `fanout.notify(..., NotificationType.ATRIBUICAO, f"Ticket #{ticket.number} atribuido a voce", extra_recipient=ticket.attendant_user_id)`.
  - `UpdateTicketInput` ganha `attendant_user_id: UUID | None = None`; `UpdateTicketUseCase` com `fanout`: quando vem e difere do atual, exige `Permission.EDITAR_QUALQUER_TICKET` (senao `PermissionDeniedError`), troca, timeline `ATRIBUICAO` com `old_value`/`new_value` (ids como string) e notifica o novo atendente.
  - `AddCommentUseCase` ganha `fanout`; apos gravar, `notify(..., NotificationType.COMENTARIO, f"Novo comentario no ticket #{ticket.number}", snippet=text[:200])`.
  - `TicketUpdateIn` (schemas.py:306) ganha `attendant_user_id: UUID | None = None`.
  - `deps.py` ganha `get_notification_fanout(session=Depends(get_tenant_session), slug=Depends(get_tenant_slug))` retornando fanout com `SqlNotificationRepository`, comments repo de `build_ticket_repos(session)` e o publisher da Task 4 (nesta task, usar um publisher stub `NullPublisher` em `repositories_notifications.py` que faz nada; a Task 4 o substitui).

- [ ] **Step 1: Escrever os testes que falham**

Unit (estender os arquivos existentes, seguindo seus fakes): transicao com fanout registra notificacao de tipo `transicao` para o atendente quando actor e outro; criacao com `attendant_user_id` de terceiro gera timeline `ATRIBUICAO` + notificacao; update trocando atendente sem `EDITAR_QUALQUER_TICKET` levanta `PermissionDeniedError`; com permissao, troca + notifica; comentario notifica atendente e comentaristas anteriores com snippet. Integracao (`test_tickets_workflow_api.py`): aprovar um ticket com atendente != ator grava linha em `notifications` do schema do tenant.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit -v -k "workflow or crud"`
Expected: FAIL nos testes novos.

- [ ] **Step 3: Implementar**

Conforme Interfaces. Cuidado: `_apply` recebe `actor` e ja tem o `ticket` com status novo e o `title` — a chamada do fanout entra depois de `self._tickets.update(ticket)`. Em `UpdateTicketUseCase`, a troca de atendente NAO altera a regra de edicao existente (`ensure_can_edit` continua primeiro); o campo omitido (None) significa "nao mexer".

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS geral (unit + integracao).

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Emite notificacoes nas transicoes, comentarios e atribuicao com reatribuicao na edicao"
```

---

### Task 4: Publisher pg_notify e API REST de notificacoes

**Files:**
- Create: `backend/src/sac/interface/routers/notifications.py`
- Modify: `backend/src/sac/infrastructure/repositories_notifications.py` (adicionar `PgNotifyPublisher`, remover `NullPublisher` do wiring)
- Modify: `backend/src/sac/interface/deps.py`, `backend/src/sac/interface/schemas.py`, `backend/src/sac/interface/app.py` (include router)
- Test: `backend/tests/integration/test_notifications_api.py`

**Interfaces:**
- Consumes: `SqlNotificationRepository` (Task 1), `NotificationFanout` (Task 2), `get_tenant_session`, `get_current_identity`.
- Produces:
  - `PgNotifyPublisher(session)` com `publish(tenant_slug, user_ids)` executando `SELECT pg_notify('sac_notifications', :payload)` com payload JSON `{"tenant": slug, "users": ["<uuid>", ...]}` (canal unico global; o listener filtra). Payload de NOTIFY tem limite de 8000 bytes — com dezenas de destinatarios nao chega perto; nao incluir conteudo da notificacao no payload.
  - Endpoints (router `prefix="/notificacoes"`, todos com sessao de tenant):
    - `GET /api/notificacoes?apenas_nao_lidas=&page=&per_page=` -> `{"items": [NotificationOut], "total": int}`; `NotificationOut`: `id, ticket_id, ticket_number, type, title, snippet, created_at, read_at`.
    - `GET /api/notificacoes/contador` -> `{"nao_lidas": int}`.
    - `POST /api/notificacoes/marcar-lidas` body `{"ids": [UUID] | null}` (null = todas) -> 204.

- [ ] **Step 1: Escrever os testes de API que falham**

Seguir `test_tickets_api.py` (helpers de login/tenant): fluxo completo — usuario B comenta em ticket atribuido a A; `GET /contador` como A retorna 1; `GET /notificacoes` lista com `ticket_number` e `type == "comentario"`; `marcar-lidas` sem ids zera o contador; notificacoes de A nao aparecem para B. Teste extra: apos o comentario, `SELECT pg_notify` aconteceu — verificavel indiretamente na Task 5; aqui basta a API.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_notifications_api.py -v`
Expected: FAIL (rota 404).

- [ ] **Step 3: Implementar**

Router seguindo o estilo de `members.py`/`tickets.py`; `get_notification_fanout` (Task 3) passa a usar `PgNotifyPublisher(session)` — mesma sessao do use case, NOTIFY sai no commit do request. Registrar router em `app.py`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_notifications_api.py -v`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Adiciona API REST de notificacoes e publisher pg_notify"
```

---

### Task 5: Listener LISTEN/NOTIFY e endpoint SSE

**Files:**
- Create: `backend/src/sac/infrastructure/notify_listener.py`
- Modify: `backend/src/sac/interface/routers/notifications.py` (endpoint `/stream`)
- Modify: `backend/src/sac/interface/app.py` (state + shutdown no lifespan)
- Test: `backend/tests/integration/test_notifications_stream.py`, `backend/tests/unit/infrastructure/test_notify_listener.py`

**Interfaces:**
- Consumes: `settings.database_url`, payload JSON do canal `sac_notifications` (Task 4), `get_current_identity`.
- Produces:

```python
class NotificationListener:
    """Uma conexao asyncpg em LISTEN por instancia; registry em memoria de
    filas SSE por (tenant_slug, user_id). start() e lazy e idempotente."""

    def __init__(self, dsn: str) -> None: ...
    async def subscribe(self, tenant_slug: str, user_id: UUID) -> asyncio.Queue[str]: ...
    def unsubscribe(self, tenant_slug: str, user_id: UUID, queue: asyncio.Queue[str]) -> None: ...
    async def start(self) -> None: ...   # conecta e faz LISTEN; reconecta com backoff
    async def stop(self) -> None: ...
```

- Endpoint `GET /api/notificacoes/stream`: `StreamingResponse(..., media_type="text/event-stream")`. Loop: `asyncio.wait_for(queue.get(), timeout=25)` -> `data: {"tipo": "nova"}\n\n`; timeout -> heartbeat `: ping\n\n`; `finally` faz unsubscribe. O dado empurrado nao carrega conteudo — o cliente refaz GET (tabela e a fonte de verdade).

- [ ] **Step 1: Escrever os testes que falham**

Unit (`test_notify_listener.py`, sem banco): `_dispatch(payload_json)` entrega so nas filas dos usuarios do payload e ignora payload malformado sem derrubar o loop (json invalido -> log e segue). Integracao (`test_notifications_stream.py`): com `httpx.AsyncClient(transport=ASGITransport(app), ...)` e `client.stream("GET", "/api/notificacoes/stream", headers=auth_A)`: dispara comentario de B via API em outra chamada, le linhas do stream com timeout de ~10s e espera `data:` com `"tipo": "nova"`. Conferir no conftest existente como o app e construido para reusar engine/settings.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_notifications_stream.py tests/unit/infrastructure/test_notify_listener.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

- `notify_listener.py` usa `asyncpg.connect` direto (dsn = `settings.database_url` sem o `+asyncpg`; escrever helper `asyncpg_dsn(url)` com teste). `conn.add_listener("sac_notifications", callback)`; callback parseia JSON e poe `"nova"` nas filas de `(tenant, user)` presentes no registry. Task de watchdog: se a conexao cair, reconectar com backoff exponencial (1s, 2s, ... max 30s), logando.
- `app.py`: `app.state.notify_listener = NotificationListener(...)` criado no create_app mas SEM conectar; `start()` lazy no primeiro subscribe (lock interno). Lifespan chama `stop()` no shutdown, antes de `engine.dispose()`.
- asyncpg ja e dependencia transitiva do SQLAlchemy async — importa direto, sem mudar pyproject.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_notifications_stream.py -v` e depois a suite inteira.
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Adiciona listener LISTEN/NOTIFY e endpoint SSE de notificacoes"
```

---

### Task 6: Preferencias de usuario (migration public + API)

**Files:**
- Create: `backend/migrations/public/versions/0004_user_preferences.py`
- Create: `backend/src/sac/application/use_cases/preferences.py`
- Create: `backend/src/sac/interface/routers/preferences.py`
- Modify: `backend/src/sac/domain/entities.py` (dataclass `UserPreferences`), `backend/src/sac/application/ports.py` (port), `backend/src/sac/infrastructure/models.py` (`UserPreferencesModel`), `backend/src/sac/infrastructure/repositories.py` (`SqlUserPreferencesRepository`), `backend/src/sac/interface/deps.py`, `schemas.py`, `app.py`
- Test: `backend/tests/unit/application/test_preferences.py`, `backend/tests/integration/test_preferences_api.py`, `test_migrations.py`

**Interfaces:**
- Produces:

```python
@dataclass
class UserPreferences:
    user_id: UUID
    theme: str = "sistema"        # "claro" | "escuro" | "sistema"
    notify_toast: bool = True
    notify_sound: bool = False

class UserPreferencesRepository(Protocol):
    async def get(self, user_id: UUID) -> UserPreferences | None: ...
    async def upsert(self, prefs: UserPreferences) -> None: ...
```

- `GET /api/preferencias` (so `get_current_identity`, sem tenant) -> `{"theme": str, "notify_toast": bool, "notify_sound": bool}`; sem linha, devolve defaults sem gravar.
- `PUT /api/preferencias` body com os 3 campos; `theme` validado contra os 3 valores (schema com `Literal["claro", "escuro", "sistema"]`).
- Migration public `0004_user_preferences` (`down_revision = "0003_pg_trgm"`): tabela `user_preferences` no schema public, PK `user_id` com FK para `users.id`, `theme varchar(10) not null default 'sistema'`, dois booleans not null com default, `updated_at timestamptz not null default now()`.

- [ ] **Step 1: Escrever os testes que falham**

Unit: use case devolve defaults quando repo retorna None; rejeita theme invalido (`ValidationError`). Integracao: GET sem linha -> defaults; PUT grava; GET reflete; PUT de novo atualiza (upsert); 401 sem token; funciona para super_admin sem tenant no token.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_preferences_api.py tests/unit/application/test_preferences.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Upsert com `pg_insert(...).on_conflict_do_update` (mesmo padrao de `SqlTicketReadRepository`). Router registrado em `app.py`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m sac.infrastructure.migrate all && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src migrations tests
git commit -m "Adiciona preferencias de usuario com tema e opcoes de notificacao"
```

---

### Task 7: Busca global (indices + endpoint)

**Files:**
- Create: `backend/migrations/tenant/versions/0010_indices_busca_global.py`
- Create: `backend/src/sac/application/use_cases/global_search.py`
- Create: `backend/src/sac/infrastructure/repositories_search.py`
- Create: `backend/src/sac/interface/routers/search.py`
- Modify: `backend/src/sac/interface/deps.py`, `schemas.py`, `app.py`
- Test: `backend/tests/unit/application/test_global_search.py`, `backend/tests/integration/test_search_api.py`, `test_migrations.py`

**Interfaces:**
- Consumes: `escape_like`/`LIKE_ESCAPE_CHAR` (`infrastructure/sql_search.py`), `restrict_to_own` (tickets_shared.py:19), indices trgm existentes (`customers.name`, `products.name`, `tickets.order_code`).
- Produces:
  - Migration `0010` (`down_revision = "0009_notifications"`): GIN trgm com `public.gin_trgm_ops` em `customers.document`, `customers.email`, `customers.phone`, `products.sku` (nomes `ix_customers_document_trgm` etc.).
  - `GlobalSearchResult` (application):

```python
@dataclass(frozen=True)
class TicketHit:
    id: UUID; number: int; status: TicketStatus; customer_name: str | None; brand_name: str | None

@dataclass(frozen=True)
class CustomerHit:
    id: UUID; name: str; document: str | None

@dataclass(frozen=True)
class ProductHit:
    id: UUID; name: str; sku: str | None

@dataclass(frozen=True)
class GlobalSearchResult:
    tickets: list[TicketHit]; customers: list[CustomerHit]; products: list[ProductHit]

class GlobalSearchRepository(Protocol):
    async def search(
        self, term: str, owner_user_id: UUID | None, limit: int
    ) -> GlobalSearchResult: ...
```

  - `GlobalSearchUseCase(repo).execute(actor, term)`: trim; menos de 2 chars -> resultado vazio sem query; `owner_user_id = restrict_to_own(actor)` (escopo do papel vale para o grupo tickets; visualizador ve todos, atendente so os seus).
  - `GET /api/busca?q=` -> `{"tickets": [...], "clientes": [...], "produtos": [...]}` com ate 5 itens por grupo. Qualquer papel do tenant (a dependencia e so a sessao de tenant; a visibilidade de tickets ja e cortada pelo use case).
  - Normalizacao: termo `so_digitos = re.sub(r"\D", "", term)`; se nao vazio, tickets tambem casam `number` por prefixo (cast texto) e clientes casam `document`/`phone` por `ilike` com os digitos; email/nome/sku/order_code usam o termo original com `escape_like`.

- [ ] **Step 1: Escrever os testes que falham**

Unit: termo curto retorna vazio sem tocar o repo (repo fake que explode se chamado); normalizacao de digitos ("532.876..." vira busca por documento). Integracao (`test_search_api.py`): semear cliente com documento e email, produto com SKU, ticket com order_code; buscar por fragmento de cada um e conferir o grupo certo; atendente nao ve ticket alheio no grupo tickets mas ve clientes/produtos; `q` com `%` nao vaza curinga (escape_like); limite de 5 por grupo.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_search_api.py tests/unit/application/test_global_search.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`SqlGlobalSearchRepository(session)`: tres selects (tickets com join em customers/brands para nome; customers; products), cada um `limit(limit)`. Migration antes dos selects. Router + include em `app.py`.

- [ ] **Step 4: Rodar e ver passar**

```bash
./.venv/Scripts/python.exe -m sac.infrastructure.migrate all
./.venv/Scripts/python.exe -m pytest -q
```
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src migrations tests
git commit -m "Adiciona busca global com indices trgm de identificadores"
```

---

### Task 8: Membros por tenant (gestao pelo admin)

**Files:**
- Create: `backend/src/sac/application/use_cases/members_admin.py`
- Modify: `backend/src/sac/application/use_cases/members.py` (variante gerencial da listagem) ou o proprio `members_admin.py` (decidir ao ler; manter listagem enxuta intacta)
- Modify: `backend/src/sac/interface/routers/members.py`, `schemas.py`, `deps.py`
- Modify: `backend/src/sac/application/ports.py` / `backend/src/sac/infrastructure/repositories.py` (o que faltar: `UserTenantRepository.get(user_id, tenant_id)`, `update(link)`; `UserRepository.get_by_email` ja existe)
- Test: `backend/tests/unit/application/test_members_admin.py`, `backend/tests/integration/test_members_admin_api.py`

**Interfaces:**
- Consumes: `CreateUserUseCase`/`ResetPasswordUseCase`/`LinkUserToTenantUseCase` (platform_users.py — reusar as validacoes, nao duplicar), `UserTenant` (`active: bool` ja existe em entities.py:59), `require_permission(Permission.GERENCIAR_USUARIOS)`, `get_tenant_slug`.
- Produces (todos os use cases recebem `tenant_id` resolvido do slug do token e `acting_user_id`):

```python
class CreateMemberUseCase:
    async def execute(self, data: CreateMemberInput) -> MemberDetail: ...
    # email existente: valida que o usuario NAO e super_admin e nao tem vinculo
    #   com este tenant; cria vinculo com o papel pedido.
    # email novo: exige name e password; cria usuario global + vinculo.

class UpdateMemberLinkUseCase:
    async def execute(self, acting_user_id: UUID, user_id: UUID, role: Role | None, active: bool | None) -> MemberDetail: ...
    # salvaguardas: user_id == acting_user_id -> ConflictError("nao e possivel alterar o proprio vinculo")
    #   usuario alvo super_admin -> NotFoundError (nao revelar)
    #   vinculo inexistente neste tenant -> NotFoundError

class ResetMemberPasswordUseCase:
    async def execute(self, acting_user_id: UUID, user_id: UUID, new_password: str) -> None: ...
    # mesmas salvaguardas; reusa a validacao de senha minima de platform_users
```

Endpoints (router `members.py`, novos, com `dependencies=[Depends(require_permission(Permission.GERENCIAR_USUARIOS))]` — o GET enxuto existente NAO muda):
- `GET /api/membros/gerencia` -> lista com `id, name, email, role, active (do vinculo), user_active`
- `POST /api/membros` body `{email, role, name?, password?}` -> 201 MemberDetail
- `PATCH /api/membros/{user_id}` body `{role?, active?}` -> MemberDetail
- `POST /api/membros/{user_id}/senha` body `{password}` -> 204

- [ ] **Step 1: Escrever os testes que falham**

Unit: cada salvaguarda (proprio vinculo, super_admin invisivel, email ja vinculado, email novo sem senha -> ValidationError). Integracao (matriz de autorizacao, seguir `test_authorization.py`): admin cria membro novo (login do novo funciona em seguida), supervisor recebe 403 em todos os 4 endpoints, atendente idem; admin nao se desativa; PATCH de papel reflete no proximo login.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_members_admin_api.py tests/unit/application/test_members_admin.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Use cases compondo os de platform_users (nao reimplementar hash/validacao). O router resolve `tenant_id` a partir do slug com `SqlTenantRepository.get_by_slug` (padrao de `require_module` em deps.py:298).

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Adiciona gestao de membros do tenant para o papel admin"
```

---

### Task 9: Rate limit fino (refresh, XFF, janela dupla)

**Files:**
- Modify: `backend/src/sac/interface/rate_limit.py`, `backend/src/sac/interface/routers/auth.py`, `backend/src/sac/infrastructure/settings.py`, `backend/src/sac/interface/app.py`
- Test: `backend/tests/unit/interface/test_rate_limit.py` e o teste de integracao de auth — ambos existentes com nomes a confirmar; localizar com `Glob tests/**/test_*rate*|*auth*` e estender os arquivos reais em vez de criar duplicados

**Interfaces:**
- Produces:
  - Settings novos: `trusted_proxy: bool = False`, `login_rate_ip_tenant: int = 5`, `login_rate_ip: int = 30`, `login_rate_window_seconds: float = 60.0`.
  - `rate_limit.py` ganha `client_ip(request, trusted_proxy) -> str`: com `trusted_proxy=True` usa o primeiro IP de `X-Forwarded-For` se presente; senao `request.client.host`.
  - `app.state.login_limiter` (IP+tenant, como hoje) e `app.state.login_ip_limiter` (IP global, janela larga), ambos construidos com os settings.
  - `POST /auth/login`: checa `login_ip_limiter.check(ip)` e depois `login_limiter.check(f"{ip}:{slug}")`.
  - `POST /auth/refresh`: checa `login_ip_limiter.check(f"refresh:{ip}")` (chave propria, mesma janela larga).

- [ ] **Step 1: Escrever os testes que falham**

Unit: `client_ip` honra XFF so com flag; janela larga bloqueia na 31a tentativa de slugs variados. Integracao: 31 logins errados com tenants diferentes do mesmo IP -> 429/`rate_limited` na 31a; refresh em loop bloqueia; refresh valido nao e bloqueado nas primeiras tentativas.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/interface/test_rate_limit.py -v`
Expected: FAIL nos novos.

- [ ] **Step 3: Implementar**

Conforme Interfaces. Documentar em docstring do `rate_limit.py`: in-memory por decisao do spec (instancia unica); trocar por backend compartilhado exige so outra implementacao do check.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Refina o rate limit de login com janela por IP, refresh e X-Forwarded-For"
```

---

### Task 10: Delecao direta de objetos no storage

**Files:**
- Modify: `backend/src/sac/application/ports_attachments.py` (`StoragePort.delete`), `backend/src/sac/infrastructure/storage.py` (`S3Storage.delete`), `backend/src/sac/application/use_cases/attachments.py` (3 use cases), `backend/src/sac/infrastructure/worker.py` (passar storage ao ExpirePending), `backend/src/sac/interface/routers/tickets.py` (injetar storage onde faltar)
- Test: `backend/tests/unit/application/test_attachments.py` (existente — estender), `backend/tests/integration/test_storage.py` (existente — estender), `backend/tests/integration/test_worker.py`

**Interfaces:**
- Produces:
  - `StoragePort.delete(self, key: str) -> None` — idempotente: objeto inexistente NAO e erro. `S3Storage.delete` usa `delete_object` com o client interno; `ClientError` de not-found e silencioso, os demais viram `StorageUnavailableError`.
  - Helper na application (`attachments.py`): `_delete_object_keys(storage, anexo)` apagando `storage_key`, `preview_key`, `preview_medium_key` (os que nao forem None), cada um em try/except `StorageUnavailableError` com `logger.warning` — best-effort, nunca propaga.
  - `DeleteAttachmentUseCase`, `DiscardIntentUseCase` (so no caminho PENDENTE) e `ExpirePendingUseCase` ganham `storage: StoragePort` e chamam o helper depois de persistir o estado.

- [ ] **Step 1: Escrever os testes que falham**

Unit com storage fake que registra deletes e pode levantar `StorageUnavailableError`: delete apaga as 3 chaves; falha de storage nao impede o soft delete (estado persiste, warning); discard de intencao PENDENTE apaga `storage_key`; expirar apaga objetos dos expirados. Integracao (`test_storage.py` contra MinIO): `delete` remove objeto e e idempotente.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/application/test_attachments.py -v`
Expected: FAIL nos novos.

- [ ] **Step 3: Implementar**

Conforme Interfaces, atualizando os pontos de construcao dos use cases (router e worker `_expire_pending`).

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Apaga objetos do storage ao expirar, descartar e excluir anexos"
```

---

### Task 11: Job de reconciliacao de orfaos no worker

**Files:**
- Create: `backend/src/sac/application/use_cases/storage_reconcile.py`
- Modify: `backend/src/sac/application/ports_attachments.py` (`StoragePort.list_keys`), `backend/src/sac/infrastructure/storage.py`, `backend/src/sac/infrastructure/worker.py`, `backend/src/sac/infrastructure/settings.py` (`reconcile_orphans_hours: int = 24`)
- Test: `backend/tests/unit/application/test_storage_reconcile.py`, `backend/tests/integration/test_worker.py` (estender)

**Interfaces:**
- Consumes: chaves legitimas vem de DUAS fontes por tenant — `ticket_attachments` (`storage_key`, `preview_key`, `preview_medium_key`; TODOS os status e mesmo soft-deletados que a Task 10 nao apagou por falha) e fotos de produto (`object_key` + previews; ver `product_photo.py` e o repositorio de fotos em `repositories_attachments.py` para o formato real das chaves — ler antes).
- Produces:
  - `StoragePort.list_keys(self, prefix: str) -> list[tuple[str, datetime]]` — chave + last_modified; `S3Storage` implementa com paginator de `list_objects_v2`.
  - Port novo em `ports_attachments.py`: `KnownKeysPort` com `async def known_keys(self) -> set[str]` (implementacao SQL por tenant em `repositories_attachments.py` unindo as duas fontes).
  - `ReconcileOrphansUseCase(storage, known_keys, prefix, older_than_hours).execute(now) -> int`: lista `prefix`, apaga chave ausente do banco com `last_modified < now - older_than_hours`; retorna total apagado; falha de UMA delecao loga e segue.
  - Worker: funcao `reconcile_orphans_all(engine, storage, hours)` iterando tenants ativos (mesmo padrao de `expire_pending_all`, com o mesmo isolamento de falha por tenant); agendada em `run_forever` a cada 86400s (`reconcile_every_seconds: float = 86400.0` como parametro).

- [ ] **Step 1: Escrever os testes que falham**

Unit com storage fake: objeto orfao velho e apagado; orfao recente (menos de 24h) fica; chave conhecida fica; falha de delete em um objeto nao impede os demais. Integracao (worker, seguir `test_worker.py`): subir objeto solto no MinIO sob o prefixo do tenant com mock de idade (ou aceitar `older_than_hours=0` no teste), rodar `reconcile_orphans_all`, objeto some e anexo legitimo permanece.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/application/test_storage_reconcile.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Conforme Interfaces. O prefixo por tenant e `f"{slug}/"` — confirmar contra `build_attachment_key`/`build_product_photo_key` no dominio antes de fixar (as chaves de anexo comecam com `{tenant}/`).

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q
git add src tests
git commit -m "Adiciona reconciliacao diaria de objetos orfaos no worker"
```

---

### Task 12: Frontend — sino de notificacoes com SSE

Invocar o skill `frontend-design` antes de escrever UI (vale para as Tasks 12-17).

**Files:**
- Create: `frontend/src/lib/notifications.ts` (tipos + fetchers + hook de stream)
- Create: `frontend/src/components/layout/NotificationBell.tsx`
- Modify: `frontend/src/components/layout/Header.tsx`
- Test: build/lint (teste de comportamento fica no e2e da Task 18)

**Interfaces:**
- Consumes: `api`/`apiRaw`/`loadSession` (`lib/api.ts`), endpoints das Tasks 4-5, componentes ui existentes (`dropdown-menu`, `button`), sonner (`toast`), preferencias (Task 14 — ate la, toast on / som off por default local).
- Produces:
  - `lib/notifications.ts`: `NotificationItem` (espelho de NotificationOut), `fetchNotifications(page, apenasNaoLidas)`, `fetchCounter()`, `markRead(ids: string[] | null)`, e `startNotificationStream(onEvent: () => void): () => void` — abre `fetch("/api/notificacoes/stream", {headers: Authorization})`, le o body com `ReadableStream`/`TextDecoder` linha a linha, chama `onEvent()` a cada bloco `data:`; reconecta com backoff (1s..30s) e para quando o cleanup e chamado; em 401 tenta uma vez o refresh via `apiRaw` (reusar `apiRaw` para a conexao ja resolve o retry).
  - `NotificationBell`: icone `Bell` (lucide) com badge numerico (esconde acima de 99 como "99+"), dropdown com as 10 mais recentes (react-query `["notificacoes"]`), acao "Marcar todas como lidas", item clicado navega `/tickets/{ticket_id}` e chama `markRead([id])`. Ao receber evento do stream: `invalidateQueries(["notificacoes"])` + `invalidateQueries(["notificacoes-contador"])`, toast com o titulo mais recente e beep curto — ambos condicionados as preferencias.
  - Som: asset unico `frontend/src/assets/notify.wav` (gerar beep curto de ~200ms programaticamente com WebAudio no proprio codigo em vez de asset, se preferir zero binario — decisao do implementador, sem biblioteca nova).
  - `Header.tsx`: sino entra a esquerda do dropdown de usuario; a11y: `aria-label="Notificacoes"`, badge com `aria-live="polite"`.

- [ ] **Step 1: Implementar conforme Interfaces** (frontend nao tem runner de unit; a verificacao e build + lint + e2e na Task 18)

- [ ] **Step 2: Verificar no app real**

`docker compose restart backend worker` e conferir manualmente com dois logins (tenant e2e): comentario de um aparece como badge/toast no outro sem reload.

- [ ] **Step 3: Verificacoes e commit**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Adiciona sino de notificacoes com stream SSE no header"
```

---

### Task 13: Frontend — busca global (Ctrl+K)

**Files:**
- Create: `frontend/src/components/layout/GlobalSearch.tsx`
- Create: `frontend/src/lib/search.ts`
- Modify: `frontend/src/components/layout/Header.tsx`
- Test: build/lint + e2e (Task 18)

**Interfaces:**
- Consumes: `GET /api/busca?q=` (Task 7), `Dialog`/`Command` de `components/ui` (verificar se `cmdk`/Command existe; se nao, compor com Dialog + input + listas — sem dependencia nova sem necessidade), `useNavigate`.
- Produces:
  - `lib/search.ts`: tipos `SearchHits` (`tickets`, `clientes`, `produtos`) + `globalSearch(q)`.
  - `GlobalSearch`: botao no header (icone lupa + texto "Buscar" + kbd "Ctrl K") abrindo dialog; input com debounce de 250ms (so consulta com 2+ chars); grupos "Tickets" (numero, cliente, status), "Clientes" (nome, documento), "Produtos" (nome, SKU); navegacao por setas + Enter; Enter em ticket -> `/tickets/{id}`, cliente -> `/cadastros/clientes` com filtro (conferir se ClientesPage aceita busca via URL; senao navegar simples), produto -> `/cadastros/produtos`; rodape "Buscar na fila" -> `/tickets?q={termo}`. Atalho global `Ctrl+K`/`Cmd+K` (listener em `keydown`, `preventDefault`).
  - Estados: vazio ("Digite ao menos 2 caracteres"), sem resultados, carregando — copy sem acentos.

- [ ] **Step 1: Implementar conforme Interfaces** (com frontend-design)

- [ ] **Step 2: Verificar no app real** (busca por documento de cliente e numero de ticket no tenant e2e)

- [ ] **Step 3: Verificacoes e commit**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Adiciona busca global com atalho Ctrl+K no header"
```

---

### Task 14: Frontend — pagina de preferencias e ThemeProvider

**Files:**
- Create: `frontend/src/pages/preferencias/PreferenciasPage.tsx`
- Create: `frontend/src/lib/preferences.ts`
- Modify: `frontend/src/main.tsx` (ThemeProvider + rota `/preferencias` dentro de `RequireAuth`, fora de `RequireTenant` — super_admin tambem tem preferencias), `frontend/src/components/layout/Header.tsx` (item "Preferencias" no dropdown do usuario)
- Test: build/lint + e2e (Task 18)

**Interfaces:**
- Consumes: `GET/PUT /api/preferencias` (Task 6), `next-themes` (ja instalado; `ThemeProvider` com `attribute="class"`, `themes={["light", "dark"]}`, `enableSystem`), react-query.
- Produces:
  - `lib/preferences.ts`: `Preferences = { theme: "claro" | "escuro" | "sistema"; notify_toast: boolean; notify_sound: boolean }`, `fetchPreferences()`, `savePreferences(p)`, hook `usePreferences()` (query `["preferencias"]`, staleTime longo) — e o mapa `claro->light, escuro->dark, sistema->system` num helper `toNextTheme(theme)`.
  - `PreferenciasPage`: secao Tema (radio de 3 opcoes aplicando `setTheme` imediatamente + PUT), secao Notificacoes (dois switches + PUT). Feedback com toast de sucesso.
  - Sincronizacao: apos login/carregar sessao, um efeito (no AppShell ou no proprio hook) aplica `setTheme(toNextTheme(prefs.theme))` quando a query resolve.
  - `NotificationBell` (Task 12) passa a ler `usePreferences()` para toast/som.

- [ ] **Step 1: Implementar conforme Interfaces** (com frontend-design)

- [ ] **Step 2: Verificar no app real** (trocar tema persiste apos reload e re-login em outro navegador)

- [ ] **Step 3: Verificacoes e commit**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Adiciona pagina de preferencias com tema e opcoes de notificacao"
```

---

### Task 15: Frontend — passe de dark mode

A maior fatia de UI da fase. Invocar `frontend-design` e seguir `docs/identidade-visual.md`; o dataviz skill cobre as cores dos graficos.

**Files:**
- Modify: `frontend/src/index.css` (tokens do tema escuro — bloco `.dark { ... }` com as variaveis), componentes que fixam cor fora dos tokens (auditar; candidatos conhecidos: graficos do dashboard, badges de status `STATUS_ACCENTS`, `SlaBadge`, skeletons, `TicketQueueCard`)
- Test: build/lint + verificacao visual tela a tela

**Interfaces:**
- Consumes: tokens existentes de `index.css` (paleta clara), `next-themes` montado (Task 14).
- Produces: paleta escura completa nos tokens; nenhum componente com cor hardcoded ilegivel no escuro.

- [ ] **Step 1: Definir a paleta escura nos tokens** (contraste AA para texto normal; conferir com os valores da identidade visual)

- [ ] **Step 2: Auditar tela a tela** — login, shell (sidebar/header), fila, detalhe do ticket (timeline, chat, anexos), criacao, cadastros (todas), dashboard (graficos legiveis nos dois temas), relatorios, galeria (lightbox), plataforma, preferencias, membros. Corrigir componente a componente; commits parciais por grupo de telas sao bem-vindos.

- [ ] **Step 3: Verificacoes e commit (final do passe)**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Aplica o tema escuro em todas as telas"
```

---

### Task 16: Frontend — pagina de membros (admin)

**Files:**
- Create: `frontend/src/pages/membros/MembrosPage.tsx`
- Create: `frontend/src/lib/members.ts`
- Modify: `frontend/src/main.tsx` (rota `/membros` sob `RequireTenant`), `frontend/src/components/layout/Sidebar.tsx` (item "Membros" visivel so para `session.role === "admin"`)
- Test: build/lint + e2e (Task 18)

**Interfaces:**
- Consumes: endpoints da Task 8, padrao de CRUD das paginas de cadastros (ler `ClientesPage.tsx` e seguir o padrao de tabela + dialog), `useAuth` (role).
- Produces: `lib/members.ts` (`MemberDetail`, `listMembers()`, `createMember(input)`, `updateMember(userId, patch)`, `resetMemberPassword(userId, password)`); pagina com tabela (nome, email, papel, status do vinculo), dialog de criacao (email primeiro — se ja existir no sistema o backend vincula; campos nome/senha para usuario novo), acoes de papel/ativar/desativar/senha com confirmacao. O proprio usuario aparece sem acoes (salvaguarda do backend refletida na UI).

- [ ] **Step 1: Implementar conforme Interfaces** (com frontend-design)

- [ ] **Step 2: Verificar no app real** (criar membro no tenant e2e e logar com ele)

- [ ] **Step 3: Verificacoes e commit**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Adiciona pagina de membros do tenant para o admin"
```

---

### Task 17: Frontend — reatribuicao na edicao + aria-live da pill

**Files:**
- Modify: o form de edicao do ticket — localizar o consumidor de `updateTicket` (`frontend/src/lib/tickets.ts:238`) e adicionar select de atendente (opcoes de `GET /api/membros`, visivel/habilitado so quando `session.role` e admin/supervisor), enviando `attendant_user_id`
- Modify: `frontend/src/lib/tickets.ts` (campo no payload de update)
- Modify: a pill do filtro de cliente na fila (`TicketsListPage.tsx` / componente da pill — commits recentes `acb4352`/`a2a3467`): envolver o container da pill em `aria-live="polite"`
- Test: build/lint + e2e existente (`07-fila-repaginada.spec.ts` continua verde)

- [ ] **Step 1: Implementar** (select reusa o padrao do `SupervisorSelect.tsx`)

- [ ] **Step 2: Verificar no app real** (reatribuir como admin gera notificacao para o novo atendente — fecha o circuito com a Task 12)

- [ ] **Step 3: Verificacoes e commit**

```bash
pnpm build && pnpm lint
git add src
git commit -m "Adiciona reatribuicao de atendente na edicao e aria-live na pill de cliente"
```

---

### Task 18: E2E Playwright dos fluxos novos

**Files:**
- Create: `frontend/e2e/08-notificacoes.spec.ts`
- Create: `frontend/e2e/09-busca-global.spec.ts`
- Create: `frontend/e2e/10-preferencias-e-membros.spec.ts`
- Modify: `frontend/e2e/helpers.ts` (o que faltar de helper de segundo contexto/login)

**Interfaces:**
- Consumes: padrao de dois contextos de `04-comentarios-e-naolido.spec.ts` (ler antes), helpers de login existentes, tenant e2e.
- Produces:
  - `08`: A (admin) comenta em ticket atribuido a B; contexto de B ve badge subir sem reload (SSE), abre dropdown, ve o titulo, clica e cai no ticket; "marcar todas" zera o badge.
  - `09`: Ctrl+K abre a palette; busca por documento de cliente conhecido do seed e2e acha o cliente; busca por numero de ticket navega ao detalhe; termo de 1 char nao consulta.
  - `10`: preferencias — trocar para "escuro" poe classe `dark` no `html` e persiste apos reload; membros — admin cria membro novo, faz logout, loga com o membro criado; supervisor nao ve a pagina de membros.

- [ ] **Step 1: Escrever os specs e rodar**

```bash
docker compose restart backend worker
cd frontend && E2E_PORT=5188 pnpm exec playwright test e2e/08-notificacoes.spec.ts e2e/09-busca-global.spec.ts e2e/10-preferencias-e-membros.spec.ts
```
(env var na mesma linha; nunca em background). Expected: PASS. Rodar tambem a suite e2e inteira ao final.

- [ ] **Step 2: Commit**

```bash
pnpm build && pnpm lint
git add e2e
git commit -m "Adiciona e2e de notificacoes, busca global, preferencias e membros"
```

---

### Task 19: Verificacao final, merge e FlowHub

- [ ] **Step 1: Suites completas**

Backend: `ruff check . && ruff format --check . && mypy && ./.venv/Scripts/python.exe -m pytest -q`. Frontend: `pnpm tsc --noEmit && pnpm lint && pnpm build` e a suite e2e completa com `E2E_PORT=5188`.

- [ ] **Step 2: Finalizar a branch**

Usar o skill `superpowers:finishing-a-development-branch` (merge em main + push, como nas fases anteriores).

- [ ] **Step 3: FlowHub e memoria**

Marcar a task da Fase 4 e subtasks como concluidas no board (curl, uma chamada por vez, conferindo cada resposta). Atualizar a memoria de checkpoint do projeto.
