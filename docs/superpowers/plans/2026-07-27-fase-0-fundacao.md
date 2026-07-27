# Fase 0 (Fundação) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fundação do SAC-B2PRO: monorepo backend/frontend, Postgres via docker-compose, Clean Architecture, migrations multi-schema (Alembic com duas árvores), autenticação completa (login com slug, argon2, JWT + refresh, papéis, rate limiting), sistema de módulos por tenant, painel da plataforma mínimo e front com login + shell + painel.

**Architecture:** Backend em camadas (domain / application / infrastructure / interface) com dependências apontando para dentro; multi-tenancy por schema Postgres resolvido com `schema_translate_map`; tabelas globais no schema `public`. Frontend React + Vite consumindo a API via proxy `/api`.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2 async (asyncpg), Alembic, argon2-cffi, PyJWT, pydantic-settings, uv, ruff, mypy, pytest; React 18 + TypeScript + Vite, Tailwind CSS 4, shadcn/ui, lucide-react, TanStack Query, React Router, pnpm.

**Spec:** `docs/superpowers/specs/2026-07-27-sac-b2pro-fase-0-design.md` (e `docs/PRD.md` seções 2, 3 e 10).

## Global Constraints

- PROIBIDO usar emojis em código, comentários, commits, UI, documentação e mensagens.
- Clean Architecture: `interface -> application -> domain`; `infrastructure` implementa os ports de `application`; `domain` e `application` nunca importam framework nem `infrastructure`.
- TDD no backend: escrever o teste antes da implementação em toda tarefa de backend.
- SEM CI. Antes de CADA commit rodar localmente e exigir sucesso:
  - Backend (em `backend/`): `uv run ruff format .` depois `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
  - Frontend (em `frontend/`): `pnpm lint` e `pnpm build` (o build roda `tsc -b`).
- Testes de integração exigem o Postgres do compose de pé: `docker compose up -d db` (na raiz do repo).
- Toda tarefa de frontend (Tasks 14-18) DEVE invocar o skill `frontend-design` antes de escrever UI e seguir `docs/identidade-visual.md` (paleta, tipografia sans + mono para dados técnicos, raio 4-6px, bordas em vez de sombras, sidebar escura, lucide-react com strokeWidth 1.5, sem ícones preenchidos).
- Commits em português, imperativo, sem prefixo convencional (seguir histórico do repo), terminando o corpo com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Python >= 3.12; Node >= 20 com pnpm.
- Nomes de schema de tenant sempre derivados de slug validado pela regex `^[a-z0-9_]{2,40}$` antes de qualquer interpolação em SQL.

## Mapa de arquivos do backend

```
backend/
  pyproject.toml
  alembic.ini
  .env.example
  src/sac/
    __init__.py
    main.py                      # app = create_app() para o uvicorn
    domain/
      __init__.py
      errors.py                  # DomainError e subclasses
      permissions.py             # Role, Permission, ROLE_PERMISSIONS, has_permission
      entities.py                # User, Tenant, UserTenant, TenantStatus, validate_slug
    application/
      __init__.py
      ports.py                   # Protocols de repositorios e servicos + TokenPayload
      use_cases/
        __init__.py
        auth.py                  # LoginUseCase, RefreshTokenUseCase, AuthResult
        platform_tenants.py      # Create/List/SetStatus/SetModules
        platform_users.py        # Create/List/SetActive/ResetPassword/Link/Unlink/ListLinks
    infrastructure/
      __init__.py
      settings.py                # Settings (pydantic-settings, prefixo SAC_)
      security.py                # Argon2PasswordHasher, JwtTokenService
      db.py                      # build_engine, build_session_factory
      models.py                  # Base + models do schema public
      models_tenant.py           # TenantBase (schema simbolico "tenant", vazio na Fase 0)
      repositories.py            # SqlUserRepository, SqlTenantRepository, SqlUserTenantRepository
      migrate.py                 # upgrade_public, upgrade_tenant, upgrade_all_tenants, CLI
      provisioning.py            # AlembicTenantProvisioner
      seed.py                    # cria super admin a partir do .env
    interface/
      __init__.py
      app.py                     # create_app
      deps.py                    # sessions, servicos, identidade, require_*
      errors.py                  # handler unico de DomainError
      rate_limit.py              # SlidingWindowRateLimiter, RateLimitedError
      schemas.py                 # Pydantic de request/response
      routers/
        __init__.py
        health.py
        auth.py
        platform_tenants.py
        platform_users.py
  migrations/
    public/{env.py, script.py.mako, versions/}
    tenant/{env.py, script.py.mako, versions/0001_baseline.py}
  tests/
    unit/           # sem I/O
    integration/    # Postgres real (banco sac_test)
```

---

### Task 1: Fundação do backend (uv, tooling, docker-compose)

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/src/sac/__init__.py` (e `__init__.py` vazios de `domain/`, `application/`, `application/use_cases/`, `infrastructure/`, `interface/`, `interface/routers/`)
- Create: `docker-compose.yml`
- Modify: `.gitignore`
- Test: `backend/tests/unit/test_sanity.py`

**Interfaces:**
- Consumes: nada.
- Produces: pacote `sac` importável; comandos `uv run ruff/mypy/pytest`; serviço `db` (Postgres 16) em `localhost:5432`, usuário/senha/banco `sac`.

- [ ] **Step 1: Criar `backend/pyproject.toml`**

```toml
[project]
name = "sac-backend"
version = "0.1.0"
description = "SAC-B2PRO backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic[email]>=2.7",
    "pydantic-settings>=2.3",
    "argon2-cffi>=23.1",
    "pyjwt>=2.8",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sac"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
strict = true
mypy_path = "src"
packages = ["sac"]

[[tool.mypy.overrides]]
module = "alembic.*"
ignore_missing_imports = true
```

- [ ] **Step 2: Criar `docker-compose.yml` na raiz do repo**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: sac
      POSTGRES_PASSWORD: sac
      POSTGRES_DB: sac
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

- [ ] **Step 3: Criar `backend/.env.example`**

```
SAC_DATABASE_URL=postgresql+asyncpg://sac:sac@localhost:5432/sac
SAC_JWT_SECRET=troque-este-segredo
SAC_SEED_ADMIN_EMAIL=
SAC_SEED_ADMIN_PASSWORD=
```

- [ ] **Step 4: Atualizar `.gitignore` (append ao conteúdo atual)**

```
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
node_modules/
dist/
```

- [ ] **Step 5: Criar o pacote e o teste de sanidade**

Criar `backend/src/sac/__init__.py` vazio (e os demais `__init__.py` listados em Files).

`backend/tests/unit/test_sanity.py`:

```python
import sac


def test_pacote_importavel() -> None:
    assert sac is not None
```

- [ ] **Step 6: Instalar e subir o banco**

Em `backend/`: `uv sync`
Na raiz: `docker compose up -d db` e depois `docker compose ps` (esperado: serviço `db` rodando).

- [ ] **Step 7: Rodar as verificações**

Em `backend/`: `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest`
Esperado: tudo passa; pytest com 1 teste.

- [ ] **Step 8: Commit**

```bash
git add backend docker-compose.yml .gitignore
git commit -m "Cria fundacao do backend com uv, tooling e docker-compose"
```

---

### Task 2: Domínio — erros e permissões

**Files:**
- Create: `backend/src/sac/domain/errors.py`
- Create: `backend/src/sac/domain/permissions.py`
- Test: `backend/tests/unit/domain/test_permissions.py`

**Interfaces:**
- Consumes: nada.
- Produces: `DomainError(message, details=None)` com atributos `code: str` e `details: dict`; subclasses `ValidationError` (code `validation_error`), `NotFoundError` (`not_found`), `ConflictError` (`conflict`), `PermissionDeniedError` (`permission_denied`), `AuthError` (`auth_error`); `Role` (admin/supervisor/atendente/visualizador), `Permission` (StrEnum), `ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]`, `has_permission(role, permission) -> bool`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/domain/test_permissions.py`:

```python
from sac.domain.permissions import ROLE_PERMISSIONS, Permission, Role, has_permission


def test_admin_tem_todas_as_permissoes() -> None:
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)


def test_supervisor_nao_gerencia_usuarios() -> None:
    assert not has_permission(Role.SUPERVISOR, Permission.GERENCIAR_USUARIOS)
    assert has_permission(Role.SUPERVISOR, Permission.DECIDIR_TICKET)


def test_atendente_nao_decide_nem_gerencia_cadastros() -> None:
    assert not has_permission(Role.ATENDENTE, Permission.DECIDIR_TICKET)
    assert not has_permission(Role.ATENDENTE, Permission.GERENCIAR_CADASTROS)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_TICKET)
    assert has_permission(Role.ATENDENTE, Permission.ENVIAR_PARA_ANALISE)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_LISTAR_CADASTROS)


def test_visualizador_so_leitura() -> None:
    assert ROLE_PERMISSIONS[Role.VISUALIZADOR] == frozenset(
        {Permission.VER_TODOS_TICKETS, Permission.LISTAR_CADASTROS}
    )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/domain/test_permissions.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar**

`backend/src/sac/domain/errors.py`:

```python
class DomainError(Exception):
    code: str = "domain_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, object] = details or {}


class ValidationError(DomainError):
    code = "validation_error"


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class PermissionDeniedError(DomainError):
    code = "permission_denied"


class AuthError(DomainError):
    code = "auth_error"
```

`backend/src/sac/domain/permissions.py` (matriz do PRD secao 3):

```python
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    ATENDENTE = "atendente"
    VISUALIZADOR = "visualizador"


class Permission(StrEnum):
    VER_TODOS_TICKETS = "ver_todos_tickets"
    VER_PROPRIOS_TICKETS = "ver_proprios_tickets"
    CRIAR_TICKET = "criar_ticket"
    EDITAR_QUALQUER_TICKET = "editar_qualquer_ticket"
    EDITAR_PROPRIO_TICKET = "editar_proprio_ticket"
    ENVIAR_PARA_ANALISE = "enviar_para_analise"
    DECIDIR_TICKET = "decidir_ticket"
    OPERAR_LOGISTICA_TODOS = "operar_logistica_todos"
    OPERAR_LOGISTICA_PROPRIOS = "operar_logistica_proprios"
    COMENTAR_ANEXAR = "comentar_anexar"
    GERENCIAR_CADASTROS = "gerenciar_cadastros"
    CRIAR_LISTAR_CADASTROS = "criar_listar_cadastros"
    LISTAR_CADASTROS = "listar_cadastros"
    GERENCIAR_USUARIOS = "gerenciar_usuarios"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.SUPERVISOR: frozenset(Permission) - {Permission.GERENCIAR_USUARIOS},
    Role.ATENDENTE: frozenset(
        {
            Permission.VER_PROPRIOS_TICKETS,
            Permission.CRIAR_TICKET,
            Permission.EDITAR_PROPRIO_TICKET,
            Permission.ENVIAR_PARA_ANALISE,
            Permission.OPERAR_LOGISTICA_PROPRIOS,
            Permission.COMENTAR_ANEXAR,
            Permission.CRIAR_LISTAR_CADASTROS,
        }
    ),
    Role.VISUALIZADOR: frozenset(
        {
            Permission.VER_TODOS_TICKETS,
            Permission.LISTAR_CADASTROS,
        }
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain/test_permissions.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/domain backend/tests/unit/domain
git commit -m "Adiciona erros de dominio e matriz de papeis e permissoes"
```

---

### Task 3: Domínio — entidades, slug e ports da application

**Files:**
- Create: `backend/src/sac/domain/entities.py`
- Create: `backend/src/sac/application/ports.py`
- Test: `backend/tests/unit/domain/test_entities.py`

**Interfaces:**
- Consumes: `ValidationError`, `Role` (Task 2).
- Produces:
  - `TenantStatus` (StrEnum: ativa/teste/suspensa/inativa); `validate_slug(slug: str) -> str` (levanta `ValidationError`); `TENANT_SLUG_RE`.
  - Dataclasses: `User(id: UUID, name, email, password_hash, is_super_admin=False, active=True, deleted_at=None)`; `Tenant(id, slug, name, status=TenantStatus.ATIVA, modules: dict[str, bool] = {}, deleted_at=None)` com propriedade `schema_name -> "t_<slug>"`; `UserTenant(user_id, tenant_id, role: Role, active=True)`.
  - Ports (Protocol, todos async exceto hasher/tokens):
    - `UserRepository`: `get_by_email(email) -> User | None`, `get_by_id(user_id) -> User | None`, `add(user) -> None`, `list_all() -> list[User]`, `update(user) -> None`
    - `TenantRepository`: `get_by_slug(slug) -> Tenant | None`, `get_by_id(tenant_id) -> Tenant | None`, `add(tenant) -> None`, `list_all() -> list[Tenant]`, `update(tenant) -> None`
    - `UserTenantRepository`: `get(user_id, tenant_id) -> UserTenant | None`, `add(link) -> None`, `remove(user_id, tenant_id) -> None`, `list_for_tenant(tenant_id) -> list[UserTenant]`
    - `PasswordHasherPort`: `hash(password) -> str`, `verify(password_hash, password) -> bool`
    - `TokenServicePort`: `create_access(user_id, tenant_slug, role, is_super_admin) -> str`, `create_refresh(...) -> str` (mesma assinatura), `decode(token, expected_type) -> TokenPayload`
    - `TenantProvisionerPort`: `provision(schema_name) -> None` (async)
  - `TokenPayload(user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool, token_type: str)` (frozen dataclass).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/domain/test_entities.py`:

```python
from uuid import uuid4

import pytest

from sac.domain.entities import Tenant, TenantStatus, validate_slug
from sac.domain.errors import ValidationError


def test_slug_valido() -> None:
    assert validate_slug("kodi_staleks_01") == "kodi_staleks_01"


@pytest.mark.parametrize("slug", ["", "a", "Maiusculo", "com-hifen", "com espaco", "a" * 41])
def test_slug_invalido(slug: str) -> None:
    with pytest.raises(ValidationError):
        validate_slug(slug)


def test_schema_name_deriva_do_slug() -> None:
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    assert tenant.schema_name == "t_b2pro"
    assert tenant.status is TenantStatus.ATIVA
    assert tenant.modules == {}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/domain/test_entities.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/domain/entities.py`**

```python
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sac.domain.errors import ValidationError
from sac.domain.permissions import Role

TENANT_SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def validate_slug(slug: str) -> str:
    if not TENANT_SLUG_RE.fullmatch(slug):
        raise ValidationError(
            "slug invalido: use 2 a 40 caracteres entre a-z, 0-9 e _",
            details={"slug": slug},
        )
    return slug


class TenantStatus(StrEnum):
    ATIVA = "ativa"
    TESTE = "teste"
    SUSPENSA = "suspensa"
    INATIVA = "inativa"


@dataclass
class User:
    id: UUID
    name: str
    email: str
    password_hash: str
    is_super_admin: bool = False
    active: bool = True
    deleted_at: datetime | None = None


@dataclass
class Tenant:
    id: UUID
    slug: str
    name: str
    status: TenantStatus = TenantStatus.ATIVA
    modules: dict[str, bool] = field(default_factory=dict)
    deleted_at: datetime | None = None

    @property
    def schema_name(self) -> str:
        return f"t_{self.slug}"


@dataclass
class UserTenant:
    user_id: UUID
    tenant_id: UUID
    role: Role
    active: bool = True
```

- [ ] **Step 4: Implementar `backend/src/sac/application/ports.py`**

```python
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sac.domain.entities import Tenant, User, UserTenant
from sac.domain.permissions import Role


@dataclass(frozen=True)
class TokenPayload:
    user_id: UUID
    tenant_slug: str | None
    role: Role | None
    is_super_admin: bool
    token_type: str


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def add(self, user: User) -> None: ...
    async def list_all(self) -> list[User]: ...
    async def update(self, user: User) -> None: ...


class TenantRepository(Protocol):
    async def get_by_slug(self, slug: str) -> Tenant | None: ...
    async def get_by_id(self, tenant_id: UUID) -> Tenant | None: ...
    async def add(self, tenant: Tenant) -> None: ...
    async def list_all(self) -> list[Tenant]: ...
    async def update(self, tenant: Tenant) -> None: ...


class UserTenantRepository(Protocol):
    async def get(self, user_id: UUID, tenant_id: UUID) -> UserTenant | None: ...
    async def add(self, link: UserTenant) -> None: ...
    async def remove(self, user_id: UUID, tenant_id: UUID) -> None: ...
    async def list_for_tenant(self, tenant_id: UUID) -> list[UserTenant]: ...


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...


class TokenServicePort(Protocol):
    def create_access(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str: ...
    def create_refresh(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str: ...
    def decode(self, token: str, expected_type: str) -> TokenPayload: ...


class TenantProvisionerPort(Protocol):
    async def provision(self, schema_name: str) -> None: ...
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/domain/entities.py backend/src/sac/application/ports.py backend/tests/unit/domain/test_entities.py
git commit -m "Adiciona entidades de dominio, validacao de slug e ports da application"
```

---

### Task 4: Infra — settings e segurança (argon2 + JWT)

**Files:**
- Create: `backend/src/sac/infrastructure/settings.py`
- Create: `backend/src/sac/infrastructure/security.py`
- Test: `backend/tests/unit/infrastructure/test_security.py`

**Interfaces:**
- Consumes: `AuthError`, `Role`, `TokenPayload` (Tasks 2-3).
- Produces:
  - `Settings` (pydantic-settings, prefixo `SAC_`, le `.env`): `database_url`, `jwt_secret`, `jwt_algorithm="HS256"`, `access_token_ttl_minutes=15`, `refresh_token_ttl_days=7`, `cors_origins=["http://localhost:5173"]`, `seed_admin_name`, `seed_admin_email`, `seed_admin_password`.
  - `Argon2PasswordHasher` implementando `PasswordHasherPort`.
  - `JwtTokenService(secret, algorithm, access_ttl, refresh_ttl)` implementando `TokenServicePort`, com classmethod `from_settings(settings) -> JwtTokenService`. Claims: `sub` (str UUID), `type` ("access"/"refresh"), `sa` (bool), `tenant` (opcional), `role` (opcional), `iat`, `exp`. `decode` levanta `AuthError` em token invalido/expirado/tipo errado.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/infrastructure/test_security.py`:

```python
from datetime import timedelta
from uuid import uuid4

import pytest

from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService


def _service(access_ttl: timedelta = timedelta(minutes=15)) -> JwtTokenService:
    return JwtTokenService("segredo-teste", "HS256", access_ttl, timedelta(days=7))


def test_hash_e_verificacao_de_senha() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("senha-forte-123")
    assert password_hash != "senha-forte-123"
    assert hasher.verify(password_hash, "senha-forte-123")
    assert not hasher.verify(password_hash, "senha-errada")
    assert not hasher.verify("hash-invalido", "qualquer")


def test_roundtrip_de_access_token() -> None:
    service = _service()
    user_id = uuid4()
    token = service.create_access(user_id, "b2pro", Role.ADMIN, False)
    payload = service.decode(token, expected_type="access")
    assert payload.user_id == user_id
    assert payload.tenant_slug == "b2pro"
    assert payload.role is Role.ADMIN
    assert payload.is_super_admin is False
    assert payload.token_type == "access"


def test_token_de_super_admin_sem_tenant() -> None:
    service = _service()
    token = service.create_access(uuid4(), None, None, True)
    payload = service.decode(token, expected_type="access")
    assert payload.tenant_slug is None
    assert payload.role is None
    assert payload.is_super_admin is True


def test_tipo_de_token_errado_e_rejeitado() -> None:
    service = _service()
    refresh = service.create_refresh(uuid4(), None, None, True)
    with pytest.raises(AuthError):
        service.decode(refresh, expected_type="access")


def test_token_expirado_e_rejeitado() -> None:
    service = _service(access_ttl=timedelta(seconds=-1))
    token = service.create_access(uuid4(), None, None, True)
    with pytest.raises(AuthError):
        service.decode(token, expected_type="access")


def test_segredo_errado_e_rejeitado() -> None:
    token = _service().create_access(uuid4(), None, None, True)
    outro = JwtTokenService("outro-segredo", "HS256", timedelta(minutes=15), timedelta(days=7))
    with pytest.raises(AuthError):
        outro.decode(token, expected_type="access")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/infrastructure/test_security.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/infrastructure/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://sac:sac@localhost:5432/sac"
    jwt_secret: str = "dev-secret-troque-em-producao"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    seed_admin_name: str = "Administrador"
    seed_admin_email: str = ""
    seed_admin_password: str = ""
```

- [ ] **Step 4: Implementar `backend/src/sac/infrastructure/security.py`**

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

from sac.application.ports import TokenPayload
from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.settings import Settings


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = _Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False


class JwtTokenService:
    def __init__(
        self, secret: str, algorithm: str, access_ttl: timedelta, refresh_ttl: timedelta
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    @classmethod
    def from_settings(cls, settings: Settings) -> "JwtTokenService":
        return cls(
            settings.jwt_secret,
            settings.jwt_algorithm,
            timedelta(minutes=settings.access_token_ttl_minutes),
            timedelta(days=settings.refresh_token_ttl_days),
        )

    def create_access(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str:
        return self._create(user_id, tenant_slug, role, is_super_admin, "access", self._access_ttl)

    def create_refresh(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str:
        return self._create(
            user_id, tenant_slug, role, is_super_admin, "refresh", self._refresh_ttl
        )

    def _create(
        self,
        user_id: UUID,
        tenant_slug: str | None,
        role: Role | None,
        is_super_admin: bool,
        token_type: str,
        ttl: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        claims: dict[str, object] = {
            "sub": str(user_id),
            "type": token_type,
            "sa": is_super_admin,
            "iat": now,
            "exp": now + ttl,
        }
        if tenant_slug is not None:
            claims["tenant"] = tenant_slug
        if role is not None:
            claims["role"] = role.value
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def decode(self, token: str, expected_type: str) -> TokenPayload:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise AuthError("token invalido ou expirado") from exc
        if claims.get("type") != expected_type:
            raise AuthError("tipo de token invalido")
        role_value = claims.get("role")
        return TokenPayload(
            user_id=UUID(claims["sub"]),
            tenant_slug=claims.get("tenant"),
            role=Role(role_value) if role_value else None,
            is_super_admin=bool(claims.get("sa", False)),
            token_type=expected_type,
        )
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/infrastructure -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure backend/tests/unit/infrastructure
git commit -m "Adiciona settings e servicos de seguranca argon2 e JWT"
```

---

### Task 5: Infra — models globais, engine e Alembic (árvore public)

**Files:**
- Create: `backend/src/sac/infrastructure/models.py`
- Create: `backend/src/sac/infrastructure/db.py`
- Create: `backend/src/sac/infrastructure/migrate.py`
- Create: `backend/alembic.ini`
- Create: `backend/migrations/public/env.py`
- Create: `backend/migrations/public/script.py.mako`
- Create: `backend/migrations/public/versions/` (migration inicial via autogenerate)
- Test: `backend/tests/integration/conftest.py`, `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Consumes: `Settings` (Task 4).
- Produces:
  - `Base` (DeclarativeBase) e models `UserModel` (tabela `users`), `TenantModel` (`tenants`), `UserTenantModel` (`user_tenants`) no schema default (public).
  - `build_engine(database_url) -> AsyncEngine`; `build_session_factory(engine) -> async_sessionmaker[AsyncSession]`.
  - `upgrade_public() -> None`, `upgrade_tenant(schema_name: str) -> None`, `upgrade_all_tenants() -> None` e CLI `python -m sac.infrastructure.migrate [public|tenants|all]`.
  - Fixtures de integração: `database` (session scope, recria o banco `sac_test`, exporta `SAC_DATABASE_URL`, roda `upgrade_public`), `engine` (function scope, trunca tabelas e derruba schemas `t_*`), `session`.

- [ ] **Step 1: Implementar `backend/src/sac/infrastructure/models.py`**

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantModel(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="ativa")
    modules: Mapped[dict[str, bool]] = mapped_column(JSONB, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserTenantModel(Base):
    __tablename__ = "user_tenants"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 2: Implementar `backend/src/sac/infrastructure/db.py`**

```python
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [ ] **Step 3: Criar `backend/alembic.ini`**

```ini
[public]
script_location = %(here)s/migrations/public

[tenant]
script_location = %(here)s/migrations/tenant
```

- [ ] **Step 4: Criar `backend/migrations/public/env.py` e `script.py.mako`**

`env.py`:

```python
import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from sac.infrastructure.models import Base
from sac.infrastructure.settings import Settings

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("modo offline nao suportado")
asyncio.run(run_async_migrations())
```

`script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Criar também a pasta vazia `backend/migrations/public/versions/`.

- [ ] **Step 5: Implementar `backend/src/sac/infrastructure/migrate.py`**

```python
import argparse
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sac.infrastructure.settings import Settings

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _config(section: str) -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"), ini_section=section)


def upgrade_public() -> None:
    command.upgrade(_config("public"), "head")


def upgrade_tenant(schema_name: str) -> None:
    cfg = _config("tenant")
    cfg.attributes["schema"] = schema_name
    command.upgrade(cfg, "head")


async def _tenant_schemas() -> list[str]:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name LIKE 't\\_%'"
            )
        )
        schemas = [str(row[0]) for row in result]
    await engine.dispose()
    return schemas


def upgrade_all_tenants() -> None:
    for schema in asyncio.run(_tenant_schemas()):
        upgrade_tenant(schema)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-migrate")
    parser.add_argument("target", choices=["public", "tenants", "all"])
    args = parser.parse_args()
    if args.target in ("public", "all"):
        upgrade_public()
    if args.target in ("tenants", "all"):
        upgrade_all_tenants()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Gerar a migration inicial (banco dev de pé)**

Em `backend/` (com `docker compose up -d db` feito na raiz):

```bash
uv run alembic -c alembic.ini -n public revision --autogenerate -m "tabelas globais"
```

Abrir o arquivo gerado em `migrations/public/versions/` e conferir que cria `users`, `tenants` e `user_tenants` com os campos do Step 1.

- [ ] **Step 7: Escrever o conftest e o teste de integração**

`backend/tests/integration/conftest.py`:

```python
import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ADMIN_URL = "postgresql+asyncpg://sac:sac@localhost:5432/postgres"
TEST_DB_URL = "postgresql+asyncpg://sac:sac@localhost:5432/sac_test"


async def _recreate_database() -> None:
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS sac_test WITH (FORCE)"))
        await conn.execute(text("CREATE DATABASE sac_test"))
    await engine.dispose()


@pytest.fixture(scope="session")
def database() -> str:
    os.environ["SAC_DATABASE_URL"] = TEST_DB_URL
    asyncio.run(_recreate_database())
    from sac.infrastructure.migrate import upgrade_public

    upgrade_public()
    return TEST_DB_URL


@pytest.fixture
async def engine(database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE user_tenants, users, tenants CASCADE"))
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name LIKE 't\\_%'"
            )
        )
        for row in result.all():
            await conn.execute(text(f'DROP SCHEMA "{row[0]}" CASCADE'))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
```

`backend/tests/integration/test_migrations.py`:

```python
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_migration_public_cria_tabelas_globais(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="public"))
    assert {"users", "tenants", "user_tenants", "alembic_version"} <= set(tables)
```

- [ ] **Step 8: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_migrations.py -v`
Esperado: PASS (exige o Postgres do compose de pé).

- [ ] **Step 9: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure backend/alembic.ini backend/migrations backend/tests/integration
git commit -m "Adiciona models globais, engine async e arvore de migrations public"
```

---

### Task 6: Infra — árvore tenant e provisionamento de schema

**Files:**
- Create: `backend/src/sac/infrastructure/models_tenant.py`
- Create: `backend/src/sac/infrastructure/provisioning.py`
- Create: `backend/migrations/tenant/env.py`
- Create: `backend/migrations/tenant/script.py.mako` (mesmo conteúdo do mako da Task 5)
- Create: `backend/migrations/tenant/versions/0001_baseline.py`
- Test: `backend/tests/integration/test_provisioning.py`

**Interfaces:**
- Consumes: `Settings`, `migrate.upgrade_tenant` (Tasks 4-5).
- Produces: `TenantBase` (DeclarativeBase para tabelas de negócio; nas fases seguintes as tabelas declaram `__table_args__ = {"schema": "tenant"}` e o schema simbólico é traduzido); `AlembicTenantProvisioner(engine)` com `provision(schema_name)` (cria schema + aplica head da árvore tenant; em falha derruba o schema e relança) e `drop(schema_name)`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_provisioning.py`:

```python
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure import migrate
from sac.infrastructure.provisioning import AlembicTenantProvisioner


async def _schema_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata")
        )
        return {str(row[0]) for row in result}


async def test_provision_cria_schema_com_version_table(engine: AsyncEngine) -> None:
    provisioner = AlembicTenantProvisioner(engine)
    await provisioner.provision("t_demo")

    assert "t_demo" in await _schema_names(engine)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert "alembic_version" in tables


async def test_falha_na_migracao_desfaz_o_schema(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(schema_name: str) -> None:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(migrate, "upgrade_tenant", explode)
    provisioner = AlembicTenantProvisioner(engine)

    with pytest.raises(RuntimeError):
        await provisioner.provision("t_falha")

    assert "t_falha" not in await _schema_names(engine)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_provisioning.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar models_tenant, env.py da árvore tenant e baseline**

`backend/src/sac/infrastructure/models_tenant.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class TenantBase(DeclarativeBase):
    pass
```

`backend/migrations/tenant/env.py`:

```python
import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from sac.infrastructure.models_tenant import TenantBase
from sac.infrastructure.settings import Settings

target_metadata = TenantBase.metadata


def _schema() -> str:
    schema = context.config.attributes.get("schema") or context.get_x_argument(
        as_dictionary=True
    ).get("schema")
    if not schema:
        raise RuntimeError("informe o schema do tenant: -x schema=t_<slug>")
    return str(schema)


def do_run_migrations(connection: Connection, schema: str) -> None:
    connection = connection.execution_options(schema_translate_map={"tenant": schema})
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(schema: str) -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(lambda conn: do_run_migrations(conn, schema))
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("modo offline nao suportado")
asyncio.run(run_async_migrations(_schema()))
```

`backend/migrations/tenant/versions/0001_baseline.py`:

```python
"""baseline do schema de tenant

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-27

"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
```

Copiar `backend/migrations/public/script.py.mako` para `backend/migrations/tenant/script.py.mako`.

- [ ] **Step 4: Implementar `backend/src/sac/infrastructure/provisioning.py`**

```python
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure import migrate


class AlembicTenantProvisioner:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def provision(self, schema_name: str) -> None:
        # schema_name sempre deriva de slug validado por validate_slug
        async with self._engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        try:
            await asyncio.to_thread(migrate.upgrade_tenant, schema_name)
        except Exception:
            await self.drop(schema_name)
            raise

    async def drop(self, schema_name: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_provisioning.py -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure backend/migrations/tenant backend/tests/integration/test_provisioning.py
git commit -m "Adiciona arvore de migrations tenant e provisionamento de schema"
```

---

### Task 7: Infra — repositórios SQL

**Files:**
- Create: `backend/src/sac/infrastructure/repositories.py`
- Test: `backend/tests/integration/test_repositories.py`

**Interfaces:**
- Consumes: models (Task 5), entidades (Task 3), `ConflictError`/`NotFoundError` (Task 2).
- Produces: `SqlUserRepository(session)`, `SqlTenantRepository(session)`, `SqlUserTenantRepository(session)` implementando os ports da Task 3. `add` levanta `ConflictError` em violação de unicidade; `update`/`remove` levantam `NotFoundError` se o registro não existe; leituras ignoram registros com `deleted_at` preenchido.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_repositories.py`:

```python
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.errors import ConflictError
from sac.domain.permissions import Role
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)


def _user(email: str = "a@b.com") -> User:
    return User(id=uuid4(), name="Ana", email=email, password_hash="h")


def _tenant(slug: str = "b2pro") -> Tenant:
    return Tenant(id=uuid4(), slug=slug, name="B2PRO", modules={"tickets": True})


async def test_user_roundtrip(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    user = _user()
    await repo.add(user)
    await session.commit()

    found = await repo.get_by_email("a@b.com")
    assert found is not None
    assert found.id == user.id
    assert await repo.get_by_id(user.id) is not None
    assert [u.email for u in await repo.list_all()] == ["a@b.com"]


async def test_email_duplicado_gera_conflito(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    await repo.add(_user())
    with pytest.raises(ConflictError):
        await repo.add(_user())


async def test_update_de_usuario(session: AsyncSession) -> None:
    repo = SqlUserRepository(session)
    user = _user()
    await repo.add(user)
    await session.commit()

    user.active = False
    user.name = "Ana Maria"
    await repo.update(user)
    await session.commit()

    found = await repo.get_by_id(user.id)
    assert found is not None and found.active is False and found.name == "Ana Maria"


async def test_tenant_roundtrip_preserva_status_e_modulos(session: AsyncSession) -> None:
    repo = SqlTenantRepository(session)
    tenant = _tenant()
    tenant.status = TenantStatus.TESTE
    await repo.add(tenant)
    await session.commit()

    found = await repo.get_by_slug("b2pro")
    assert found is not None
    assert found.status is TenantStatus.TESTE
    assert found.modules == {"tickets": True}
    with pytest.raises(ConflictError):
        await repo.add(_tenant())


async def test_vinculo_roundtrip(session: AsyncSession) -> None:
    users = SqlUserRepository(session)
    tenants = SqlTenantRepository(session)
    links = SqlUserTenantRepository(session)
    user, tenant = _user(), _tenant()
    await users.add(user)
    await tenants.add(tenant)
    link = UserTenant(user_id=user.id, tenant_id=tenant.id, role=Role.SUPERVISOR)
    await links.add(link)
    await session.commit()

    found = await links.get(user.id, tenant.id)
    assert found is not None and found.role is Role.SUPERVISOR
    assert len(await links.list_for_tenant(tenant.id)) == 1

    await links.remove(user.id, tenant.id)
    await session.commit()
    assert await links.get(user.id, tenant.id) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_repositories.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/infrastructure/repositories.py`**

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError
from sac.domain.permissions import Role
from sac.infrastructure.models import TenantModel, UserModel, UserTenantModel


def _user_entity(m: UserModel) -> User:
    return User(
        id=m.id,
        name=m.name,
        email=m.email,
        password_hash=m.password_hash,
        is_super_admin=m.is_super_admin,
        active=m.active,
        deleted_at=m.deleted_at,
    )


def _tenant_entity(m: TenantModel) -> Tenant:
    return Tenant(
        id=m.id,
        slug=m.slug,
        name=m.name,
        status=TenantStatus(m.status),
        modules=dict(m.modules),
        deleted_at=m.deleted_at,
    )


def _link_entity(m: UserTenantModel) -> UserTenant:
    return UserTenant(
        user_id=m.user_id, tenant_id=m.tenant_id, role=Role(m.role), active=m.active
    )


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        m = await self._session.scalar(
            select(UserModel).where(UserModel.email == email, UserModel.deleted_at.is_(None))
        )
        return _user_entity(m) if m else None

    async def get_by_id(self, user_id: UUID) -> User | None:
        m = await self._session.get(UserModel, user_id)
        return _user_entity(m) if m and m.deleted_at is None else None

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                name=user.name,
                email=user.email,
                password_hash=user.password_hash,
                is_super_admin=user.is_super_admin,
                active=user.active,
                deleted_at=user.deleted_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("email ja cadastrado") from exc

    async def list_all(self) -> list[User]:
        result = await self._session.scalars(
            select(UserModel).where(UserModel.deleted_at.is_(None)).order_by(UserModel.name)
        )
        return [_user_entity(m) for m in result]

    async def update(self, user: User) -> None:
        m = await self._session.get(UserModel, user.id)
        if m is None:
            raise NotFoundError("usuario nao encontrado")
        m.name = user.name
        m.email = user.email
        m.password_hash = user.password_hash
        m.is_super_admin = user.is_super_admin
        m.active = user.active
        m.deleted_at = user.deleted_at
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("email ja cadastrado") from exc


class SqlTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slug(self, slug: str) -> Tenant | None:
        m = await self._session.scalar(
            select(TenantModel).where(TenantModel.slug == slug, TenantModel.deleted_at.is_(None))
        )
        return _tenant_entity(m) if m else None

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        m = await self._session.get(TenantModel, tenant_id)
        return _tenant_entity(m) if m and m.deleted_at is None else None

    async def add(self, tenant: Tenant) -> None:
        self._session.add(
            TenantModel(
                id=tenant.id,
                slug=tenant.slug,
                name=tenant.name,
                status=tenant.status.value,
                modules=dict(tenant.modules),
                deleted_at=tenant.deleted_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("slug ja cadastrado") from exc

    async def list_all(self) -> list[Tenant]:
        result = await self._session.scalars(
            select(TenantModel).where(TenantModel.deleted_at.is_(None)).order_by(TenantModel.slug)
        )
        return [_tenant_entity(m) for m in result]

    async def update(self, tenant: Tenant) -> None:
        m = await self._session.get(TenantModel, tenant.id)
        if m is None:
            raise NotFoundError("tenant nao encontrado")
        m.name = tenant.name
        m.status = tenant.status.value
        m.modules = dict(tenant.modules)
        m.deleted_at = tenant.deleted_at
        await self._session.flush()


class SqlUserTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID, tenant_id: UUID) -> UserTenant | None:
        m = await self._session.get(UserTenantModel, (user_id, tenant_id))
        return _link_entity(m) if m else None

    async def add(self, link: UserTenant) -> None:
        self._session.add(
            UserTenantModel(
                user_id=link.user_id,
                tenant_id=link.tenant_id,
                role=link.role.value,
                active=link.active,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("vinculo ja existe") from exc

    async def remove(self, user_id: UUID, tenant_id: UUID) -> None:
        m = await self._session.get(UserTenantModel, (user_id, tenant_id))
        if m is None:
            raise NotFoundError("vinculo nao encontrado")
        await self._session.delete(m)
        await self._session.flush()

    async def list_for_tenant(self, tenant_id: UUID) -> list[UserTenant]:
        result = await self._session.scalars(
            select(UserTenantModel).where(UserTenantModel.tenant_id == tenant_id)
        )
        return [_link_entity(m) for m in result]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_repositories.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure/repositories.py backend/tests/integration/test_repositories.py
git commit -m "Adiciona repositorios SQL das tabelas globais"
```

---

### Task 8: Application — use cases de login e refresh (com fakes)

**Files:**
- Create: `backend/src/sac/application/use_cases/auth.py`
- Create: `backend/tests/unit/fakes.py`
- Test: `backend/tests/unit/application/test_auth_use_cases.py`

**Interfaces:**
- Consumes: ports e entidades (Task 3), `JwtTokenService`/`Argon2PasswordHasher` (Task 4, apenas nos testes).
- Produces:
  - `AuthResult(access_token: str, refresh_token: str, user: User, tenant_slug: str | None, role: Role | None)` (frozen dataclass).
  - `LoginUseCase(users, tenants, links, hasher, tokens)` com `execute(email, password, tenant_slug: str | None) -> AuthResult`. Regras: email normalizado (strip + lower); falhas sempre com `AuthError("credenciais invalidas")` sem revelar etapa; com slug exige tenant com status em (ativa, teste) e vínculo ativo; sem slug exige `is_super_admin`.
  - `RefreshTokenUseCase(users, tenants, links, tokens)` com `execute(refresh_token: str) -> AuthResult`; revalida usuário/tenant/vínculo e reemite o par de tokens.
  - Fakes em memória reutilizáveis: `InMemoryUserRepository`, `InMemoryTenantRepository`, `InMemoryUserTenantRepository`, `FakeHasher` (hash = `"h:" + senha`).

- [ ] **Step 1: Criar os fakes**

`backend/tests/unit/fakes.py`:

```python
from uuid import UUID

from sac.domain.entities import Tenant, User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return next(
            (u for u in self.items.values() if u.email == email and u.deleted_at is None), None
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        user = self.items.get(user_id)
        return user if user and user.deleted_at is None else None

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email):
            raise ConflictError("email ja cadastrado")
        self.items[user.id] = user

    async def list_all(self) -> list[User]:
        return sorted(
            (u for u in self.items.values() if u.deleted_at is None), key=lambda u: u.name
        )

    async def update(self, user: User) -> None:
        if user.id not in self.items:
            raise NotFoundError("usuario nao encontrado")
        self.items[user.id] = user


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Tenant] = {}

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return next(
            (t for t in self.items.values() if t.slug == slug and t.deleted_at is None), None
        )

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        tenant = self.items.get(tenant_id)
        return tenant if tenant and tenant.deleted_at is None else None

    async def add(self, tenant: Tenant) -> None:
        if await self.get_by_slug(tenant.slug):
            raise ConflictError("slug ja cadastrado")
        self.items[tenant.id] = tenant

    async def list_all(self) -> list[Tenant]:
        return sorted(
            (t for t in self.items.values() if t.deleted_at is None), key=lambda t: t.slug
        )

    async def update(self, tenant: Tenant) -> None:
        if tenant.id not in self.items:
            raise NotFoundError("tenant nao encontrado")
        self.items[tenant.id] = tenant


class InMemoryUserTenantRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], UserTenant] = {}

    async def get(self, user_id: UUID, tenant_id: UUID) -> UserTenant | None:
        return self.items.get((user_id, tenant_id))

    async def add(self, link: UserTenant) -> None:
        key = (link.user_id, link.tenant_id)
        if key in self.items:
            raise ConflictError("vinculo ja existe")
        self.items[key] = link

    async def remove(self, user_id: UUID, tenant_id: UUID) -> None:
        if (user_id, tenant_id) not in self.items:
            raise NotFoundError("vinculo nao encontrado")
        del self.items[(user_id, tenant_id)]

    async def list_for_tenant(self, tenant_id: UUID) -> list[UserTenant]:
        return [link for link in self.items.values() if link.tenant_id == tenant_id]


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"h:{password}"
```

- [ ] **Step 2: Escrever o teste que falha**

`backend/tests/unit/application/test_auth_use_cases.py`:

```python
from datetime import timedelta
from uuid import uuid4

import pytest

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.security import JwtTokenService
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)

TOKENS = JwtTokenService("segredo-teste", "HS256", timedelta(minutes=15), timedelta(days=7))


class Cenario:
    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.tenants = InMemoryTenantRepository()
        self.links = InMemoryUserTenantRepository()
        self.hasher = FakeHasher()
        self.login = LoginUseCase(self.users, self.tenants, self.links, self.hasher, TOKENS)
        self.refresh = RefreshTokenUseCase(self.users, self.tenants, self.links, TOKENS)

    async def com_usuario(
        self, *, email: str = "ana@b2.com", active: bool = True, super_admin: bool = False
    ) -> User:
        user = User(
            id=uuid4(),
            name="Ana",
            email=email,
            password_hash="h:senha123",
            is_super_admin=super_admin,
            active=active,
        )
        await self.users.add(user)
        return user

    async def com_tenant(
        self, *, slug: str = "b2pro", status: TenantStatus = TenantStatus.ATIVA
    ) -> Tenant:
        tenant = Tenant(id=uuid4(), slug=slug, name="B2PRO", status=status)
        await self.tenants.add(tenant)
        return tenant

    async def com_vinculo(
        self, user: User, tenant: Tenant, *, role: Role = Role.ADMIN, active: bool = True
    ) -> None:
        await self.links.add(
            UserTenant(user_id=user.id, tenant_id=tenant.id, role=role, active=active)
        )


async def test_login_com_tenant_retorna_tokens_e_papel() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant, role=Role.SUPERVISOR)

    result = await c.login.execute("  ANA@B2.com ", "senha123", "b2pro")

    assert result.role is Role.SUPERVISOR
    assert result.tenant_slug == "b2pro"
    payload = TOKENS.decode(result.access_token, expected_type="access")
    assert payload.user_id == user.id and payload.role is Role.SUPERVISOR
    TOKENS.decode(result.refresh_token, expected_type="refresh")


async def test_login_super_admin_sem_slug() -> None:
    c = Cenario()
    await c.com_usuario(super_admin=True)
    result = await c.login.execute("ana@b2.com", "senha123", None)
    assert result.tenant_slug is None and result.role is None
    assert TOKENS.decode(result.access_token, expected_type="access").is_super_admin


@pytest.mark.parametrize(
    "caso",
    ["senha_errada", "usuario_inexistente", "usuario_inativo", "sem_vinculo",
     "vinculo_inativo", "tenant_suspenso", "comum_sem_slug"],
)
async def test_falhas_de_login_sao_indistinguiveis(caso: str) -> None:
    c = Cenario()
    user = await c.com_usuario(active=caso != "usuario_inativo")
    tenant = await c.com_tenant(
        status=TenantStatus.SUSPENSA if caso == "tenant_suspenso" else TenantStatus.ATIVA
    )
    if caso not in ("sem_vinculo",):
        await c.com_vinculo(user, tenant, active=caso != "vinculo_inativo")

    email = "nao@existe.com" if caso == "usuario_inexistente" else "ana@b2.com"
    password = "errada" if caso == "senha_errada" else "senha123"
    slug = None if caso == "comum_sem_slug" else "b2pro"

    with pytest.raises(AuthError) as exc:
        await c.login.execute(email, password, slug)
    assert str(exc.value) == "credenciais invalidas"


async def test_tenant_em_teste_permite_login() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant(status=TenantStatus.TESTE)
    await c.com_vinculo(user, tenant)
    result = await c.login.execute("ana@b2.com", "senha123", "b2pro")
    assert result.tenant_slug == "b2pro"


async def test_refresh_reemite_par_de_tokens() -> None:
    c = Cenario()
    user = await c.com_usuario()
    tenant = await c.com_tenant()
    await c.com_vinculo(user, tenant, role=Role.ATENDENTE)
    login = await c.login.execute("ana@b2.com", "senha123", "b2pro")

    result = await c.refresh.execute(login.refresh_token)
    assert result.role is Role.ATENDENTE
    TOKENS.decode(result.access_token, expected_type="access")


async def test_refresh_rejeita_access_token() -> None:
    c = Cenario()
    await c.com_usuario(super_admin=True)
    login = await c.login.execute("ana@b2.com", "senha123", None)
    with pytest.raises(AuthError):
        await c.refresh.execute(login.access_token)


async def test_refresh_falha_se_usuario_desativado() -> None:
    c = Cenario()
    user = await c.com_usuario(super_admin=True)
    login = await c.login.execute("ana@b2.com", "senha123", None)
    user.active = False
    await c.users.update(user)
    with pytest.raises(AuthError):
        await c.refresh.execute(login.refresh_token)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_auth_use_cases.py -v`
Esperado: FAIL (ModuleNotFoundError em `sac.application.use_cases.auth`).

- [ ] **Step 4: Implementar `backend/src/sac/application/use_cases/auth.py`**

```python
from dataclasses import dataclass

from sac.application.ports import (
    PasswordHasherPort,
    TenantRepository,
    TokenServicePort,
    UserRepository,
    UserTenantRepository,
)
from sac.domain.entities import TenantStatus, User
from sac.domain.errors import AuthError
from sac.domain.permissions import Role

_LOGIN_FAILED = "credenciais invalidas"
_SESSION_INVALID = "sessao invalida"
_LOGIN_TENANT_STATUSES = (TenantStatus.ATIVA, TenantStatus.TESTE)


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    refresh_token: str
    user: User
    tenant_slug: str | None
    role: Role | None


class LoginUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
        hasher: PasswordHasherPort,
        tokens: TokenServicePort,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links
        self._hasher = hasher
        self._tokens = tokens

    async def execute(self, email: str, password: str, tenant_slug: str | None) -> AuthResult:
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or not user.active or not self._hasher.verify(
            user.password_hash, password
        ):
            raise AuthError(_LOGIN_FAILED)
        role: Role | None = None
        if tenant_slug:
            role = await _tenant_role(self._tenants, self._links, user, tenant_slug, _LOGIN_FAILED)
        elif not user.is_super_admin:
            raise AuthError(_LOGIN_FAILED)
        return _issue(self._tokens, user, tenant_slug or None, role)


class RefreshTokenUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
        tokens: TokenServicePort,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links
        self._tokens = tokens

    async def execute(self, refresh_token: str) -> AuthResult:
        payload = self._tokens.decode(refresh_token, expected_type="refresh")
        user = await self._users.get_by_id(payload.user_id)
        if user is None or not user.active:
            raise AuthError(_SESSION_INVALID)
        role: Role | None = None
        if payload.tenant_slug:
            role = await _tenant_role(
                self._tenants, self._links, user, payload.tenant_slug, _SESSION_INVALID
            )
        elif not user.is_super_admin:
            raise AuthError(_SESSION_INVALID)
        return _issue(self._tokens, user, payload.tenant_slug, role)


async def _tenant_role(
    tenants: TenantRepository,
    links: UserTenantRepository,
    user: User,
    slug: str,
    error_message: str,
) -> Role:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None or tenant.status not in _LOGIN_TENANT_STATUSES:
        raise AuthError(error_message)
    link = await links.get(user.id, tenant.id)
    if link is None or not link.active:
        raise AuthError(error_message)
    return link.role


def _issue(
    tokens: TokenServicePort, user: User, tenant_slug: str | None, role: Role | None
) -> AuthResult:
    access = tokens.create_access(user.id, tenant_slug, role, user.is_super_admin)
    refresh = tokens.create_refresh(user.id, tenant_slug, role, user.is_super_admin)
    return AuthResult(
        access_token=access,
        refresh_token=refresh,
        user=user,
        tenant_slug=tenant_slug,
        role=role,
    )
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/application -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/application backend/tests/unit
git commit -m "Adiciona use cases de login e refresh com fakes de teste"
```

---

### Task 9: Interface — app FastAPI, erros, rate limiter e router de auth

**Files:**
- Create: `backend/src/sac/interface/app.py`
- Create: `backend/src/sac/interface/errors.py`
- Create: `backend/src/sac/interface/rate_limit.py`
- Create: `backend/src/sac/interface/schemas.py`
- Create: `backend/src/sac/interface/deps.py`
- Create: `backend/src/sac/interface/routers/health.py`
- Create: `backend/src/sac/interface/routers/auth.py`
- Create: `backend/src/sac/main.py`
- Test: `backend/tests/unit/interface/test_rate_limit.py`, `backend/tests/integration/test_auth_api.py`, helpers em `backend/tests/integration/helpers.py`, fixtures `app`/`client` no `backend/tests/integration/conftest.py`

**Interfaces:**
- Consumes: use cases (Task 8), repositórios (Task 7), segurança/settings (Task 4), db (Task 5).
- Produces:
  - `create_app(settings: Settings | None = None) -> FastAPI` com `app.state.settings`, `app.state.engine`, `app.state.session_factory`, `app.state.login_limiter`; CORS a partir de `settings.cors_origins`; engine descartado no shutdown. `sac.main` expõe `app = create_app()` (rodar com `uv run uvicorn sac.main:app --reload`).
  - Handler único: `DomainError -> JSON {code, message, details}` com status por code: validation_error 422, not_found 404, conflict 409, permission_denied 403, auth_error 401, rate_limited 429, default 400.
  - `SlidingWindowRateLimiter(max_attempts=5, window_seconds=60.0, clock=time.monotonic)` com `check(key)` que levanta `RateLimitedError` (DomainError, code `rate_limited`).
  - Rotas: `GET /api/health` -> `{"status": "ok"}`; `POST /api/auth/login` (body `{email, password, tenant_slug?}`) -> `LoginOut`; `POST /api/auth/refresh` (body `{refresh_token}`) -> `LoginOut`.
  - `LoginOut = {access_token, refresh_token, token_type: "bearer", user: {id, name, email, is_super_admin, active}, tenant_slug, role}`.
  - Deps: `get_settings`, `get_session` (commit no sucesso, rollback no erro), `get_hasher`, `get_token_service`, `get_login_use_case`, `get_refresh_use_case`.
  - Helpers de integração: `seed_user`, `seed_tenant`, `seed_link`, `token_for` e fixtures `app`/`client`.

- [ ] **Step 1: Teste unitário do rate limiter (falha primeiro)**

`backend/tests/unit/interface/test_rate_limit.py`:

```python
import pytest

from sac.interface.rate_limit import RateLimitedError, SlidingWindowRateLimiter


def test_bloqueia_apos_o_limite_e_libera_depois_da_janela() -> None:
    now = 0.0
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60.0, clock=lambda: now)

    for _ in range(3):
        limiter.check("1.2.3.4:b2pro")
    with pytest.raises(RateLimitedError):
        limiter.check("1.2.3.4:b2pro")

    limiter.check("5.6.7.8:b2pro")  # outra chave nao e afetada

    now = 61.0
    limiter.check("1.2.3.4:b2pro")  # janela expirou
```

Run: `uv run pytest tests/unit/interface -v` — esperado FAIL. Implementar `backend/src/sac/interface/rate_limit.py`:

```python
import time
from collections import deque
from collections.abc import Callable

from sac.domain.errors import DomainError


class RateLimitedError(DomainError):
    code = "rate_limited"


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._max:
            raise RateLimitedError("muitas tentativas, aguarde um instante")
        hits.append(now)
```

Rodar de novo — esperado PASS.

- [ ] **Step 2: Implementar erros, schemas e deps**

`backend/src/sac/interface/errors.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sac.domain.errors import DomainError

STATUS_BY_CODE = {
    "validation_error": 422,
    "not_found": 404,
    "conflict": 409,
    "permission_denied": 403,
    "auth_error": 401,
    "rate_limited": 429,
}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_BY_CODE.get(exc.code, 400),
        content={"code": exc.code, "message": str(exc), "details": exc.details},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
```

`backend/src/sac/interface/schemas.py`:

```python
from uuid import UUID

from pydantic import BaseModel, EmailStr

from sac.application.use_cases.auth import AuthResult


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    is_super_admin: bool
    active: bool


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant_slug: str | None
    role: str | None


def login_out(result: AuthResult) -> LoginOut:
    return LoginOut(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=UserOut(
            id=result.user.id,
            name=result.user.name,
            email=result.user.email,
            is_super_admin=result.user.is_super_admin,
            active=result.user.active,
        ),
        tenant_slug=result.tenant_slug,
        role=result.role.value if result.role else None,
    )
```

`backend/src/sac/interface/deps.py` (primeira versão; a Task 10 acrescenta identidade e require_*):

```python
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def get_token_service(settings: Settings = Depends(get_settings)) -> JwtTokenService:
    return JwtTokenService.from_settings(settings)


def get_login_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
    tokens: JwtTokenService = Depends(get_token_service),
) -> LoginUseCase:
    return LoginUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        hasher,
        tokens,
    )


def get_refresh_use_case(
    session: AsyncSession = Depends(get_session),
    tokens: JwtTokenService = Depends(get_token_service),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        tokens,
    )
```

- [ ] **Step 3: Implementar routers, app e main**

`backend/src/sac/interface/routers/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

`backend/src/sac/interface/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, Request

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.interface.deps import get_login_use_case, get_refresh_use_case
from sac.interface.rate_limit import SlidingWindowRateLimiter
from sac.interface.schemas import LoginIn, LoginOut, RefreshIn, login_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    request: Request,
    use_case: LoginUseCase = Depends(get_login_use_case),
) -> LoginOut:
    limiter: SlidingWindowRateLimiter = request.app.state.login_limiter
    client_ip = request.client.host if request.client else "desconhecido"
    limiter.check(f"{client_ip}:{body.tenant_slug or ''}")
    result = await use_case.execute(body.email, body.password, body.tenant_slug)
    return login_out(result)


@router.post("/refresh", response_model=LoginOut)
async def refresh(
    body: RefreshIn,
    use_case: RefreshTokenUseCase = Depends(get_refresh_use_case),
) -> LoginOut:
    result = await use_case.execute(body.refresh_token)
    return login_out(result)
```

`backend/src/sac/interface/app.py`:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.settings import Settings
from sac.interface.errors import register_error_handlers
from sac.interface.rate_limit import SlidingWindowRateLimiter
from sac.interface.routers import auth, health


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="SAC-B2PRO", lifespan=_lifespan)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.login_limiter = SlidingWindowRateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    return app
```

`backend/src/sac/main.py`:

```python
from sac.interface.app import create_app

app = create_app()
```

- [ ] **Step 4: Helpers e fixtures de integração**

Acrescentar ao `backend/tests/integration/conftest.py`:

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sac.infrastructure.settings import Settings
from sac.interface.app import create_app


@pytest.fixture
async def app(engine: AsyncEngine, database: str) -> AsyncIterator[FastAPI]:
    application = create_app(Settings(database_url=database))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

`backend/tests/integration/helpers.py`:

```python
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.permissions import Role
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings

HASHER = Argon2PasswordHasher()
DEFAULT_PASSWORD = "senha-forte-123"
_PASSWORD_HASH = HASHER.hash(DEFAULT_PASSWORD)


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    name: str = "Usuario Teste",
    is_super_admin: bool = False,
    active: bool = True,
) -> User:
    user = User(
        id=uuid4(),
        name=name,
        email=email,
        password_hash=_PASSWORD_HASH,
        is_super_admin=is_super_admin,
        active=active,
    )
    await SqlUserRepository(session).add(user)
    await session.commit()
    return user


async def seed_tenant(
    session: AsyncSession,
    *,
    slug: str,
    status: TenantStatus = TenantStatus.ATIVA,
    modules: dict[str, bool] | None = None,
) -> Tenant:
    tenant = Tenant(id=uuid4(), slug=slug, name=slug.upper(), status=status, modules=modules or {})
    await SqlTenantRepository(session).add(tenant)
    await session.commit()
    return tenant


async def seed_link(
    session: AsyncSession,
    *,
    user: User,
    tenant: Tenant,
    role: Role = Role.ADMIN,
    active: bool = True,
) -> UserTenant:
    link = UserTenant(user_id=user.id, tenant_id=tenant.id, role=role, active=active)
    await SqlUserTenantRepository(session).add(link)
    await session.commit()
    return link


def token_for(
    user: User, *, tenant_slug: str | None = None, role: Role | None = None
) -> dict[str, str]:
    tokens = JwtTokenService.from_settings(Settings())
    access = tokens.create_access(user.id, tenant_slug, role, user.is_super_admin)
    return {"Authorization": f"Bearer {access}"}
```

- [ ] **Step 5: Escrever o teste de integração que falha**

`backend/tests/integration/test_auth_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import DEFAULT_PASSWORD, seed_link, seed_tenant, seed_user


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_login_completo(client: AsyncClient, session: AsyncSession) -> None:
    user = await seed_user(session, email="ana@b2.com")
    tenant = await seed_tenant(session, slug="b2pro")
    await seed_link(session, user=user, tenant=tenant)

    response = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": DEFAULT_PASSWORD, "tenant_slug": "b2pro"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    assert body["user"]["email"] == "ana@b2.com"

    refreshed = await client.post(
        "/api/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


async def test_login_com_senha_errada_retorna_401_padronizado(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await seed_user(session, email="ana@b2.com")
    tenant = await seed_tenant(session, slug="b2pro")
    await seed_link(session, user=user, tenant=tenant)

    response = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": "errada", "tenant_slug": "b2pro"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth_error"
    assert body["message"] == "credenciais invalidas"


async def test_rate_limit_no_login(client: AsyncClient, session: AsyncSession) -> None:
    await seed_user(session, email="ana@b2.com")
    payload = {"email": "ana@b2.com", "password": "errada", "tenant_slug": "b2pro"}

    for _ in range(5):
        await client.post("/api/auth/login", json=payload)
    response = await client.post("/api/auth/login", json=payload)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
```

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_auth_api.py -v`
Esperado: PASS.

- [ ] **Step 7: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests
git commit -m "Adiciona app FastAPI com handler de erros, rate limiter e rotas de auth"
```

---

### Task 10: Interface — identidade e dependencies de autorização

**Files:**
- Modify: `backend/src/sac/interface/deps.py` (acrescentar ao final)
- Test: `backend/tests/integration/test_authorization.py`

**Interfaces:**
- Consumes: `JwtTokenService`, `TokenPayload`, `Permission`, `has_permission`, `SqlTenantRepository` (tasks anteriores).
- Produces:
  - `get_current_identity(...) -> TokenPayload` (HTTPBearer com `auto_error=False`; sem credencial ou token invalido -> `AuthError` 401).
  - `require_super_admin(...) -> TokenPayload` (403 se não for super admin).
  - `require_permission(permission: Permission)` -> dependency que exige papel de tenant com a permissão (403 caso contrário).
  - `require_module(module: str)` -> dependency que carrega o tenant do JWT e exige `modules[module]` verdadeiro (403 caso contrário).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_authorization.py` (usa um router de teste montado só na fixture):

```python
from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Permission, Role
from sac.infrastructure.settings import Settings
from sac.interface.app import create_app
from sac.interface.deps import require_module, require_permission, require_super_admin
from tests.integration.helpers import seed_link, seed_tenant, seed_user

router = APIRouter(prefix="/api/teste")


@router.get("/plataforma", dependencies=[Depends(require_super_admin)])
async def rota_plataforma() -> dict[str, bool]:
    return {"ok": True}


@router.get("/decidir", dependencies=[Depends(require_permission(Permission.DECIDIR_TICKET))])
async def rota_decidir() -> dict[str, bool]:
    return {"ok": True}


@router.get("/modulo", dependencies=[Depends(require_module("tickets"))])
async def rota_modulo() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
async def guarded_client(engine: AsyncEngine, database: str) -> AsyncIterator[AsyncClient]:
    application: FastAPI = create_app(Settings(database_url=database))
    application.include_router(router)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await application.state.engine.dispose()


async def test_sem_token_retorna_401(guarded_client: AsyncClient) -> None:
    response = await guarded_client.get("/api/teste/plataforma")
    assert response.status_code == 401


async def test_super_admin_exigido(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    comum = await seed_user(session, email="comum@b2.com")
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)

    negado = await guarded_client.get("/api/teste/plataforma", headers=token_for(comum))
    permitido = await guarded_client.get("/api/teste/plataforma", headers=token_for(sa))

    assert negado.status_code == 403
    assert permitido.status_code == 200


async def test_permissao_por_papel(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    user = await seed_user(session, email="ana@b2.com")

    atendente = await guarded_client.get(
        "/api/teste/decidir", headers=token_for(user, tenant_slug="b2pro", role=Role.ATENDENTE)
    )
    supervisor = await guarded_client.get(
        "/api/teste/decidir", headers=token_for(user, tenant_slug="b2pro", role=Role.SUPERVISOR)
    )

    assert atendente.status_code == 403
    assert supervisor.status_code == 200


async def test_modulo_por_tenant(guarded_client: AsyncClient, session: AsyncSession) -> None:
    from tests.integration.helpers import token_for

    user = await seed_user(session, email="ana@b2.com")
    com_modulo = await seed_tenant(session, slug="com_mod", modules={"tickets": True})
    sem_modulo = await seed_tenant(session, slug="sem_mod", modules={})
    await seed_link(session, user=user, tenant=com_modulo)
    await seed_link(session, user=user, tenant=sem_modulo)

    permitido = await guarded_client.get(
        "/api/teste/modulo", headers=token_for(user, tenant_slug="com_mod", role=Role.ADMIN)
    )
    negado = await guarded_client.get(
        "/api/teste/modulo", headers=token_for(user, tenant_slug="sem_mod", role=Role.ADMIN)
    )

    assert permitido.status_code == 200
    assert negado.status_code == 403
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_authorization.py -v`
Esperado: FAIL (ImportError em require_super_admin).

- [ ] **Step 3: Acrescentar ao `backend/src/sac/interface/deps.py`**

Imports adicionais no topo do arquivo:

```python
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sac.application.ports import TokenPayload
from sac.domain.errors import AuthError, PermissionDeniedError
from sac.domain.permissions import Permission, has_permission
```

Funções ao final do arquivo:

```python
_bearer = HTTPBearer(auto_error=False)

IdentityDependency = Callable[..., Coroutine[Any, Any, TokenPayload]]


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    tokens: JwtTokenService = Depends(get_token_service),
) -> TokenPayload:
    if credentials is None:
        raise AuthError("credenciais ausentes")
    return tokens.decode(credentials.credentials, expected_type="access")


async def require_super_admin(
    identity: TokenPayload = Depends(get_current_identity),
) -> TokenPayload:
    if not identity.is_super_admin:
        raise PermissionDeniedError("acesso restrito ao painel da plataforma")
    return identity


def require_permission(permission: Permission) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
    ) -> TokenPayload:
        if identity.role is None or not has_permission(identity.role, permission):
            raise PermissionDeniedError("permissao insuficiente")
        return identity

    return dependency


def require_module(module: str) -> IdentityDependency:
    async def dependency(
        identity: TokenPayload = Depends(get_current_identity),
        session: AsyncSession = Depends(get_session),
    ) -> TokenPayload:
        if identity.tenant_slug is None:
            raise PermissionDeniedError("modulo indisponivel fora de um tenant")
        tenant = await SqlTenantRepository(session).get_by_slug(identity.tenant_slug)
        if tenant is None or not tenant.modules.get(module, False):
            raise PermissionDeniedError(f"modulo nao habilitado: {module}")
        return identity

    return dependency
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_authorization.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/interface/deps.py backend/tests/integration/test_authorization.py
git commit -m "Adiciona identidade JWT e dependencies de autorizacao por papel e modulo"
```

---

### Task 11: Plataforma — gestão de tenants (use cases + rotas)

**Files:**
- Create: `backend/src/sac/application/use_cases/platform_tenants.py`
- Create: `backend/src/sac/interface/routers/platform_tenants.py`
- Modify: `backend/src/sac/interface/schemas.py` (acrescentar schemas de tenant)
- Modify: `backend/src/sac/interface/deps.py` (factories dos use cases e do provisioner)
- Modify: `backend/src/sac/interface/app.py` (registrar router)
- Test: `backend/tests/unit/application/test_platform_tenants.py`, `backend/tests/integration/test_platform_tenants_api.py`

**Interfaces:**
- Consumes: ports, entidades, `validate_slug`, `AlembicTenantProvisioner`, `require_super_admin` (tasks anteriores).
- Produces:
  - `CreateTenantInput(slug, name, modules: dict[str, bool])` e `CreateTenantUseCase(tenants, provisioner)` com `execute(data) -> Tenant` (valida slug e nomes de módulo pela regex `^[a-z][a-z0-9_]{1,40}$`, conflito de slug, cria linha e provisiona `t_<slug>`).
  - `ListTenantsUseCase(tenants)` com `execute() -> list[Tenant]`.
  - `SetTenantStatusUseCase(tenants)` com `execute(tenant_id, status: TenantStatus) -> Tenant`.
  - `SetTenantModulesUseCase(tenants)` com `execute(tenant_id, modules: dict[str, bool]) -> Tenant`.
  - Rotas (todas sob `Depends(require_super_admin)`): `POST /api/platform/tenants` (201), `GET /api/platform/tenants`, `PATCH /api/platform/tenants/{tenant_id}/status`, `PUT /api/platform/tenants/{tenant_id}/modules`.
  - Schema `TenantOut = {id, slug, name, status, modules}`.

- [ ] **Step 1: Escrever os testes unitários que falham**

`backend/tests/unit/application/test_platform_tenants.py`:

```python
from uuid import uuid4

import pytest

from sac.application.use_cases.platform_tenants import (
    CreateTenantInput,
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.domain.entities import Tenant, TenantStatus
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from tests.unit.fakes import InMemoryTenantRepository


class FakeProvisioner:
    def __init__(self) -> None:
        self.provisioned: list[str] = []

    async def provision(self, schema_name: str) -> None:
        self.provisioned.append(schema_name)


async def test_criar_tenant_provisiona_schema() -> None:
    tenants = InMemoryTenantRepository()
    provisioner = FakeProvisioner()
    use_case = CreateTenantUseCase(tenants, provisioner)

    tenant = await use_case.execute(
        CreateTenantInput(slug="b2pro", name="B2PRO", modules={"tickets": True})
    )

    assert tenant.status is TenantStatus.ATIVA
    assert provisioner.provisioned == ["t_b2pro"]
    assert await tenants.get_by_slug("b2pro") is not None


async def test_slug_invalido_e_rejeitado_sem_provisionar() -> None:
    provisioner = FakeProvisioner()
    use_case = CreateTenantUseCase(InMemoryTenantRepository(), provisioner)
    with pytest.raises(ValidationError):
        await use_case.execute(CreateTenantInput(slug="Com-Hifen", name="X", modules={}))
    assert provisioner.provisioned == []


async def test_modulo_com_nome_invalido_e_rejeitado() -> None:
    use_case = CreateTenantUseCase(InMemoryTenantRepository(), FakeProvisioner())
    with pytest.raises(ValidationError):
        await use_case.execute(
            CreateTenantInput(slug="b2pro", name="X", modules={"Tickets!": True})
        )


async def test_slug_duplicado_gera_conflito() -> None:
    tenants = InMemoryTenantRepository()
    use_case = CreateTenantUseCase(tenants, FakeProvisioner())
    await use_case.execute(CreateTenantInput(slug="b2pro", name="X", modules={}))
    with pytest.raises(ConflictError):
        await use_case.execute(CreateTenantInput(slug="b2pro", name="Y", modules={}))


async def test_alterar_status_e_modulos() -> None:
    tenants = InMemoryTenantRepository()
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    await tenants.add(tenant)

    alterado = await SetTenantStatusUseCase(tenants).execute(tenant.id, TenantStatus.SUSPENSA)
    assert alterado.status is TenantStatus.SUSPENSA

    alterado = await SetTenantModulesUseCase(tenants).execute(tenant.id, {"tickets": False})
    assert alterado.modules == {"tickets": False}

    assert len(await ListTenantsUseCase(tenants).execute()) == 1


async def test_status_de_tenant_inexistente_gera_not_found() -> None:
    with pytest.raises(NotFoundError):
        await SetTenantStatusUseCase(InMemoryTenantRepository()).execute(
            uuid4(), TenantStatus.ATIVA
        )
```

Run: `uv run pytest tests/unit/application/test_platform_tenants.py -v` — esperado FAIL.

- [ ] **Step 2: Implementar `backend/src/sac/application/use_cases/platform_tenants.py`**

```python
import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sac.application.ports import TenantProvisionerPort, TenantRepository
from sac.domain.entities import Tenant, TenantStatus, validate_slug
from sac.domain.errors import ConflictError, NotFoundError, ValidationError

_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def _validate_modules(modules: dict[str, bool]) -> None:
    for key in modules:
        if not _MODULE_RE.fullmatch(key):
            raise ValidationError(f"nome de modulo invalido: {key}")


@dataclass(frozen=True)
class CreateTenantInput:
    slug: str
    name: str
    modules: dict[str, bool] = field(default_factory=dict)


class CreateTenantUseCase:
    def __init__(self, tenants: TenantRepository, provisioner: TenantProvisionerPort) -> None:
        self._tenants = tenants
        self._provisioner = provisioner

    async def execute(self, data: CreateTenantInput) -> Tenant:
        validate_slug(data.slug)
        _validate_modules(data.modules)
        if await self._tenants.get_by_slug(data.slug) is not None:
            raise ConflictError("slug ja cadastrado")
        tenant = Tenant(id=uuid4(), slug=data.slug, name=data.name, modules=dict(data.modules))
        await self._tenants.add(tenant)
        await self._provisioner.provision(tenant.schema_name)
        return tenant


class ListTenantsUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self) -> list[Tenant]:
        return await self._tenants.list_all()


class SetTenantStatusUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self, tenant_id: UUID, status: TenantStatus) -> Tenant:
        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant nao encontrado")
        tenant.status = status
        await self._tenants.update(tenant)
        return tenant


class SetTenantModulesUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self, tenant_id: UUID, modules: dict[str, bool]) -> Tenant:
        _validate_modules(modules)
        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("tenant nao encontrado")
        tenant.modules = dict(modules)
        await self._tenants.update(tenant)
        return tenant
```

Run: `uv run pytest tests/unit/application/test_platform_tenants.py -v` — esperado PASS.

- [ ] **Step 3: Escrever o teste de integração que falha**

`backend/tests/integration/test_platform_tenants_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.helpers import seed_user, token_for


async def test_crud_de_tenants_pelo_painel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    headers = token_for(sa)

    created = await client.post(
        "/api/platform/tenants",
        json={"slug": "b2pro", "name": "B2PRO", "modules": {"tickets": True}},
        headers=headers,
    )
    assert created.status_code == 201
    tenant = created.json()
    assert tenant["slug"] == "b2pro"

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 't_b2pro'")
        )
        assert result.scalar() == 1

    listed = await client.get("/api/platform/tenants", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    status = await client.patch(
        f"/api/platform/tenants/{tenant['id']}/status",
        json={"status": "suspensa"},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "suspensa"

    modules = await client.put(
        f"/api/platform/tenants/{tenant['id']}/modules",
        json={"modules": {"tickets": False, "cadastros": True}},
        headers=headers,
    )
    assert modules.status_code == 200
    assert modules.json()["modules"] == {"tickets": False, "cadastros": True}


async def test_slug_duplicado_retorna_409(client: AsyncClient, session: AsyncSession) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    headers = token_for(sa)
    payload = {"slug": "b2pro", "name": "B2PRO", "modules": {}}

    assert (await client.post("/api/platform/tenants", json=payload, headers=headers)).status_code == 201
    assert (await client.post("/api/platform/tenants", json=payload, headers=headers)).status_code == 409


async def test_nao_super_admin_recebe_403(client: AsyncClient, session: AsyncSession) -> None:
    comum = await seed_user(session, email="comum@b2.com")
    response = await client.get("/api/platform/tenants", headers=token_for(comum))
    assert response.status_code == 403
```

Run: `uv run pytest tests/integration/test_platform_tenants_api.py -v` — esperado FAIL (404).

- [ ] **Step 4: Schemas, deps e router**

Acrescentar em `backend/src/sac/interface/schemas.py`:

```python
from pydantic import Field

from sac.domain.entities import Tenant, TenantStatus


class TenantCreateIn(BaseModel):
    slug: str
    name: str
    modules: dict[str, bool] = Field(default_factory=dict)


class TenantStatusIn(BaseModel):
    status: TenantStatus


class TenantModulesIn(BaseModel):
    modules: dict[str, bool]


class TenantOut(BaseModel):
    id: UUID
    slug: str
    name: str
    status: TenantStatus
    modules: dict[str, bool]


def tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        modules=tenant.modules,
    )
```

Acrescentar em `backend/src/sac/interface/deps.py`:

```python
from sac.application.use_cases.platform_tenants import (
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.infrastructure.provisioning import AlembicTenantProvisioner


def get_tenant_provisioner(request: Request) -> AlembicTenantProvisioner:
    return AlembicTenantProvisioner(request.app.state.engine)


def get_create_tenant_use_case(
    session: AsyncSession = Depends(get_session),
    provisioner: AlembicTenantProvisioner = Depends(get_tenant_provisioner),
) -> CreateTenantUseCase:
    return CreateTenantUseCase(SqlTenantRepository(session), provisioner)


def get_list_tenants_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListTenantsUseCase:
    return ListTenantsUseCase(SqlTenantRepository(session))


def get_set_tenant_status_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetTenantStatusUseCase:
    return SetTenantStatusUseCase(SqlTenantRepository(session))


def get_set_tenant_modules_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetTenantModulesUseCase:
    return SetTenantModulesUseCase(SqlTenantRepository(session))
```

Criar `backend/src/sac/interface/routers/platform_tenants.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.platform_tenants import (
    CreateTenantInput,
    CreateTenantUseCase,
    ListTenantsUseCase,
    SetTenantModulesUseCase,
    SetTenantStatusUseCase,
)
from sac.interface.deps import (
    get_create_tenant_use_case,
    get_list_tenants_use_case,
    get_set_tenant_modules_use_case,
    get_set_tenant_status_use_case,
    require_super_admin,
)
from sac.interface.schemas import (
    TenantCreateIn,
    TenantModulesIn,
    TenantOut,
    TenantStatusIn,
    tenant_out,
)

router = APIRouter(
    prefix="/platform/tenants",
    tags=["platform"],
    dependencies=[Depends(require_super_admin)],
)


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreateIn,
    use_case: CreateTenantUseCase = Depends(get_create_tenant_use_case),
) -> TenantOut:
    tenant = await use_case.execute(
        CreateTenantInput(slug=body.slug, name=body.name, modules=body.modules)
    )
    return tenant_out(tenant)


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    use_case: ListTenantsUseCase = Depends(get_list_tenants_use_case),
) -> list[TenantOut]:
    return [tenant_out(t) for t in await use_case.execute()]


@router.patch("/{tenant_id}/status", response_model=TenantOut)
async def set_status(
    tenant_id: UUID,
    body: TenantStatusIn,
    use_case: SetTenantStatusUseCase = Depends(get_set_tenant_status_use_case),
) -> TenantOut:
    return tenant_out(await use_case.execute(tenant_id, body.status))


@router.put("/{tenant_id}/modules", response_model=TenantOut)
async def set_modules(
    tenant_id: UUID,
    body: TenantModulesIn,
    use_case: SetTenantModulesUseCase = Depends(get_set_tenant_modules_use_case),
) -> TenantOut:
    return tenant_out(await use_case.execute(tenant_id, body.modules))
```

Em `backend/src/sac/interface/app.py`, importar e registrar:

```python
from sac.interface.routers import auth, health, platform_tenants
...
    app.include_router(platform_tenants.router, prefix="/api")
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_platform_tenants_api.py tests/unit -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests
git commit -m "Adiciona gestao de tenants no painel da plataforma com provisionamento"
```

---

### Task 12: Plataforma — usuários globais e vínculos (use cases + rotas)

**Files:**
- Create: `backend/src/sac/application/use_cases/platform_users.py`
- Create: `backend/src/sac/interface/routers/platform_users.py`
- Modify: `backend/src/sac/interface/schemas.py`, `backend/src/sac/interface/deps.py`, `backend/src/sac/interface/app.py`, `backend/src/sac/interface/routers/platform_tenants.py` (rotas de vínculo)
- Test: `backend/tests/unit/application/test_platform_users.py`, `backend/tests/integration/test_platform_users_api.py`

**Interfaces:**
- Consumes: ports, fakes, `require_super_admin`, `Argon2PasswordHasher` (tasks anteriores).
- Produces:
  - `CreateUserInput(name, email, password, is_super_admin=False)`; `CreateUserUseCase(users, hasher)` (email normalizado, senha minima de 8 caracteres senão `ValidationError`, conflito de email).
  - `ListUsersUseCase(users)`; `SetUserActiveUseCase(users)` com `execute(user_id, active) -> User`; `ResetPasswordUseCase(users, hasher)` com `execute(user_id, new_password) -> None` (mesma regra de senha).
  - `LinkUserToTenantUseCase(users, tenants, links)` com `execute(user_id, tenant_id, role: Role) -> UserTenant` (`NotFoundError` se usuário/tenant não existem, `ConflictError` se vínculo já existe); `UnlinkUserFromTenantUseCase(links)`; `ListTenantLinksUseCase(links)` com `execute(tenant_id) -> list[UserTenant]`.
  - Rotas sob `require_super_admin`: `POST/GET /api/platform/users`, `PATCH /api/platform/users/{user_id}/active`, `POST /api/platform/users/{user_id}/password`, `POST/GET /api/platform/tenants/{tenant_id}/links`, `DELETE /api/platform/tenants/{tenant_id}/links/{user_id}`.
  - Schemas: `UserCreateIn(name, email: EmailStr, password, is_super_admin=False)`, `UserActiveIn(active: bool)`, `PasswordResetIn(password)`, `LinkCreateIn(user_id: UUID, role: Role)`, `LinkOut(user_id, tenant_id, role, active)`.

- [ ] **Step 1: Escrever os testes unitários que falham**

`backend/tests/unit/application/test_platform_users.py`:

```python
from uuid import uuid4

import pytest

from sac.application.use_cases.platform_users import (
    CreateUserInput,
    CreateUserUseCase,
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
    UnlinkUserFromTenantUseCase,
)
from sac.domain.entities import Tenant, User
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role
from tests.unit.fakes import (
    FakeHasher,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryUserTenantRepository,
)


async def test_criar_usuario_normaliza_email_e_faz_hash() -> None:
    users = InMemoryUserRepository()
    use_case = CreateUserUseCase(users, FakeHasher())

    user = await use_case.execute(
        CreateUserInput(name="Ana", email="  ANA@B2.com ", password="senha-forte")
    )

    assert user.email == "ana@b2.com"
    assert user.password_hash == "h:senha-forte"
    assert not user.is_super_admin


async def test_senha_curta_e_rejeitada() -> None:
    use_case = CreateUserUseCase(InMemoryUserRepository(), FakeHasher())
    with pytest.raises(ValidationError):
        await use_case.execute(CreateUserInput(name="Ana", email="a@b.com", password="curta"))


async def test_email_duplicado_gera_conflito() -> None:
    users = InMemoryUserRepository()
    use_case = CreateUserUseCase(users, FakeHasher())
    await use_case.execute(CreateUserInput(name="Ana", email="a@b.com", password="senha-forte"))
    with pytest.raises(ConflictError):
        await use_case.execute(
            CreateUserInput(name="Bia", email="a@b.com", password="senha-forte")
        )


async def test_ativar_desativar_e_resetar_senha() -> None:
    users = InMemoryUserRepository()
    user = User(id=uuid4(), name="Ana", email="a@b.com", password_hash="h:antiga")
    await users.add(user)

    alterado = await SetUserActiveUseCase(users).execute(user.id, False)
    assert alterado.active is False

    await ResetPasswordUseCase(users, FakeHasher()).execute(user.id, "nova-senha-forte")
    atualizado = await users.get_by_id(user.id)
    assert atualizado is not None and atualizado.password_hash == "h:nova-senha-forte"

    assert len(await ListUsersUseCase(users).execute()) == 1

    with pytest.raises(NotFoundError):
        await SetUserActiveUseCase(users).execute(uuid4(), True)


async def test_vinculos() -> None:
    users = InMemoryUserRepository()
    tenants = InMemoryTenantRepository()
    links = InMemoryUserTenantRepository()
    user = User(id=uuid4(), name="Ana", email="a@b.com", password_hash="h")
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    await users.add(user)
    await tenants.add(tenant)

    link_use_case = LinkUserToTenantUseCase(users, tenants, links)
    link = await link_use_case.execute(user.id, tenant.id, Role.SUPERVISOR)
    assert link.role is Role.SUPERVISOR

    with pytest.raises(ConflictError):
        await link_use_case.execute(user.id, tenant.id, Role.ADMIN)

    with pytest.raises(NotFoundError):
        await link_use_case.execute(uuid4(), tenant.id, Role.ADMIN)

    assert len(await ListTenantLinksUseCase(links).execute(tenant.id)) == 1

    await UnlinkUserFromTenantUseCase(links).execute(user.id, tenant.id)
    assert await links.get(user.id, tenant.id) is None
```

Run: `uv run pytest tests/unit/application/test_platform_users.py -v` — esperado FAIL.

- [ ] **Step 2: Implementar `backend/src/sac/application/use_cases/platform_users.py`**

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports import (
    PasswordHasherPort,
    TenantRepository,
    UserRepository,
    UserTenantRepository,
)
from sac.domain.entities import User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role

MIN_PASSWORD_LENGTH = 8


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres")


@dataclass(frozen=True)
class CreateUserInput:
    name: str
    email: str
    password: str
    is_super_admin: bool = False


class CreateUserUseCase:
    def __init__(self, users: UserRepository, hasher: PasswordHasherPort) -> None:
        self._users = users
        self._hasher = hasher

    async def execute(self, data: CreateUserInput) -> User:
        _validate_password(data.password)
        email = data.email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise ConflictError("email ja cadastrado")
        user = User(
            id=uuid4(),
            name=data.name,
            email=email,
            password_hash=self._hasher.hash(data.password),
            is_super_admin=data.is_super_admin,
        )
        await self._users.add(user)
        return user


class ListUsersUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self) -> list[User]:
        return await self._users.list_all()


class SetUserActiveUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: UUID, active: bool) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("usuario nao encontrado")
        user.active = active
        await self._users.update(user)
        return user


class ResetPasswordUseCase:
    def __init__(self, users: UserRepository, hasher: PasswordHasherPort) -> None:
        self._users = users
        self._hasher = hasher

    async def execute(self, user_id: UUID, new_password: str) -> None:
        _validate_password(new_password)
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("usuario nao encontrado")
        user.password_hash = self._hasher.hash(new_password)
        await self._users.update(user)


class LinkUserToTenantUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links

    async def execute(self, user_id: UUID, tenant_id: UUID, role: Role) -> UserTenant:
        if await self._users.get_by_id(user_id) is None:
            raise NotFoundError("usuario nao encontrado")
        if await self._tenants.get_by_id(tenant_id) is None:
            raise NotFoundError("tenant nao encontrado")
        link = UserTenant(user_id=user_id, tenant_id=tenant_id, role=role)
        await self._links.add(link)
        return link


class UnlinkUserFromTenantUseCase:
    def __init__(self, links: UserTenantRepository) -> None:
        self._links = links

    async def execute(self, user_id: UUID, tenant_id: UUID) -> None:
        await self._links.remove(user_id, tenant_id)


class ListTenantLinksUseCase:
    def __init__(self, links: UserTenantRepository) -> None:
        self._links = links

    async def execute(self, tenant_id: UUID) -> list[UserTenant]:
        return await self._links.list_for_tenant(tenant_id)
```

Run: `uv run pytest tests/unit/application/test_platform_users.py -v` — esperado PASS.

- [ ] **Step 3: Escrever o teste de integração que falha**

`backend/tests/integration/test_platform_users_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import DEFAULT_PASSWORD, seed_tenant, seed_user, token_for


async def test_fluxo_de_usuarios_e_vinculos(client: AsyncClient, session: AsyncSession) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    tenant = await seed_tenant(session, slug="b2pro")
    headers = token_for(sa)

    created = await client.post(
        "/api/platform/users",
        json={"name": "Ana", "email": "ana@b2.com", "password": "senha-forte-123"},
        headers=headers,
    )
    assert created.status_code == 201
    user = created.json()

    listed = await client.get("/api/platform/users", headers=headers)
    assert listed.status_code == 200
    assert {u["email"] for u in listed.json()} == {"ana@b2.com", "sa@b2.com"}

    linked = await client.post(
        f"/api/platform/tenants/{tenant.id}/links",
        json={"user_id": user["id"], "role": "atendente"},
        headers=headers,
    )
    assert linked.status_code == 201
    assert linked.json()["role"] == "atendente"

    links = await client.get(f"/api/platform/tenants/{tenant.id}/links", headers=headers)
    assert links.status_code == 200 and len(links.json()) == 1

    login = await client.post(
        "/api/auth/login",
        json={"email": "ana@b2.com", "password": "senha-forte-123", "tenant_slug": "b2pro"},
    )
    assert login.status_code == 200 and login.json()["role"] == "atendente"

    unlinked = await client.delete(
        f"/api/platform/tenants/{tenant.id}/links/{user['id']}", headers=headers
    )
    assert unlinked.status_code == 204

    deactivated = await client.patch(
        f"/api/platform/users/{user['id']}/active", json={"active": False}, headers=headers
    )
    assert deactivated.status_code == 200 and deactivated.json()["active"] is False

    reset = await client.post(
        f"/api/platform/users/{user['id']}/password",
        json={"password": "outra-senha-forte"},
        headers=headers,
    )
    assert reset.status_code == 204


async def test_criacao_de_usuario_exige_super_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    comum = await seed_user(session, email="comum@b2.com")
    response = await client.post(
        "/api/platform/users",
        json={"name": "X", "email": "x@b2.com", "password": DEFAULT_PASSWORD},
        headers=token_for(comum),
    )
    assert response.status_code == 403
```

Run: `uv run pytest tests/integration/test_platform_users_api.py -v` — esperado FAIL (404).

- [ ] **Step 4: Schemas, deps e routers**

Acrescentar em `backend/src/sac/interface/schemas.py`:

```python
from sac.domain.permissions import Role


class UserCreateIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    is_super_admin: bool = False


class UserActiveIn(BaseModel):
    active: bool


class PasswordResetIn(BaseModel):
    password: str


class LinkCreateIn(BaseModel):
    user_id: UUID
    role: Role


class LinkOut(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: Role
    active: bool
```

Acrescentar em `backend/src/sac/interface/deps.py` as factories (mesmo padrão das anteriores): `get_create_user_use_case` (users + hasher), `get_list_users_use_case`, `get_set_user_active_use_case`, `get_reset_password_use_case` (users + hasher), `get_link_use_case` (users + tenants + links), `get_unlink_use_case` (links), `get_list_links_use_case` (links). Exemplo:

```python
from sac.application.use_cases.platform_users import (
    CreateUserUseCase,
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
    UnlinkUserFromTenantUseCase,
)


def get_create_user_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
) -> CreateUserUseCase:
    return CreateUserUseCase(SqlUserRepository(session), hasher)


def get_list_users_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListUsersUseCase:
    return ListUsersUseCase(SqlUserRepository(session))


def get_set_user_active_use_case(
    session: AsyncSession = Depends(get_session),
) -> SetUserActiveUseCase:
    return SetUserActiveUseCase(SqlUserRepository(session))


def get_reset_password_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
) -> ResetPasswordUseCase:
    return ResetPasswordUseCase(SqlUserRepository(session), hasher)


def get_link_use_case(
    session: AsyncSession = Depends(get_session),
) -> LinkUserToTenantUseCase:
    return LinkUserToTenantUseCase(
        SqlUserRepository(session), SqlTenantRepository(session), SqlUserTenantRepository(session)
    )


def get_unlink_use_case(
    session: AsyncSession = Depends(get_session),
) -> UnlinkUserFromTenantUseCase:
    return UnlinkUserFromTenantUseCase(SqlUserTenantRepository(session))


def get_list_links_use_case(
    session: AsyncSession = Depends(get_session),
) -> ListTenantLinksUseCase:
    return ListTenantLinksUseCase(SqlUserTenantRepository(session))
```

Criar `backend/src/sac/interface/routers/platform_users.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.platform_users import (
    CreateUserInput,
    CreateUserUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
)
from sac.interface.deps import (
    get_create_user_use_case,
    get_list_users_use_case,
    get_reset_password_use_case,
    get_set_user_active_use_case,
    require_super_admin,
)
from sac.interface.schemas import PasswordResetIn, UserActiveIn, UserCreateIn, UserOut

router = APIRouter(
    prefix="/platform/users",
    tags=["platform"],
    dependencies=[Depends(require_super_admin)],
)


def _user_out(user: object) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateIn,
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
) -> UserOut:
    user = await use_case.execute(
        CreateUserInput(
            name=body.name,
            email=body.email,
            password=body.password,
            is_super_admin=body.is_super_admin,
        )
    )
    return _user_out(user)


@router.get("", response_model=list[UserOut])
async def list_users(
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
) -> list[UserOut]:
    return [_user_out(u) for u in await use_case.execute()]


@router.patch("/{user_id}/active", response_model=UserOut)
async def set_active(
    user_id: UUID,
    body: UserActiveIn,
    use_case: SetUserActiveUseCase = Depends(get_set_user_active_use_case),
) -> UserOut:
    return _user_out(await use_case.execute(user_id, body.active))


@router.post("/{user_id}/password", status_code=204)
async def reset_password(
    user_id: UUID,
    body: PasswordResetIn,
    use_case: ResetPasswordUseCase = Depends(get_reset_password_use_case),
) -> None:
    await use_case.execute(user_id, body.password)
```

Acrescentar ao `backend/src/sac/interface/routers/platform_tenants.py`:

```python
from sac.application.use_cases.platform_users import (
    LinkUserToTenantUseCase,
    ListTenantLinksUseCase,
    UnlinkUserFromTenantUseCase,
)
from sac.interface.deps import get_link_use_case, get_list_links_use_case, get_unlink_use_case
from sac.interface.schemas import LinkCreateIn, LinkOut


@router.post("/{tenant_id}/links", response_model=LinkOut, status_code=201)
async def create_link(
    tenant_id: UUID,
    body: LinkCreateIn,
    use_case: LinkUserToTenantUseCase = Depends(get_link_use_case),
) -> LinkOut:
    link = await use_case.execute(body.user_id, tenant_id, body.role)
    return LinkOut(
        user_id=link.user_id, tenant_id=link.tenant_id, role=link.role, active=link.active
    )


@router.get("/{tenant_id}/links", response_model=list[LinkOut])
async def list_links(
    tenant_id: UUID,
    use_case: ListTenantLinksUseCase = Depends(get_list_links_use_case),
) -> list[LinkOut]:
    return [
        LinkOut(user_id=x.user_id, tenant_id=x.tenant_id, role=x.role, active=x.active)
        for x in await use_case.execute(tenant_id)
    ]


@router.delete("/{tenant_id}/links/{user_id}", status_code=204)
async def delete_link(
    tenant_id: UUID,
    user_id: UUID,
    use_case: UnlinkUserFromTenantUseCase = Depends(get_unlink_use_case),
) -> None:
    await use_case.execute(user_id, tenant_id)
```

Em `backend/src/sac/interface/app.py`, registrar `platform_users.router` com `prefix="/api"`.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_platform_users_api.py tests/unit -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests
git commit -m "Adiciona gestao de usuarios globais e vinculos no painel da plataforma"
```

---

### Task 13: Seed do super admin (CLI)

**Files:**
- Create: `backend/src/sac/infrastructure/seed.py`
- Test: `backend/tests/integration/test_seed.py`

**Interfaces:**
- Consumes: `Settings` (campos `seed_admin_name/email/password`), `build_engine`/`build_session_factory`, `SqlUserRepository`, `Argon2PasswordHasher`, `CreateUserUseCase`.
- Produces: `seed_super_admin(settings) -> str` (mensagem de resultado; idempotente) e CLI `python -m sac.infrastructure.seed`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_seed.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.infrastructure.repositories import SqlUserRepository
from sac.infrastructure.seed import seed_super_admin
from sac.infrastructure.settings import Settings


async def test_seed_cria_super_admin_uma_unica_vez(
    engine: AsyncEngine, session: AsyncSession, database: str
) -> None:
    settings = Settings(
        database_url=database,
        seed_admin_email="root@b2pro.com",
        seed_admin_password="senha-forte-123",
    )

    primeira = await seed_super_admin(settings)
    segunda = await seed_super_admin(settings)

    assert "criado" in primeira
    assert "ja existe" in segunda

    user = await SqlUserRepository(session).get_by_email("root@b2pro.com")
    assert user is not None and user.is_super_admin


async def test_seed_sem_credenciais_orienta_configuracao(database: str) -> None:
    settings = Settings(database_url=database, seed_admin_email="", seed_admin_password="")
    resultado = await seed_super_admin(settings)
    assert "SAC_SEED_ADMIN_EMAIL" in resultado
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_seed.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/infrastructure/seed.py`**

```python
import asyncio

from sac.application.use_cases.platform_users import CreateUserInput, CreateUserUseCase
from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.repositories import SqlUserRepository
from sac.infrastructure.security import Argon2PasswordHasher
from sac.infrastructure.settings import Settings


async def seed_super_admin(settings: Settings) -> str:
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return "configure SAC_SEED_ADMIN_EMAIL e SAC_SEED_ADMIN_PASSWORD no .env"
    engine = build_engine(settings.database_url)
    try:
        factory = build_session_factory(engine)
        async with factory() as session:
            users = SqlUserRepository(session)
            email = settings.seed_admin_email.strip().lower()
            if await users.get_by_email(email) is not None:
                return f"super admin ja existe: {email}"
            await CreateUserUseCase(users, Argon2PasswordHasher()).execute(
                CreateUserInput(
                    name=settings.seed_admin_name,
                    email=email,
                    password=settings.seed_admin_password,
                    is_super_admin=True,
                )
            )
            await session.commit()
            return f"super admin criado: {email}"
    finally:
        await engine.dispose()


def main() -> None:
    print(asyncio.run(seed_super_admin(Settings())))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_seed.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure/seed.py backend/tests/integration/test_seed.py
git commit -m "Adiciona seed idempotente do super admin"
```

---

### Task 14: Frontend — scaffold Vite + Tailwind 4 + shadcn/ui + tokens da identidade visual

Antes de qualquer passo desta task, invocar o skill `frontend-design` e reler `docs/identidade-visual.md`.

**Files:**
- Create: `frontend/` (template Vite react-ts via pnpm)
- Create/Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/components.json`, `frontend/src/index.css`, `frontend/src/App.tsx`
- Delete: `frontend/src/App.css`, `frontend/src/assets/react.svg`, `frontend/public/vite.svg`

**Interfaces:**
- Consumes: identidade visual (`docs/identidade-visual.md`).
- Produces: projeto front com alias `@ -> src`, proxy `/api -> http://localhost:8000`, tokens CSS da paleta, fontes Public Sans Variable e JetBrains Mono Variable, componentes shadcn/ui instalados (button, card, input, label, table, dialog, select, dropdown-menu, badge, switch, sonner, checkbox). Comandos: `pnpm dev`, `pnpm lint`, `pnpm build`.

- [ ] **Step 1: Criar o projeto**

Na raiz do repo:

```bash
pnpm create vite@latest frontend --template react-ts
cd frontend
pnpm install
pnpm add tailwindcss @tailwindcss/vite lucide-react @tanstack/react-query react-router-dom
pnpm add @fontsource-variable/public-sans @fontsource-variable/jetbrains-mono
pnpm add -D @types/node
```

- [ ] **Step 2: Configurar alias e proxy**

`frontend/vite.config.ts`:

```ts
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import path from "node:path"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
})
```

Em `frontend/tsconfig.app.json`, dentro de `compilerOptions`, acrescentar:

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

Acrescentar o mesmo bloco `compilerOptions` com `baseUrl`/`paths` no `frontend/tsconfig.json` (nivel raiz do arquivo, junto de `references`), pois o shadcn CLI le esse arquivo.

- [ ] **Step 3: Inicializar shadcn/ui**

Criar `frontend/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

Substituir `frontend/src/index.css` por um arquivo mínimo antes do CLI (o CLI espera `@import "tailwindcss"`):

```css
@import "tailwindcss";
```

Rodar:

```bash
pnpm dlx shadcn@latest add button card input label table dialog select dropdown-menu badge switch sonner checkbox
```

Esperado: componentes em `src/components/ui/` e `src/lib/utils.ts` criados.

- [ ] **Step 4: Aplicar os tokens da identidade visual**

Substituir `frontend/src/index.css` por:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "@fontsource-variable/public-sans";
@import "@fontsource-variable/jetbrains-mono";

@custom-variant dark (&:is(.dark *));

:root {
  --background: #fffcf2;
  --foreground: #403d39;
  --card: #fffcf2;
  --card-foreground: #403d39;
  --popover: #fffcf2;
  --popover-foreground: #403d39;
  --primary: #eb5e28;
  --primary-foreground: #fffcf2;
  --secondary: #ece7da;
  --secondary-foreground: #403d39;
  --muted: #ece7da;
  --muted-foreground: #736e66;
  --accent: #ece7da;
  --accent-foreground: #252422;
  --destructive: #b3261e;
  --destructive-foreground: #fffcf2;
  --border: #ccc5b9;
  --input: #ccc5b9;
  --ring: #403d39;
  --radius: 0.3125rem;
  --sidebar: #252422;
  --sidebar-foreground: #ccc5b9;
  --sidebar-primary: #eb5e28;
  --sidebar-primary-foreground: #fffcf2;
  --sidebar-accent: #403d39;
  --sidebar-accent-foreground: #fffcf2;
  --sidebar-border: #403d39;
  --sidebar-ring: #eb5e28;
}

.dark {
  --background: #252422;
  --foreground: #ccc5b9;
  --card: #2e2c29;
  --card-foreground: #ccc5b9;
  --popover: #2e2c29;
  --popover-foreground: #ccc5b9;
  --primary: #eb5e28;
  --primary-foreground: #fffcf2;
  --secondary: #403d39;
  --secondary-foreground: #ccc5b9;
  --muted: #403d39;
  --muted-foreground: #8d877d;
  --accent: #403d39;
  --accent-foreground: #fffcf2;
  --destructive: #d64545;
  --destructive-foreground: #fffcf2;
  --border: #403d39;
  --input: #403d39;
  --ring: #ccc5b9;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);
  --font-sans: "Public Sans Variable", system-ui, sans-serif;
  --font-mono: "JetBrains Mono Variable", ui-monospace, monospace;
  --radius-sm: calc(var(--radius) - 2px);
  --radius-md: var(--radius);
  --radius-lg: calc(var(--radius) + 2px);
  --radius-xl: calc(var(--radius) + 4px);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground font-sans;
  }
}
```

Se o `pnpm dlx shadcn` não tiver instalado `tw-animate-css`, rodar `pnpm add tw-animate-css`.

Regras da identidade que valem para todo o front: zero drop-shadow decorativo (remover classes `shadow-*` dos componentes shadcn copiados quando aparecerem em card/dialog), foco/hover muda a cor da borda para `--foreground`, Paprika somente em ação primária/alerta, classe `font-mono` em todo dado técnico (slug, email em tabelas, códigos).

- [ ] **Step 5: Limpar o template**

Substituir `frontend/src/App.tsx` por:

```tsx
export default function App() {
  return <p className="p-8">SAC-B2PRO</p>
}
```

Remover `frontend/src/App.css`, `frontend/src/assets/react.svg` e `frontend/public/vite.svg`; remover os imports correspondentes em `main.tsx`/`index.html`.

- [ ] **Step 6: Verificar e commitar**

Em `frontend/`: `pnpm lint && pnpm build` — esperado: sucesso.
Conferir visualmente com `pnpm dev`: página com fundo Floral White e fonte Public Sans.

```bash
git add frontend
git commit -m "Cria frontend Vite com Tailwind 4, shadcn/ui e tokens da identidade visual"
```

---

### Task 15: Frontend — cliente de API, sessão e tela de login

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md`.

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/auth.tsx`
- Create: `frontend/src/lib/guards.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/main.tsx`
- Delete: `frontend/src/App.tsx` (substituído pelo router)

**Interfaces:**
- Consumes: rotas `/api/auth/login` e `/api/auth/refresh` (Task 9).
- Produces:
  - `api<T>(path, {method?, body?}) -> Promise<T>`: prefixa `/api`, envia JSON, anexa Bearer, tenta 1 refresh em 401 e redireciona para `/login` se falhar; lança `ApiError(status, code, message, details)`.
  - `Session = {accessToken, refreshToken, user: {id, name, email, is_super_admin, active}, tenantSlug, role}`; `loadSession/saveSession(session, remember)/clearSession` (localStorage quando "manter sessão", senão sessionStorage; chave `sac.session`).
  - `AuthProvider` + `useAuth() -> {session, login(input), logout()}`.
  - Guards `RequireAuth` e `RequireSuperAdmin` (redirecionam para `/login` e `/`).
  - Rotas: `/login`, `/` (protegida).

- [ ] **Step 1: Implementar `frontend/src/lib/api.ts`**

```ts
export type SessionUser = {
  id: string
  name: string
  email: string
  is_super_admin: boolean
  active: boolean
}

export type Session = {
  accessToken: string
  refreshToken: string
  user: SessionUser
  tenantSlug: string | null
  role: string | null
}

export type LoginResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user: SessionUser
  tenant_slug: string | null
  role: string | null
}

const KEY = "sac.session"

export function loadSession(): Session | null {
  const raw = sessionStorage.getItem(KEY) ?? localStorage.getItem(KEY)
  return raw ? (JSON.parse(raw) as Session) : null
}

export function saveSession(session: Session, remember: boolean): void {
  clearSession()
  const target = remember ? localStorage : sessionStorage
  target.setItem(KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(KEY)
  sessionStorage.removeItem(KEY)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message)
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as { code?: string; message?: string; details?: unknown }
    return new ApiError(res.status, body.code ?? "erro", body.message ?? res.statusText, body.details)
  } catch {
    return new ApiError(res.status, "erro", res.statusText)
  }
}

async function tryRefresh(): Promise<Session | null> {
  const current = loadSession()
  if (!current) return null
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: current.refreshToken }),
  })
  if (!res.ok) {
    clearSession()
    return null
  }
  const data = (await res.json()) as LoginResponse
  const remember = localStorage.getItem(KEY) != null
  const next: Session = {
    ...current,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  }
  saveSession(next, remember)
  return next
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const doFetch = (token: string | null) =>
    fetch(`/api${path}`, {
      method: init.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    })

  let session = loadSession()
  let res = await doFetch(session?.accessToken ?? null)
  if (res.status === 401 && session) {
    session = await tryRefresh()
    if (!session) {
      window.location.assign("/login")
      throw new ApiError(401, "auth_error", "sessao expirada")
    }
    res = await doFetch(session.accessToken)
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
```

- [ ] **Step 2: Implementar `frontend/src/lib/auth.tsx`**

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from "react"

import {
  api,
  clearSession,
  loadSession,
  saveSession,
  type LoginResponse,
  type Session,
} from "@/lib/api"

type LoginInput = {
  email: string
  password: string
  tenantSlug: string
  remember: boolean
}

type AuthContextValue = {
  session: Session | null
  login: (input: LoginInput) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(loadSession)

  const login = useCallback(async (input: LoginInput) => {
    const data = await api<LoginResponse>("/auth/login", {
      method: "POST",
      body: {
        email: input.email,
        password: input.password,
        tenant_slug: input.tenantSlug || null,
      },
    })
    const next: Session = {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: data.user,
      tenantSlug: data.tenant_slug,
      role: data.role,
    }
    saveSession(next, input.remember)
    setSession(next)
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setSession(null)
  }, [])

  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth fora do AuthProvider")
  return ctx
}
```

- [ ] **Step 3: Implementar `frontend/src/lib/guards.tsx`**

```tsx
import { Navigate, Outlet } from "react-router-dom"

import { useAuth } from "@/lib/auth"

export function RequireAuth() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RequireSuperAdmin() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (!session.user.is_super_admin) return <Navigate to="/" replace />
  return <Outlet />
}
```

- [ ] **Step 4: Implementar `frontend/src/pages/LoginPage.tsx`**

Estrutura funcional (o refinamento visual segue o skill frontend-design e a identidade):

```tsx
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [tenantSlug, setTenantSlug] = useState("")
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    try {
      await login({ email, password, tenantSlug, remember })
      navigate("/")
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "erro inesperado ao entrar"
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>SAC-B2PRO</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="tenant">Organizacao (slug)</Label>
              <Input
                id="tenant"
                className="font-mono"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
                placeholder="vazio para painel da plataforma"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Senha</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="remember"
                checked={remember}
                onCheckedChange={(checked) => setRemember(checked === true)}
              />
              <Label htmlFor="remember">Manter sessao</Label>
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Entrando..." : "Entrar"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
```

- [ ] **Step 5: Montar o router em `frontend/src/main.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router-dom"
import { Toaster } from "sonner"

import { AuthProvider } from "@/lib/auth"
import { RequireAuth } from "@/lib/guards"
import LoginPage from "@/pages/LoginPage"
import "./index.css"

const queryClient = new QueryClient()

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [{ path: "/", element: <p className="p-8">Bem-vindo ao SAC-B2PRO</p> }],
  },
])

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
        <Toaster position="top-right" />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
```

Remover `frontend/src/App.tsx`. Ajustar `index.html`: `<title>SAC-B2PRO</title>` e `<html lang="pt-BR">`.

- [ ] **Step 6: Verificar e commitar**

Backend de pé (`uv run uvicorn sac.main:app --reload` com banco migrado e seed feito), `pnpm dev`, testar login com o super admin do seed (slug vazio) e um login com erro (toast com "credenciais invalidas").
Em `frontend/`: `pnpm lint && pnpm build` — esperado sucesso.

```bash
git add frontend
git commit -m "Adiciona cliente de API, sessao com refresh e tela de login"
```

---

### Task 16: Frontend — shell da aplicação (sidebar escura + header)

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md` (sidebar em Carbon Black, indicador ativo Paprika sólido de 2px sem blur, ícones lucide strokeWidth 1.5).

**Files:**
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/Header.tsx`
- Modify: `frontend/src/main.tsx` (rotas protegidas dentro do shell)

**Interfaces:**
- Consumes: `useAuth` (Task 15).
- Produces: `AppShell` (layout com `<Outlet />`), `Sidebar` com grupos de navegação derivados da sessão (super admin ve o grupo "Plataforma": Tenants e Usuários), `Header` com menu do usuário (nome, email em `font-mono`, item "Sair" que chama `logout()` e navega para `/login`).

- [ ] **Step 1: Implementar `Sidebar.tsx`**

```tsx
import { Building2, Users } from "lucide-react"
import { NavLink } from "react-router-dom"

import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth"

type NavItem = { to: string; label: string; icon: typeof Building2 }

export function Sidebar() {
  const { session } = useAuth()

  const groups: { label: string; items: NavItem[] }[] = []
  if (session?.user.is_super_admin) {
    groups.push({
      label: "Plataforma",
      items: [
        { to: "/plataforma/tenants", label: "Tenants", icon: Building2 },
        { to: "/plataforma/usuarios", label: "Usuarios", icon: Users },
      ],
    })
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="border-b border-sidebar-border px-4 py-4 text-sm font-semibold tracking-wide text-sidebar-accent-foreground">
        SAC B2PRO
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {groups.map((group) => (
          <div key={group.label} className="mb-4">
            <p className="px-4 py-2 text-xs uppercase tracking-wider text-sidebar-foreground/60">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 border-l-2 border-transparent px-4 py-2 text-sm",
                    "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    isActive &&
                      "border-sidebar-primary bg-sidebar-accent text-sidebar-accent-foreground",
                  )
                }
              >
                <item.icon size={20} strokeWidth={1.5} />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 2: Implementar `Header.tsx`**

```tsx
import { ChevronDown, LogOut } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth"

export function Header() {
  const { session, logout } = useAuth()
  const navigate = useNavigate()

  function onLogout() {
    logout()
    navigate("/login")
  }

  return (
    <header className="flex h-14 items-center justify-end border-b border-border bg-background px-4">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2">
            {session?.user.name}
            <ChevronDown size={16} strokeWidth={1.5} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel className="font-mono text-xs">
            {session?.user.email}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onLogout}>
            <LogOut size={16} strokeWidth={1.5} />
            Sair
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
```

- [ ] **Step 3: Implementar `AppShell.tsx` e atualizar rotas**

```tsx
import { Outlet } from "react-router-dom"

import { Header } from "@/components/layout/Header"
import { Sidebar } from "@/components/layout/Sidebar"

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

Em `main.tsx`, a rota protegida passa a usar o shell:

```tsx
import { AppShell } from "@/components/layout/AppShell"

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <p>Bem-vindo ao SAC-B2PRO</p> },
        ],
      },
    ],
  },
])
```

- [ ] **Step 4: Verificar e commitar**

`pnpm dev` com backend de pé: logar como super admin, ver sidebar escura com grupo Plataforma e menu do usuário funcionando (Sair volta ao login).
Em `frontend/`: `pnpm lint && pnpm build` — esperado sucesso.

```bash
git add frontend
git commit -m "Adiciona shell da aplicacao com sidebar escura e header"
```

---

### Task 17: Frontend — painel da plataforma: tenants

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md` (tabela densa, slug em `font-mono`, badge de status neutro em Silver, Paprika só no botão primário "Novo tenant").

**Files:**
- Create: `frontend/src/lib/platform.ts`
- Create: `frontend/src/pages/platform/TenantsPage.tsx`
- Modify: `frontend/src/main.tsx` (rota `/plataforma/tenants` sob `RequireSuperAdmin`)

**Interfaces:**
- Consumes: rotas de tenants (Task 11), `api` (Task 15), shell (Task 16).
- Produces:
  - Tipos e funções: `Tenant = {id, slug, name, status, modules}`; `listTenants()`, `createTenant({slug, name, modules?})`, `setTenantStatus(id, status)`, `setTenantModules(id, modules)`; tipos de vínculo usados na Task 18: `LinkOut = {user_id, tenant_id, role, active}`, `listLinks(tenantId)`, `createLink(tenantId, {user_id, role})`, `deleteLink(tenantId, userId)`.
  - Página com tabela (slug, nome, status, módulos ativos, ações), dialog de criação, ação de alterar status e dialog de módulos (switch por módulo conhecido: `cadastros`, `tickets`, `relatorios`, `galeria`, `notificacoes`).

- [ ] **Step 1: Implementar `frontend/src/lib/platform.ts`**

```ts
import { api } from "@/lib/api"

export type TenantStatus = "ativa" | "teste" | "suspensa" | "inativa"

export type Tenant = {
  id: string
  slug: string
  name: string
  status: TenantStatus
  modules: Record<string, boolean>
}

export type PlatformUser = {
  id: string
  name: string
  email: string
  is_super_admin: boolean
  active: boolean
}

export type TenantLink = {
  user_id: string
  tenant_id: string
  role: "admin" | "supervisor" | "atendente" | "visualizador"
  active: boolean
}

export const KNOWN_MODULES = ["cadastros", "tickets", "relatorios", "galeria", "notificacoes"]

export const listTenants = () => api<Tenant[]>("/platform/tenants")

export const createTenant = (input: {
  slug: string
  name: string
  modules?: Record<string, boolean>
}) => api<Tenant>("/platform/tenants", { method: "POST", body: input })

export const setTenantStatus = (id: string, status: TenantStatus) =>
  api<Tenant>(`/platform/tenants/${id}/status`, { method: "PATCH", body: { status } })

export const setTenantModules = (id: string, modules: Record<string, boolean>) =>
  api<Tenant>(`/platform/tenants/${id}/modules`, { method: "PUT", body: { modules } })

export const listUsers = () => api<PlatformUser[]>("/platform/users")

export const createUser = (input: {
  name: string
  email: string
  password: string
  is_super_admin?: boolean
}) => api<PlatformUser>("/platform/users", { method: "POST", body: input })

export const setUserActive = (id: string, active: boolean) =>
  api<PlatformUser>(`/platform/users/${id}/active`, { method: "PATCH", body: { active } })

export const resetPassword = (id: string, password: string) =>
  api<void>(`/platform/users/${id}/password`, { method: "POST", body: { password } })

export const listLinks = (tenantId: string) =>
  api<TenantLink[]>(`/platform/tenants/${tenantId}/links`)

export const createLink = (tenantId: string, input: { user_id: string; role: TenantLink["role"] }) =>
  api<TenantLink>(`/platform/tenants/${tenantId}/links`, { method: "POST", body: input })

export const deleteLink = (tenantId: string, userId: string) =>
  api<void>(`/platform/tenants/${tenantId}/links/${userId}`, { method: "DELETE" })
```

- [ ] **Step 2: Implementar `TenantsPage.tsx`**

Estrutura funcional minima (refinamento visual pelo skill):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError } from "@/lib/api"
import {
  KNOWN_MODULES,
  createTenant,
  listTenants,
  setTenantModules,
  setTenantStatus,
  type Tenant,
  type TenantStatus,
} from "@/lib/platform"

const STATUSES: TenantStatus[] = ["ativa", "teste", "suspensa", "inativa"]

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function TenantsPage() {
  const queryClient = useQueryClient()
  const { data: tenants, isLoading } = useQuery({ queryKey: ["tenants"], queryFn: listTenants })
  const [createOpen, setCreateOpen] = useState(false)
  const [modulesTenant, setModulesTenant] = useState<Tenant | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["tenants"] })

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Tenant criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: TenantStatus }) =>
      setTenantStatus(id, status),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const modulesMutation = useMutation({
    mutationFn: ({ id, modules }: { id: string; modules: Record<string, boolean> }) =>
      setTenantModules(id, modules),
    onSuccess: () => {
      invalidate()
      setModulesTenant(null)
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      slug: String(form.get("slug")),
      name: String(form.get("name")),
    })
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Tenants</h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>Novo tenant</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo tenant</DialogTitle>
            </DialogHeader>
            <form onSubmit={onCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="slug">Slug</Label>
                <Input id="slug" name="slug" className="font-mono" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="name">Nome</Label>
                <Input id="name" name="name" required />
              </div>
              <Button type="submit" disabled={createMutation.isPending}>
                Criar
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Slug</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Modulos</TableHead>
              <TableHead className="w-24">Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(tenants ?? []).map((tenant) => (
              <TableRow key={tenant.id}>
                <TableCell className="font-mono">{tenant.slug}</TableCell>
                <TableCell>{tenant.name}</TableCell>
                <TableCell>
                  <Badge variant="outline">{tenant.status}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {Object.entries(tenant.modules)
                    .filter(([, on]) => on)
                    .map(([name]) => name)
                    .join(", ") || "nenhum"}
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        Opcoes
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {STATUSES.filter((s) => s !== tenant.status).map((status) => (
                        <DropdownMenuItem
                          key={status}
                          onSelect={() => statusMutation.mutate({ id: tenant.id, status })}
                        >
                          Marcar como {status}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuItem onSelect={() => setModulesTenant(tenant)}>
                        Modulos
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={modulesTenant != null} onOpenChange={(open) => !open && setModulesTenant(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Modulos de {modulesTenant?.name}</DialogTitle>
          </DialogHeader>
          {modulesTenant && (
            <ModulesForm
              tenant={modulesTenant}
              pending={modulesMutation.isPending}
              onSave={(modules) => modulesMutation.mutate({ id: modulesTenant.id, modules })}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}

function ModulesForm({
  tenant,
  pending,
  onSave,
}: {
  tenant: Tenant
  pending: boolean
  onSave: (modules: Record<string, boolean>) => void
}) {
  const [modules, setModules] = useState<Record<string, boolean>>(() => ({
    ...Object.fromEntries(KNOWN_MODULES.map((name) => [name, false])),
    ...tenant.modules,
  }))

  return (
    <div className="flex flex-col gap-3">
      {Object.entries(modules).map(([name, enabled]) => (
        <div key={name} className="flex items-center justify-between">
          <span className="font-mono text-sm">{name}</span>
          <Switch
            checked={enabled}
            onCheckedChange={(checked) => setModules({ ...modules, [name]: checked })}
          />
        </div>
      ))}
      <Button onClick={() => onSave(modules)} disabled={pending}>
        Salvar
      </Button>
    </div>
  )
}
```

- [ ] **Step 3: Registrar a rota**

Em `main.tsx`, dentro dos children do `AppShell`:

```tsx
import { RequireSuperAdmin } from "@/lib/guards"
import TenantsPage from "@/pages/platform/TenantsPage"

{
  element: <RequireSuperAdmin />,
  children: [{ path: "/plataforma/tenants", element: <TenantsPage /> }],
},
```

- [ ] **Step 4: Verificar e commitar**

`pnpm dev` com backend: criar um tenant real (ex.: slug `b2pro`), ver na tabela, suspender, editar módulos. Erros (slug duplicado) devem aparecer como toast.
Em `frontend/`: `pnpm lint && pnpm build` — esperado sucesso.

```bash
git add frontend
git commit -m "Adiciona pagina de tenants do painel da plataforma"
```

---

### Task 18: Frontend — painel da plataforma: usuários e vínculos

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md`.

**Files:**
- Create: `frontend/src/pages/platform/UsersPage.tsx`
- Modify: `frontend/src/pages/platform/TenantsPage.tsx` (item "Vinculos" no menu de ações + dialog)
- Modify: `frontend/src/main.tsx` (rota `/plataforma/usuarios`)

**Interfaces:**
- Consumes: funções de `lib/platform.ts` (Task 17), rotas da Task 12.
- Produces: página de usuários (tabela: nome, email mono, badge "super admin", switch ativo, ação redefinir senha; dialog de criação) e dialog de vínculos por tenant (lista email+papel, adicionar via select de usuário + select de papel, remover).

- [ ] **Step 1: Implementar `UsersPage.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { ApiError } from "@/lib/api"
import {
  createUser,
  listUsers,
  resetPassword,
  setUserActive,
  type PlatformUser,
} from "@/lib/platform"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function UsersPage() {
  const queryClient = useQueryClient()
  const { data: users, isLoading } = useQuery({ queryKey: ["platform-users"], queryFn: listUsers })
  const [createOpen, setCreateOpen] = useState(false)
  const [resetUser, setResetUser] = useState<PlatformUser | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["platform-users"] })

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Usuario criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => setUserActive(id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      resetPassword(id, password),
    onSuccess: () => {
      setResetUser(null)
      toast.success("Senha redefinida")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      name: String(form.get("name")),
      email: String(form.get("email")),
      password: String(form.get("password")),
      is_super_admin: form.get("is_super_admin") === "on",
    })
  }

  function onReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!resetUser) return
    const form = new FormData(event.currentTarget)
    resetMutation.mutate({ id: resetUser.id, password: String(form.get("password")) })
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Usuarios</h1>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>Novo usuario</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo usuario</DialogTitle>
            </DialogHeader>
            <form onSubmit={onCreate} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="name">Nome</Label>
                <Input id="name" name="name" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" className="font-mono" required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Senha</Label>
                <Input id="password" name="password" type="password" required minLength={8} />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="is_super_admin" name="is_super_admin" />
                <Label htmlFor="is_super_admin">Super admin</Label>
              </div>
              <Button type="submit" disabled={createMutation.isPending}>
                Criar
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Perfil</TableHead>
              <TableHead>Ativo</TableHead>
              <TableHead className="w-40">Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(users ?? []).map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.name}</TableCell>
                <TableCell className="font-mono">{user.email}</TableCell>
                <TableCell>
                  {user.is_super_admin ? <Badge variant="outline">super admin</Badge> : null}
                </TableCell>
                <TableCell>
                  <Switch
                    checked={user.active}
                    onCheckedChange={(checked) =>
                      activeMutation.mutate({ id: user.id, active: checked })
                    }
                  />
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" onClick={() => setResetUser(user)}>
                    Redefinir senha
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={resetUser != null} onOpenChange={(open) => !open && setResetUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Redefinir senha de {resetUser?.name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={onReset} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-password">Nova senha</Label>
              <Input id="new-password" name="password" type="password" required minLength={8} />
            </div>
            <Button type="submit" disabled={resetMutation.isPending}>
              Salvar
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
```

- [ ] **Step 2: Dialog de vínculos na `TenantsPage`**

Acrescentar um estado `linksTenant: Tenant | null`, um item "Vinculos" no dropdown de ações da linha e o componente abaixo no final do arquivo (renderizado num `Dialog` igual ao de módulos):

```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { createLink, deleteLink, listLinks, listUsers, type TenantLink } from "@/lib/platform"

const ROLES: TenantLink["role"][] = ["admin", "supervisor", "atendente", "visualizador"]

function LinksDialogContent({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient()
  const { data: links } = useQuery({
    queryKey: ["links", tenant.id],
    queryFn: () => listLinks(tenant.id),
  })
  const { data: users } = useQuery({ queryKey: ["platform-users"], queryFn: listUsers })
  const [userId, setUserId] = useState("")
  const [role, setRole] = useState<TenantLink["role"]>("atendente")

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["links", tenant.id] })

  const addMutation = useMutation({
    mutationFn: () => createLink(tenant.id, { user_id: userId, role }),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })
  const removeMutation = useMutation({
    mutationFn: (linkUserId: string) => deleteLink(tenant.id, linkUserId),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  const emailById = new Map((users ?? []).map((u) => [u.id, u.email]))

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {(links ?? []).map((link) => (
          <li key={link.user_id} className="flex items-center justify-between border-b border-border pb-2">
            <span className="font-mono text-sm">{emailById.get(link.user_id) ?? link.user_id}</span>
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              {link.role}
              <Button variant="ghost" size="sm" onClick={() => removeMutation.mutate(link.user_id)}>
                Remover
              </Button>
            </span>
          </li>
        ))}
        {links?.length === 0 && (
          <li className="text-sm text-muted-foreground">Nenhum vinculo para este tenant</li>
        )}
      </ul>
      <div className="flex items-end gap-2">
        <div className="flex flex-1 flex-col gap-2">
          <Label>Usuario</Label>
          <Select value={userId} onValueChange={setUserId}>
            <SelectTrigger>
              <SelectValue placeholder="selecione" />
            </SelectTrigger>
            <SelectContent>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label>Papel</Label>
          <Select value={role} onValueChange={(v) => setRole(v as TenantLink["role"])}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => addMutation.mutate()} disabled={!userId || addMutation.isPending}>
          Vincular
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Registrar a rota**

Em `main.tsx`, ao lado da rota de tenants:

```tsx
import UsersPage from "@/pages/platform/UsersPage"

{ path: "/plataforma/usuarios", element: <UsersPage /> },
```

- [ ] **Step 4: Verificar e commitar**

`pnpm dev` com backend: criar usuário, desativar/reativar, redefinir senha, vincular a um tenant e conferir que o login desse usuário passa a funcionar com o slug.
Em `frontend/`: `pnpm lint && pnpm build` — esperado sucesso.

```bash
git add frontend
git commit -m "Adiciona paginas de usuarios e vinculos do painel da plataforma"
```

---

### Task 19: Verificação final integrada e README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: tudo anterior.
- Produces: fluxo completo validado ponta a ponta e README com quickstart.

- [ ] **Step 1: Subir tudo do zero**

```bash
docker compose up -d db
cd backend
cp .env.example .env   # preencher SAC_SEED_ADMIN_EMAIL e SAC_SEED_ADMIN_PASSWORD
uv run python -m sac.infrastructure.migrate all
uv run python -m sac.infrastructure.seed
uv run uvicorn sac.main:app --reload
```

Em outro terminal: `cd frontend && pnpm dev`.

- [ ] **Step 2: Fluxo manual de aceitação**

1. Login como super admin (slug vazio) — entra no shell com grupo Plataforma.
2. Criar tenant `b2pro` — aparece na tabela; conferir no banco que o schema `t_b2pro` existe.
3. Criar usuário `ana@...` e vincular ao tenant como `admin`.
4. Sair; logar como `ana` com slug `b2pro` — entra sem o grupo Plataforma.
5. Tentar senha errada 6 vezes — toast de rate limit (429).
6. Suspender o tenant e conferir que o login da `ana` passa a falhar com "credenciais invalidas".

- [ ] **Step 3: Verificações completas**

Backend (em `backend/`): `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest` — tudo verde.
Frontend (em `frontend/`): `pnpm lint && pnpm build` — tudo verde.

- [ ] **Step 4: Atualizar `README.md`**

Ler o conteúdo atual e reescrever com: descrição de uma linha do projeto, stack, pré-requisitos (Docker, uv, Node 20+, pnpm), passos do Step 1 como quickstart, comandos de teste/verificação e apontadores para `docs/PRD.md`, o spec e este plano.

- [ ] **Step 5: Commit final**

```bash
git add README.md
git commit -m "Atualiza README com quickstart da fundacao"
```
