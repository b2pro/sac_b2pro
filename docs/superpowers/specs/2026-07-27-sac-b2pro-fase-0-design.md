# Design — SAC-B2PRO Fase 0 (Fundação)

Data: 2026-07-27. Fonte de requisitos: `docs/PRD.md` (prevalece em divergência). Este documento fecha as decisões de implementação da Fase 0 e a arquitetura geral que as demais fases seguirão.

## Objetivo da Fase 0

Entregar a fundação do sistema: monorepo, infraestrutura local (Postgres via docker-compose), esqueleto Clean Architecture, migrations multi-schema, autenticação completa (login com slug, JWT, papéis), sistema de módulos por tenant e painel da plataforma mínimo. Nenhuma tabela de negócio (cadastros/tickets) nesta fase. Sem CI: as verificações rodam localmente antes de cada commit (seção 8).

## Decisões de tooling (fechadas com o usuário em 2026-07-27)

- Planejamento por fase: um design geral + plano detalhado apenas da fase corrente.
- Frontend: Tailwind CSS 4 + shadcn/ui (Radix), ícones Lucide, pnpm, TanStack Query, React Router.
- Backend: uv (dependências/venv), ruff (lint + format), mypy (tipos), pytest.
- Sem CI: lint, tipos e testes rodam localmente antes de cada commit.
- Todo trabalho de frontend usa o skill frontend-design e segue `docs/identidade-visual.md`.

## 1. Estrutura do monorepo

```
backend/
  src/sac/
    domain/          # entidades, value objects, erros de domínio (Python puro, sem framework)
    application/     # use cases, ports (interfaces de repositório/serviços), DTOs
    infrastructure/  # SQLAlchemy (models, repositórios), segurança (argon2, JWT), settings, alembic
    interface/       # app FastAPI, routers, dependencies, schemas Pydantic, middleware, handlers
  tests/
    unit/            # domínio e use cases, repositórios fake, sem I/O
    integration/     # API + Postgres real
  pyproject.toml
  alembic.ini
frontend/
  src/
docker-compose.yml   # Postgres 16
```

Regra de dependência: `interface -> application -> domain`; `infrastructure` implementa os ports declarados em `application` e nunca é importada por `domain`/`application`. O grafo de objetos é montado nas dependencies do FastAPI (composition root em `interface`).

## 2. Multi-tenancy

- Schema `public` (global): `tenants` (id, slug único, nome, status: ativa/teste/suspensa/inativa, modules JSONB, timestamps, soft delete), `users` (id, nome, email único global, senha argon2, is_super_admin, ativo, timestamps, soft delete), `user_tenants` (user_id, tenant_id, papel, ativo).
- Schemas `t_<slug>`: tabelas de negócio (criadas nas fases seguintes; a Fase 0 entrega o mecanismo).
- Resolução de tenant por `schema_translate_map` do SQLAlchemy: models de negócio declarados com schema simbólico (`tenant`); a session de cada request aplica `execution_options(schema_translate_map={"tenant": "t_<slug>"})` com o slug extraído do JWT. Sem `SET search_path` manual e sem coluna `tenant_id` nas tabelas de negócio.
- Nomes de schema derivados exclusivamente do slug validado (regex `^[a-z0-9_]{2,40}$`) para eliminar injeção via identificador.

## 3. Migrations (Alembic, duas árvores)

- `migrations/public`: tabelas globais; version table `alembic_version` no schema `public`.
- `migrations/tenant`: tabelas de negócio; version table `alembic_version` dentro de cada schema de tenant.
- Runner próprio (comando CLI do backend): aplica a árvore public e itera os schemas `t_*` existentes aplicando a árvore tenant em cada um.
- Provisionamento de tenant: criar schema + aplicar head da árvore tenant + registrar em `tenants`, de forma atômica; falha desfaz o schema criado.

## 4. Autenticação e autorização

- `POST /auth/login` (email + senha + slug): valida tenant ativo -> vínculo em `user_tenants` -> usuário ativo -> senha argon2 (argon2-cffi). Erros de credencial não revelam qual etapa falhou. Rate limiting por IP+slug (slowapi).
- Tokens: access JWT curto (15 min) com `sub` (user id), `tenant` (slug), `role`; refresh token (7 dias, rota `/auth/refresh`). "Manter sessão" controla persistência do refresh no front. Sem registro público; reset de senha por admin (rota de admin define nova senha).
- Login de super_admin: mesmo endpoint sem slug (ou slug vazio) emite token global sem tenant, válido apenas nas rotas da plataforma.
- Papéis: `super_admin` (global); por tenant: `admin`, `supervisor`, `atendente`, `visualizador`. Matriz de permissões do PRD seção 3.
- Autorização em um único estilo: enum `Permission` + mapa papel -> permissões no domínio; dependency `require_permission(p)` nos routers. Nenhuma checagem manual espalhada.
- Sistema de módulos: `tenants.modules` JSONB (ex.: `{"tickets": true}`) + dependency `require_module(m)` nos routers de módulo. Módulo Eventos fora de escopo, mecanismo pronto.

## 5. Painel da plataforma (mínimo)

Rotas exclusivas de super_admin, fora de qualquer tenant:

- Tenants: criar (provisiona schema), listar, ativar/suspender, editar módulos.
- Usuários globais: criar, listar, ativar/desativar, redefinir senha.
- Vínculos: associar usuário a tenant com papel; remover vínculo.

Indicadores da plataforma ficam para fase posterior.

## 6. Frontend Fase 0

- Vite + React + TypeScript, Tailwind CSS 4 + shadcn/ui, Lucide, TanStack Query, React Router, pnpm.
- Entregas: tela de login (email + senha + slug, "manter sessão"), layout base (sidebar agrupada por módulos, header com menu de usuário), guarda de rotas por papel, telas mínimas do painel da plataforma (tenants, usuários, vínculos).
- Identidade visual conforme `docs/identidade-visual.md`: paleta Floral White / Silver / Charcoal Brown / Carbon Black / Spicy Paprika (Paprika só como sinalização), sans humanista + mono para dados técnicos, raio 4-6px, bordas em vez de sombras, sidebar escura. Os tokens do shadcn/ui são sobrescritos por esses valores.
- Design tokens via CSS variables; dark mode preparado (classe `dark`), sem toggle obrigatório nesta fase.
- Proibido emoji; modais e toasts próprios (shadcn/ui), nunca confirm/alert nativos.

## 7. Erros

- Domínio lança erros tipados (`DomainError` e subclasses: `NotFoundError`, `PermissionDeniedError`, `ValidationError`, `ConflictError`, `AuthError`).
- Exception handler único em `interface` mapeia para HTTP (404/403/422/409/401) com corpo padronizado `{code, message, details}`. Nenhum handler ad hoc por rota.

## 8. Testes e verificação local

- TDD (red-green-refactor) obrigatório no backend.
- Unit: domínio e use cases com repositórios fake em memória; sem banco.
- Integração: httpx AsyncClient contra a app + Postgres real (docker-compose); cada teste/módulo usa schema descartável criado e destruído na hora (sem testcontainers, funciona no Windows local).
- Sem CI. Antes de cada commit rodar localmente: backend `ruff check`, `ruff format --check`, `mypy`, `pytest`; frontend `tsc --noEmit`, `eslint`, `build` quando relevante.

## 9. Fora da Fase 0

Cadastros (Fase 1), tickets/máquina de estados/anexos Wasabi (Fase 2), dashboard/relatórios/galeria/importador (Fase 3), notificações/busca/hardening (Fase 4). Cada fase terá seu próprio plano de implementação derivado do PRD e deste design.
