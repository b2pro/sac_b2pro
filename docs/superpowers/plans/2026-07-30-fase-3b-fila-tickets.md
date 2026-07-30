# Fase 3B (Fila de tickets repaginada) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repaginar a fila de tickets conforme o mockup aprovado — filtros no header, chips de filtro rapido com contagem e lista de cards — junto com os filtros e o endpoint de contadores que o backend ainda nao tem.

**Architecture:** Tres filtros novos no `GET /api/tickets` (`atendente_id`, `q`, `unread`) resolvidos no `SqlTicketRepository`, mais um `GET /api/tickets/contadores` somente leitura; no front, `TicketsListPage` reescrita reusando os componentes compartilhados da Fase 3.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL, pytest (integracao contra Postgres real), React + TypeScript + Vite, Playwright.

**Spec:** `docs/superpowers/specs/2026-07-30-sac-b2pro-fase-3b-fila-tickets-design.md`
**Mockup normativo:** `docs/frontendmockups/Tickets.dc.html` (estados `padrao`, `carregando`, `vazio` no painel de Tweaks)

**Pre-requisito:** a Fase 3 precisa estar concluida — este plano reusa `Pagination`, `EmptyState` (`src/components/reporting/`), o `SlaBadge` compacto e os filtros da lista na URL, todos entregues lá.

## Global Constraints

- PROIBIDO usar emojis em codigo, comentarios, commits, UI e documentacao.
- Clean Architecture: dominio sem framework; ports na application; SQL na infrastructure; routers na interface.
- TDD no backend: escrever o teste, ver falhar, implementar o minimo, ver passar, commitar.
- Antes de CADA commit de backend (em `backend/`): `ruff check .`, `ruff format --check .`, `mypy` (**sem path** — `mypy .` da erro falso em `migrations/tenant/env.py`), `pytest`. Integracao exige `docker compose up -d` na raiz (Postgres em localhost:5432, MinIO em localhost:9000).
- Antes de CADA commit de frontend (em `frontend/`): `pnpm build` e `pnpm lint`. Gerenciador e **pnpm**.
- Nunca rodar verificacoes em background — elas ficam orfas; sempre em foreground.
- Copy da UI em portugues sem acentos; identificadores de codigo em ingles; rotas em portugues.
- **Numero do ticket continua `#489`** (decisao do usuario). O formato `#2026-0489` que aparece no mockup NAO e adotado.
- **O botao "Novo ticket" permanece** no header (o mockup o omite; a omissao nao e adotada).
- **A ordenacao permanece**, como select compacto no header.

---

### Task 1: Filtro por atendente e busca livre no GET /tickets

**Files:**
- Modify: `backend/src/sac/application/ports_tickets.py`
- Modify: `backend/src/sac/infrastructure/repositories_tickets.py`
- Modify: `backend/src/sac/interface/routers/tickets.py`
- Test: `backend/tests/integration/test_repositories_tickets.py`, `backend/tests/integration/test_tickets_api.py`

**Interfaces:**
- Consumes: `TicketFilters` (ja tem `attendant_user_id`, ja aplicado em `_base_stmt`), `SqlTicketRepository._base_stmt`, `ProductModel`/`TicketItemModel`/`CustomerModel` de `models_tenant.py`.
- Produces: `TicketFilters` ganha `search: str | None = None`; `GET /api/tickets` ganha os query params `atendente_id: UUID | None` e `q: str | None`.

- [ ] **Step 1: Escrever os testes que falham**

Em `test_repositories_tickets.py`, seguir o estilo dos testes de filtro que ja existem no arquivo (ler primeiro) e cobrir:

```python
async def test_filtra_por_atendente(...):
    # dois tickets de atendentes diferentes; filtrar por um devolve so o dele

async def test_busca_por_prefixo_do_numero(...):
    # tickets numerados; TicketFilters(search="48") acha #48 e #489, nao acha #7

async def test_busca_por_nome_do_cliente(...):
    # TicketFilters(search="mari") acha o ticket de "Mariana Alves" (case-insensitive)

async def test_busca_por_nome_do_produto(...):
    # ticket com item de produto "Alicate de cuticula"; search="alicate" acha; search="esmalte" nao

async def test_busca_nao_casa_o_que_nao_deve(...):
    # search com termo inexistente devolve lista vazia e total zero
```

Em `test_tickets_api.py`, um teste de rota conferindo que `GET /api/tickets?q=<termo>` e `?atendente_id=<id>` filtram, e que `q` em branco e tratado como ausente.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_tickets.py -v -k "atendente or busca"`
Expected: FAIL — `TicketFilters` nao aceita `search`.

- [ ] **Step 3: Implementar**

`ports_tickets.py`: acrescentar `search: str | None = None` ao `TicketFilters`.

`repositories_tickets.py`, dentro de `_base_stmt`, depois dos filtros existentes:

```python
        if filters.search:
            termo = filters.search.strip().lstrip("#")
            if termo:
                alvos = [
                    TicketModel.customer_id.in_(
                        select(CustomerModel.id).where(CustomerModel.name.ilike(f"%{termo}%"))
                    ),
                    exists(
                        select(TicketItemModel.id)
                        .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
                        .where(
                            TicketItemModel.ticket_id == TicketModel.id,
                            ProductModel.name.ilike(f"%{termo}%"),
                        )
                    ),
                ]
                if termo.isdigit():
                    alvos.append(cast(TicketModel.number, String).like(f"{termo}%"))
                stmt = stmt.where(or_(*alvos))
```

Importar `cast` e `String` de `sqlalchemy` (`or_` e `exists` ja estao importados). Nota: a busca por numero e por **prefixo** (`like "48%"`), nao por trecho — `"48"` acha `#48` e `#489`, e nao `#148`, que confundiria mais do que ajudaria.

`routers/tickets.py`, em `list_tickets`: acrescentar `atendente_id: UUID | None = None` e `q: str | None = None` a assinatura e passar `attendant_user_id=atendente_id, search=q` ao construir `TicketFilters`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_tickets.py tests/integration/test_tickets_api.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && python -m pytest -q
git add src/sac tests/integration
git commit -m "Adiciona filtro por atendente e busca livre na lista de tickets"
```

---

### Task 2: Filtro de nao lidos

**Files:**
- Modify: `backend/src/sac/application/ports_tickets.py`
- Modify: `backend/src/sac/infrastructure/repositories_tickets.py`
- Modify: `backend/src/sac/interface/routers/tickets.py`
- Test: `backend/tests/integration/test_repositories_tickets.py`

**Interfaces:**
- Consumes: `TicketReadModel` de `models_tenant.py`; `SqlTicketRepository._base_stmt` (que hoje recebe apenas `filters`) e `list(..., unread_for: UUID)`.
- Produces: `TicketFilters` ganha `unread: bool = False`; `GET /api/tickets` ganha `unread: bool = False`.

Atencao: a condicao de nao lido depende do **usuario**, que hoje chega em `list()` como `unread_for` e nao esta em `TicketFilters`. Passar `unread_for` para `_base_stmt` (mudar a assinatura para `_base_stmt(self, filters, unread_for)`) e ajustar as duas chamadas dentro de `list()`. Nao inventar um `user_id` dentro de `TicketFilters` — o filtro e "nao lido por quem esta olhando", nao "nao lido por um id qualquer".

- [ ] **Step 1: Escrever os testes que falham**

```python
async def test_filtra_nao_lidos(...):
    # tres tickets para o mesmo usuario:
    #  - nunca lido (sem linha em ticket_reads)        -> entra
    #  - lido antes da ultima atividade                -> entra
    #  - lido depois da ultima atividade               -> fica fora
    # conferir tambem que o total reflete o filtro, nao a lista inteira

async def test_nao_lidos_e_por_usuario(...):
    # o mesmo ticket lido pelo usuario A e nao lido pelo usuario B:
    # filtrar como A devolve vazio; como B devolve o ticket
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_tickets.py -v -k "nao_lido"`
Expected: FAIL — `TicketFilters` nao aceita `unread`.

- [ ] **Step 3: Implementar**

`ports_tickets.py`: `unread: bool = False` em `TicketFilters`.

`repositories_tickets.py`: `_base_stmt(self, filters: TicketFilters, unread_for: UUID)` e, ao fim dos filtros:

```python
        if filters.unread:
            leitura = select(TicketReadModel.last_read_at).where(
                TicketReadModel.ticket_id == TicketModel.id,
                TicketReadModel.user_id == unread_for,
            )
            stmt = stmt.where(
                or_(
                    ~exists(leitura),
                    leitura.scalar_subquery() < TicketModel.last_activity_at,
                )
            )
```

Ajustar as duas chamadas de `_base_stmt` em `list()` para repassar `unread_for`.

`routers/tickets.py`: `unread: bool = False` na assinatura de `list_tickets`, repassado ao `TicketFilters`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_repositories_tickets.py -v`
Expected: PASS (os testes de lista existentes tambem — a mudanca de assinatura de `_base_stmt` e interna).

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && python -m pytest -q
git add src/sac tests/integration
git commit -m "Adiciona filtro de tickets nao lidos por usuario"
```

---

### Task 3: Endpoint de contadores da fila

**Files:**
- Modify: `backend/src/sac/application/ports_tickets.py`
- Modify: `backend/src/sac/infrastructure/repositories_tickets.py`
- Modify: `backend/src/sac/application/use_cases/tickets_queries.py`
- Modify: `backend/src/sac/interface/routers/tickets.py`, `backend/src/sac/interface/schemas.py`
- Test: `backend/tests/integration/test_tickets_api.py`

**Interfaces:**
- Consumes: `TicketFilters`, `_base_stmt` (com `unread` e `search` das tasks 1-2), `CLOSED_STATUSES` de `domain/tickets.py`, `TicketActor`, e a regra de escopo por papel que `ListTicketsUseCase` ja aplica (ler como ela restringe atendente aos proprios tickets e reusar exatamente a mesma regra).
- Produces:

```python
# ports_tickets.py
@dataclass(frozen=True)
class TicketCounters:
    todos: int
    ativos: int
    abertos: int
    aguardando_analise: int
    atrasados: int
    nao_lidos: int
    meus: int

# TicketRepository (Protocol)
    async def counters(self, base: TicketFilters, unread_for: UUID, now: datetime) -> TicketCounters: ...

# use_cases/tickets_queries.py
class GetTicketCountersUseCase:
    def __init__(self, tickets: TicketRepository) -> None: ...
    async def execute(self, actor: TicketActor, now: datetime) -> TicketCounters: ...

# rota
GET /api/tickets/contadores -> TicketCountersOut  (mesmos sete campos)
```

**Declarar `/contadores` ANTES de `/{ticket_id}` no router**, senao a rota dinamica engole o caminho.

- [ ] **Step 1: Escrever o teste que falha**

Em `test_tickets_api.py`, reusando os helpers de seed do arquivo:

```python
async def test_contadores_da_fila(...):
    # cenario: um aberto nao lido, um aguardando analise, um finalizado,
    # um atrasado (due_at no passado e nao encerrado), um de outro atendente,
    # e um excluido (soft delete)
    res = await client.get("/api/tickets/contadores", headers=h_admin)
    assert res.status_code == 200
    body = res.json()
    assert body["todos"] == 5          # excluido fora
    assert body["ativos"] == 4         # finalizado fora
    assert body["abertos"] == 2
    assert body["aguardando_analise"] == 1
    assert body["atrasados"] == 1
    assert body["nao_lidos"] == 5      # admin nunca abriu nenhum
    assert body["meus"] == 4           # os criados por ele

async def test_contadores_de_atendente_veem_so_os_proprios(...):
    # atendente com um ticket proprio e outro de terceiro: todos == 1

async def test_contadores_exigem_autenticacao(...):
    # sem token -> 401
```

Ajustar os numeros do cenario ao que o seed realmente cria — as assercoes precisam refletir o cenario montado, nao o inverso.

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_tickets_api.py -v -k contadores`
Expected: FAIL com 404.

- [ ] **Step 3: Implementar**

`repositories_tickets.py`, em `SqlTicketRepository`:

```python
    async def counters(
        self, base: TicketFilters, unread_for: UUID, now: datetime
    ) -> TicketCounters:
        async def conta(filtros: TicketFilters) -> int:
            stmt = self._base_stmt(filtros, unread_for)
            total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
            return int(total or 0)

        fechados = [str(s) for s in CLOSED_STATUSES]
        ativos_stmt = self._base_stmt(base, unread_for).where(TicketModel.status.not_in(fechados))
        ativos = await self._session.scalar(
            select(func.count()).select_from(ativos_stmt.subquery())
        )
        return TicketCounters(
            todos=await conta(base),
            ativos=int(ativos or 0),
            abertos=await conta(replace(base, status=TicketStatus.ABERTO)),
            aguardando_analise=await conta(replace(base, status=TicketStatus.AGUARDANDO_ANALISE)),
            atrasados=await conta(replace(base, overdue=True)),
            nao_lidos=await conta(replace(base, unread=True)),
            meus=await conta(replace(base, attendant_user_id=unread_for)),
        )
```

`replace` de `dataclasses`. `base` chega do use case ja com o escopo do papel aplicado (para atendente, `attendant_user_id` = ele mesmo), o que faz `todos` e os demais ja respeitarem a visao — e nesse caso `meus` coincide com `todos`, que e o correto.

`use_cases/tickets_queries.py`: `GetTicketCountersUseCase` monta o `TicketFilters` base com a mesma regra de escopo de `ListTicketsUseCase` e chama `counters`.

`schemas.py`: `TicketCountersOut` (BaseModel com os sete inteiros) e uma funcao `ticket_counters_out`.

`routers/tickets.py`: rota `GET /contadores` com a dependency `_read`, declarada **antes** de `GET /{ticket_id}`.

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/test_tickets_api.py -v`
Expected: PASS

- [ ] **Step 5: Verificacoes e commit**

```bash
ruff check . && ruff format --check . && mypy && python -m pytest -q
git add src/sac tests/integration
git commit -m "Adiciona endpoint de contadores da fila de tickets"
```

---

### Task 4: Front — fila de tickets repaginada

**Mockup normativo:** `docs/frontendmockups/Tickets.dc.html`. **Invocar o skill `frontend-design` antes de escrever JSX** e ler `docs/identidade-visual.md`. Usar a mesma tabela de traducao de tokens do plano da Fase 3 (secao "Frontend: fonte de verdade visual").

**Files:**
- Create: `frontend/src/components/tickets/QuickFilterChips.tsx`
- Create: `frontend/src/components/tickets/TicketQueueCard.tsx`
- Rewrite: `frontend/src/pages/tickets/TicketsListPage.tsx`
- Modify: `frontend/src/lib/tickets.ts`

**Interfaces:**
- Consumes: `Pagination` e `EmptyState` de `@/components/reporting/` (Fase 3); `StatusBadge`, `PriorityBadge`, `SlaBadge`, `STATUS_ACCENTS` de `@/components/tickets/badges`; `useDebounce` de `@/lib/useDebounce`; membros do tenant de `@/lib/members`; `listTickets` de `@/lib/tickets`.
- Produces:

```typescript
// lib/tickets.ts
export type TicketCounters = {
  todos: number; ativos: number; abertos: number
  aguardando_analise: number; atrasados: number; nao_lidos: number; meus: number
}
export const getTicketCounters: () => Promise<TicketCounters>
// ListTicketsParams ganha: q?: string; atendenteId?: string; unread?: boolean
```

```tsx
// QuickFilterChips.tsx
export type QuickFilterKey = "todos" | "abertos" | "aguardando_analise" | "atrasados" | "nao_lidos" | "meus"
export function QuickFilterChips(props: {
  counters: TicketCounters | undefined
  active: QuickFilterKey
  onSelect: (key: QuickFilterKey) => void
}): JSX.Element

// TicketQueueCard.tsx
export function TicketQueueCard(props: { item: TicketListItem }): JSX.Element
```

- [ ] **Step 1: Client**

Em `lib/tickets.ts`: acrescentar `q`, `atendenteId` e `unread` a `ListTicketsParams` e ao mapeamento de `listTickets` (`q`, `atendente_id`, `unread`); adicionar `getTicketCounters` batendo em `/tickets/contadores`.

- [ ] **Step 2: `QuickFilterChips`**

`flex flex-wrap gap-1.5 mb-5`. Um `<button>` por chip com `h-7 px-2.5 border rounded-md text-xs whitespace-nowrap hover:border-foreground`, contendo o rotulo e a contagem em `font-mono text-[11px]`. Estados:

- ativo: `bg-accent-foreground text-background border-accent-foreground font-semibold`, contagem em `text-border`;
- "Atrasados" inativo: `text-primary font-semibold` e contagem tambem em `text-primary`;
- demais inativos: `bg-card border-border text-foreground`, contagem em `text-muted-foreground`.

Rotulos e ordem: Todos, Abertos, Aguardando analise, Atrasados, Nao lidos, Meus tickets. Enquanto `counters` for `undefined`, renderizar os chips sem a contagem (nao um spinner — o chip ja e clicavel). `aria-pressed` no chip ativo.

- [ ] **Step 3: `TicketQueueCard`**

`<Link>` para `/tickets/{id}` com `block bg-card border border-border border-l-[3px] rounded-md px-4 py-3 hover:border-foreground` e a cor da borda esquerda de `STATUS_ACCENTS[status]`. Duas linhas:

1. `flex flex-wrap items-center gap-2.5`: bolinha de 8px (`rounded-full`, `bg-primary` quando `unread`, senao invisivel mas ocupando espaco, com `title="Atividade nao lida"` e `aria-label` quando nao lido); `#numero` em `font-mono font-semibold text-[13.5px] text-primary`; nome do cliente em `text-[13.5px] font-semibold text-accent-foreground`; `<StatusBadge>`; `<PriorityBadge>`; e, com `ml-auto`, `<SlaBadge>`.
2. `flex flex-wrap items-center gap-2.5 mt-1.5 text-[12.5px] text-muted-foreground`: produto (`truncate max-w-[340px]` + `title`), separador `·`, contagem de itens ("1 item" / "N itens"), separador, atendente, e com `ml-auto` em `font-mono text-[11.5px]` o texto "aberto DD/MM · atividade DD/MM HH:MM" (usar os helpers de data de `@/lib/format`).

Cliente sem nome cai para "Cliente nao informado" em `text-muted-foreground`; produto ausente, para "Sem itens".

- [ ] **Step 4: `TicketsListPage` reescrita**

- Header: `flex flex-wrap items-end justify-between gap-4 mb-5`. Esquerda: `<h1>` "Tickets" (`text-xl font-bold text-accent-foreground`) e subtitulo "Fila de trocas e defeitos — `N` tickets ativos" (numero em `font-mono`, vindo de `counters.ativos`). Direita, `flex flex-wrap gap-2 items-center`: campo de busca de 250px com icone `Search` a esquerda e placeholder "Buscar por no, cliente ou produto" (estado local + `useDebounce` de 400ms escrevendo `q` na URL), selects de Status / Marca / Atendente, select compacto de ordenacao (as quatro opcoes atuais de `SORT_OPTIONS` mais o toggle de `order`, preservados) e o botao "Novo ticket" (`Button` primario, link para `/tickets/novo`).
- Filtros na URL, como a Fase 3 deixou: `q`, `status`, `brand_id`, `atendente_id`, `unread`, `overdue`, `page`, `sort`, `order`. Reusar o helper `setParam`.
- Chips: `QuickFilterChips` mapeando cada chave para o recorte na URL — `todos` limpa `status`/`overdue`/`unread`/`atendente_id`; `abertos` seta `status=aberto`; `aguardando_analise` seta `status=aguardando_analise`; `atrasados` seta `overdue=1`; `nao_lidos` seta `unread=1`; `meus` seta `atendente_id` = usuario do token (`useAuth`). O chip ativo e derivado da URL (nao de estado proprio).
- Dados: `useQuery` da lista (chave com todos os params) e `useQuery` dos contadores (chave `["ticket-contadores"]`).
- Corpo: `flex flex-col gap-2.5` com um `TicketQueueCard` por item, e `Pagination` abaixo.
- Carregando: oito blocos de 76px (`bg-muted rounded-md animate-pulse`).
- Vazio: `EmptyState` "Nenhum ticket aberto para este filtro" / "Ajuste a busca ou os filtros acima."
- O que sai: card de filtros, tabela, filtro de prioridade e campo de pedido dedicados (o pedido fica alcancavel pela busca livre). O menu kebab por linha nao existe hoje e continua fora.

- [ ] **Step 5: Verificar**

Run (em `frontend/`): `pnpm build && pnpm lint`
Expected: sem erros.

- [ ] **Step 6: Conferencia visual**

Com backend e `pnpm dev` de pe, comparar com `Tickets.dc.html` nos tres estados. Checar: busca por numero e por nome; cada chip trocando o recorte e a contagem batendo com o resultado; ordenacao; bolinha de nao lido; Tab percorrendo chips e cards com foco visivel; deep link do dashboard (`/tickets?status=aberto`) chegando com o chip "Abertos" ativo.

- [ ] **Step 7: Commit**

```bash
git add src/lib/tickets.ts src/components/tickets src/pages/tickets/TicketsListPage.tsx
git commit -m "Repagina a fila de tickets com filtros no header e cards"
```

---

### Task 5: e2e e documentacao

**Files:**
- Modify: `frontend/e2e/01-lista-e-papeis.spec.ts` (e os demais specs que dependem da tabela antiga)
- Create/extend: `frontend/e2e/07-fila-repaginada.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Ajustar os specs existentes**

Rodar `pnpm e2e` e ver o que quebra. Os specs 01 a 05 esperam a tabela (`getByRole("row")`, rotulos "Status"/"Marca"/"Cliente"/"Produto"/"Pedido"/"Prioridade"/"Ordenar por" do card de filtros, `#filtro-ordenar`). Atualizar os **seletores** para a estrutura nova (cards como link, filtros no header, chips), preservando o que cada teste verifica. Nao enfraquecer assercao: se um teste checava que a linha inteira navega, o equivalente e o card inteiro navegar.

- [ ] **Step 2: Spec novo da fila**

```typescript
import { expect, test } from "@playwright/test"

import { apiFullTicket, login } from "./helpers"

test.describe("Fila de tickets repaginada", () => {
  test("busca por numero e chips filtram a fila", async ({ page, request }) => {
    const ticket = await apiFullTicket(request, "admin")
    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()

    const card = page.getByRole("link").filter({ hasText: `#${ticket.number}` }).first()
    await expect(card).toBeVisible()

    await page.getByPlaceholder("Buscar por no, cliente ou produto").fill(String(ticket.number))
    await expect(card).toBeVisible()

    await page.getByRole("button", { name: /Atrasados/ }).click()
    await expect(page).toHaveURL(/overdue=1/)

    await page.getByRole("button", { name: /Todos/ }).click()
    await expect(card).toBeVisible()
    await card.click()
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`))
  })

  test("contadores aparecem no subtitulo e nos chips", async ({ page, request }) => {
    await apiFullTicket(request, "admin")
    await login(page, request, "admin")
    await page.getByRole("link", { name: "Tickets" }).click()
    await expect(page.getByText(/tickets ativos/)).toBeVisible()
    await expect(page.getByRole("button", { name: /Nao lidos/ })).toBeVisible()
  })
})
```

Ajustar rotulos e seletores ao que a UI renderizar.

- [ ] **Step 3: Rodar tudo**

Run: `pnpm e2e`
Expected: verde.

- [ ] **Step 4: README**

Acrescentar a Fase 3B em "Fases entregues", descrevendo a fila repaginada (filtros no header com busca livre, chips com contagem, cards de duas linhas, ordenacao preservada) e os filtros/endpoint novos do backend (`atendente_id`, `q`, `unread`, `GET /api/tickets/contadores`). Citar o mockup e a spec.

- [ ] **Step 5: Commit**

```bash
git add e2e ../README.md
git commit -m "Ajusta e2e para a fila repaginada e documenta a Fase 3B"
```

---

### Task 6: Verificacao final da fase

- [ ] **Step 1: Backend**

Run (em `backend/`): `ruff check . && ruff format --check . && mypy && python -m pytest`
Expected: tudo verde.

- [ ] **Step 2: Frontend**

Run (em `frontend/`): `pnpm build && pnpm lint && pnpm e2e`
Expected: tudo verde.

- [ ] **Step 3: Passeio manual**

Login, fila: buscar por numero, por cliente e por produto; percorrer os seis chips conferindo contagem contra o resultado; ordenar por vencimento; abrir um card; voltar e conferir que o filtro sobreviveu; conferir o deep link vindo do dashboard.
