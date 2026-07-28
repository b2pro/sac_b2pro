# SAC-B2PRO

Plataforma de SAC para automatizar o controle de trocas, defeitos e garantias hoje feito em planilhas (marcas KODI e STALEKS), com backend limpo e testado e front que evolui o layout do sistema legado.

## Stack

- **Backend**: Python 3.12+, FastAPI, Uvicorn, SQLAlchemy (async), Alembic, PostgreSQL. Clean Architecture (domain / application / infrastructure / interface). Multi-tenant por schema, autenticação por email + senha + slug do tenant (JWT).
- **Frontend**: React + TypeScript + Vite.

## Pré-requisitos

- Docker (para o PostgreSQL do `docker-compose.yml`)
- [uv](https://docs.astral.sh/uv/) (gerenciador de ambiente/pacotes do backend)
- Node.js 20+
- pnpm

## Quickstart

### Um comando (recomendado para dev)

```powershell
./dev.ps1
```

O script builda e sobe o Postgres e o backend em containers (migrations e seed rodam automaticamente; hot-reload ativo via volume montado) e depois inicia o frontend com `pnpm dev` no terminal atual. Super admin de dev: `admin@b2pro.com` / `admin-dev-12345` (deixe o slug vazio no login). Para parar os containers depois: `docker compose down`. As credenciais podem ser sobrescritas pelas variáveis de ambiente `SAC_SEED_ADMIN_EMAIL` e `SAC_SEED_ADMIN_PASSWORD` antes de rodar o script.

### Passo a passo manual

Suba o banco de dados:

```bash
docker compose up -d db
```

Backend:

```bash
cd backend
cp .env.example .env   # preencher SAC_SEED_ADMIN_EMAIL e SAC_SEED_ADMIN_PASSWORD
uv run python -m sac.infrastructure.migrate all
uv run python -m sac.infrastructure.seed
uv run uvicorn sac.main:app --reload
```

Frontend (em outro terminal):

```bash
cd frontend
pnpm install
pnpm dev
```

O backend sobe em `http://localhost:8000` (docs em `/docs`) e o frontend em `http://localhost:5173`.

## Verificações locais

Não há CI: as verificações abaixo devem passar localmente antes de cada commit.

Backend (em `backend/`):

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

Frontend (em `frontend/`):

```bash
pnpm lint
pnpm build
```

## Fases entregues

- **Fase 0 — Fundação**: monorepo, Clean Architecture, Alembic multi-schema, autenticação (login com slug + JWT), sistema de módulos por tenant, painel mínimo da plataforma.
- **Fase 1 — Cadastros**: marcas, clientes, produtos, defeitos, soluções e canais, com CRUDs no front e design system inicial.
- **Fase 2A — Tickets (core)**: núcleo do fluxo de trocas/defeitos/garantia.
  - **Domínio**: máquina de estados explícita com um use case por transição (9 transições — enviar para análise, aprovar, declinar, aguardar cliente, retomar, produto recebido, finalizar, cancelar, reabrir), cada uma com permissão, guards e marcos próprios.
  - **Numeração**: sequence nativa por schema de tenant, sem race condition entre criações concorrentes.
  - **Itens**: `TicketItem` (produto + defeito + quantidade) como fonte única de verdade — nenhum dado de produto/defeito duplicado no ticket.
  - **SLA**: `sla_policies` por tenant (semeada com urgente/alta/média/baixa e alerta antes do vencimento), prazo calculado na criação e recalculado na troca de prioridade.
  - **Colaboração**: comentários internos com reply (bloqueados em ticket encerrado), timeline de auditoria (transições, itens, reversos, garantia, edições) e lido/não lido por usuário.
  - **Logística**: códigos reversos (registrar/excluir, com retorno automático de status) e pedido de garantia (código + rastreio).
  - **API**: rotas sob `/api/tickets` (CRUD, itens, transições, reversos, garantia, comentários, marcar não lido).
  - **Frontend**: lista com filtros e debounce, indicador de não lido e paginação; detalhe em duas colunas (2/3 dados + chat + timeline, 1/3 ação primária contextual por estado com trilha de status); criação com lookup de cliente por documento/CEP e itens repetíveis.
  - Anexos (Wasabi S3) ficam para a Fase 2B — o detalhe já reserva o espaço com um card placeholder desabilitado.

## Documentação

- `docs/PRD.md` — fonte de verdade de requisitos, domínio e fases do produto.
- `docs/superpowers/specs/2026-07-27-sac-b2pro-fase-0-design.md` — design técnico da Fase 0.
- `docs/superpowers/plans/2026-07-27-fase-0-fundacao.md` — plano de implementação da Fase 0.
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-1-design.md` — design técnico da Fase 1 (cadastros).
- `docs/superpowers/plans/2026-07-28-fase-1-cadastros.md` — plano de implementação da Fase 1.
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-2a-tickets-design.md` — design técnico da Fase 2A (tickets).
- `docs/superpowers/plans/2026-07-28-fase-2a-tickets.md` — plano de implementação da Fase 2A.
- `docs/identidade-visual.md` — identidade visual do frontend.
- `CLAUDE.md` — decisões de arquitetura e regras obrigatórias do projeto.
