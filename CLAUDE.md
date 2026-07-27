# SAC-B2PRO

Projeto novo (greenfield). Este arquivo registra as decisões de arquitetura e stack.

Sistema de SAC para automatizar o controle de trocas e defeitos hoje feito em planilhas (KODI e STALEKS, na raiz de `work2/`). O projeto legado `../SAC-Tickets` (Laravel, vibe-codado) serve de referência funcional e de layout — a disposição de telas e menus deve se inspirar nele, sempre melhorando e profissionalizando.

**Documento principal do produto: `docs/PRD.md`** — fonte de verdade de requisitos, domínio e fases. Apoio: `docs/planilhas.md` (planilhas a automatizar), `docs/legado-funcionamento.md` (regras do legado), `docs/legado-ui.md` (layout do legado), `docs/proposta-alto-nivel.md` (proposta consolidada no PRD), `docs/armazenamento-anexos.md` (anexos no Wasabi S3).

## Decisões de produto (2026-07-27)

- KODI e STALEKS operam em **um único tenant**; a marca é cadastro + campo do ticket. A arquitetura multi-schema permanece para futuras organizações.
- Módulo Eventos fica de fora por agora, mas o **sistema de módulos por tenant** (feature flags) é implementado desde o início.
- SAC **apenas interno** — sem notificação ao cliente final por enquanto.
- Anexos (imagens e PDFs) no **Wasabi S3**: upload direto via presigned URL (chave gerada no servidor, TTL curto, bucket privado), PDFs salvos como estão, imagens comprimidas acima do limite, previews gerados por job limitado (Wasabi não tem thumbnail nativo). Ver `docs/armazenamento-anexos.md`.

## Regras obrigatórias

- **PROIBIDO usar emojis** — em código, comentários, commits, UI, documentação e respostas.
- **Clean Architecture** no backend: domínio independente de framework; camadas domain / application (use cases) / infrastructure (ORM, FastAPI) / interface (routers). Dependências apontam para dentro.
- **TDD no backend**: escrever teste antes da implementação (red-green-refactor). Pytest.
- Front pode ser testado com **Playwright** quando necessário.
- **Sem CI**: verificações rodam localmente antes de cada commit — backend `ruff check`, `ruff format --check`, `mypy`, `pytest`; frontend `tsc --noEmit`, `eslint`, `build` quando relevante.
- **Todo trabalho de frontend usa o skill `frontend-design`** e segue a identidade visual de `docs/identidade-visual.md`.

## Stack

### Backend
- **Python** com **FastAPI**
- Servidor: **Uvicorn**
- ORM: **SQLAlchemy** (async) com **Alembic** para migrations
- Banco de dados: **PostgreSQL**
- Seguir boas práticas: tipagem (type hints), Pydantic para schemas de request/response, injeção de dependências do FastAPI, separação em camadas (routers / services / repositories / models)

### Frontend
- **React + TypeScript + Vite**

## Arquitetura Multi-Tenant

- Multi-tenancy por **schema separado** no PostgreSQL (um schema por tenant)
- **Usuários são globais** (ficam no schema público/compartilhado), relacionados aos tenants via tabela de associação (um usuário pode pertencer a um ou mais tenants)
- Tabelas globais (schema `public`): `users`, `tenants`, `user_tenants` (associação)
- Tabelas de negócio ficam no schema de cada tenant

## Autenticação

- Login com **email + senha + slug do tenant**
- Fluxo: o slug identifica o tenant → valida se o usuário (global) tem vínculo com aquele tenant → autentica com email+senha
- Senhas com hash forte (bcrypt/argon2)
- JWT contendo a identificação do usuário e do tenant ativo

## Convenções

- Backend e frontend em pastas separadas (ex.: `backend/` e `frontend/`)
- Variáveis de ambiente via `.env` (nunca commitar segredos)
- Migrations do Alembic devem contemplar a criação/atualização de schemas por tenant
