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

## Documentação

- `docs/PRD.md` — fonte de verdade de requisitos, domínio e fases do produto.
- `docs/superpowers/specs/2026-07-27-sac-b2pro-fase-0-design.md` — design técnico da Fase 0.
- `docs/superpowers/plans/2026-07-27-fase-0-fundacao.md` — plano de implementação da Fase 0.
- `docs/identidade-visual.md` — identidade visual do frontend.
- `CLAUDE.md` — decisões de arquitetura e regras obrigatórias do projeto.
