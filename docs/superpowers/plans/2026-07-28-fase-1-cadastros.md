# Fase 1 (Cadastros) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cadastros por tenant (Marca, Defeito, Solução, Canal via catálogo genérico; Cliente e Produto dedicados) com tenancy real via `schema_translate_map`, lookup de CEP no backend, seeds híbridos e CRUDs no frontend.

**Architecture:** Mesma Clean Architecture da Fase 0 (`interface -> application -> domain`; `infrastructure` implementa ports). Novidade estrutural: primeiras tabelas no schema simbólico `tenant` (traduzido para `t_<slug>` por request) e um mecanismo genérico de catálogo parametrizado por `CatalogKind` que serve 4 cadastros.

**Tech Stack:** o existente (FastAPI, SQLAlchemy 2 async, Alembic, pytest; React + TanStack Query + shadcn/ui). httpx passa a dependência de runtime (gateway ViaCEP).

**Spec:** `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-1-design.md`.

## Global Constraints

- PROIBIDO usar emojis em código, comentários, commits, UI, documentação e mensagens.
- Clean Architecture: `domain` e `application` são Python puro (sem FastAPI/SQLAlchemy/Pydantic); `infrastructure` implementa os ports.
- TDD no backend: teste antes da implementação em toda tarefa de backend.
- SEM CI. Antes de CADA commit rodar localmente e exigir sucesso:
  - Backend (em `backend/`): `uv run ruff format .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
  - Frontend (em `frontend/`): `pnpm lint` e `pnpm build`.
- Testes de integração exigem o Postgres do compose de pé (`docker compose up -d db` na raiz).
- Toda tarefa de frontend (Tasks 12-15) DEVE invocar o skill `frontend-design` antes de escrever UI e seguir `docs/identidade-visual.md` (dado técnico em `font-mono`: SKU, documento, CEP, telefone; Paprika só na ação primária; lucide strokeWidth 1.5, 16px em tabelas / 20px em botões; empty states de texto direto; sem sombras decorativas).
- Commits em português, imperativo, sem prefixo convencional, corpo terminando com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Sem exclusão física em cadastros: não existe endpoint DELETE; o caminho é `PATCH /{id}/active`.
- Permissões (matriz PRD): listar -> `LISTAR_CADASTROS`; criar -> `CRIAR_LISTAR_CADASTROS`; editar/inativar -> `GERENCIAR_CADASTROS`.
- Testes de integração de cadastros devem tolerar seeds pré-existentes (Task 11 faz o provisionamento semear defaults): nunca assertar lista vazia ou contagens absolutas de catálogo; usar nomes únicos e verificar presença/ausência.

## Mapa de arquivos novos/modificados (backend)

```
backend/src/sac/
  domain/
    documents.py           # normalize_digits, is_valid_cpf/cnpj, validate_document, BR_STATES, validate_state
    catalog.py             # CatalogKind, CatalogItem
    cadastros.py           # Customer, Product (entidades)
    errors.py              # +CepUnavailableError
    permissions.py         # ATENDENTE += LISTAR_CADASTROS
  application/
    ports_cadastros.py     # CatalogRepository, CustomerRepository, ProductRepository, CepGatewayPort, CepAddress
    use_cases/
      catalog.py           # List/Create/Update/SetActive de CatalogItem
      customers.py         # List/Create/Update/SetActive de Customer
      products.py          # List/Create/Update/SetActive de Product
      cep.py               # LookupCepUseCase
  infrastructure/
    models_tenant.py       # TenantTableMixin, CatalogModelBase, Brand/DefectType/SolutionType/PurchaseChannel/Product/CustomerModel
    repositories_cadastros.py  # CATALOG_MODELS, SqlCatalogRepository, SqlCustomerRepository, SqlProductRepository
    cep.py                 # ViaCepGateway (httpx)
    tenant_seeds.py        # listas default + seed_tenant_defaults(session)
    seed_tenant.py         # CLI: python -m sac.infrastructure.seed_tenant <slug>
    provisioning.py        # provision() passa a semear defaults
  interface/
    deps.py                # +get_tenant_session, factories de repos/use cases de cadastros, get_cep_gateway
    errors.py              # STATUS_BY_CODE += cep_indisponivel: 503
    schemas.py             # +CatalogItemIn/Out, ActiveIn, CustomerIn/Out, CustomersPageOut, ProductIn/Out, ProductsPageOut, CepOut
    routers/
      cadastros_catalog.py    # build_catalog_router + 4 instancias
      cadastros_customers.py
      cadastros_products.py
      cep.py
backend/migrations/tenant/versions/0002_cadastros.py
backend/tests/... (unit e integração por tarefa)
frontend/src/
  lib/cadastros.ts, lib/format.ts, lib/guards.tsx (+RequireTenant)
  pages/cadastros/CatalogPage.tsx, ProdutosPage.tsx, ClientesPage.tsx
  components/layout/Sidebar.tsx (grupo Cadastros), main.tsx (rotas)
```

---

### Task 1: Permissão de listagem para atendente

**Files:**
- Modify: `backend/src/sac/domain/permissions.py`
- Test: `backend/tests/unit/domain/test_permissions.py`

**Interfaces:**
- Consumes: `Role`, `Permission`, `ROLE_PERMISSIONS` existentes.
- Produces: `has_permission(Role.ATENDENTE, Permission.LISTAR_CADASTROS) == True` (matriz do PRD: atendente "criar + listar").

- [ ] **Step 1: Atualizar o teste (falha primeiro)**

Em `backend/tests/unit/domain/test_permissions.py`, alterar o teste do atendente:

```python
def test_atendente_nao_decide_nem_gerencia_cadastros() -> None:
    assert not has_permission(Role.ATENDENTE, Permission.DECIDIR_TICKET)
    assert not has_permission(Role.ATENDENTE, Permission.GERENCIAR_CADASTROS)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_TICKET)
    assert has_permission(Role.ATENDENTE, Permission.ENVIAR_PARA_ANALISE)
    assert has_permission(Role.ATENDENTE, Permission.CRIAR_LISTAR_CADASTROS)
    assert has_permission(Role.ATENDENTE, Permission.LISTAR_CADASTROS)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/domain/test_permissions.py -v`
Esperado: FAIL no novo assert.

- [ ] **Step 3: Implementar**

Em `backend/src/sac/domain/permissions.py`, no frozenset de `Role.ATENDENTE`, acrescentar:

```python
            Permission.LISTAR_CADASTROS,
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/domain/permissions.py backend/tests/unit/domain/test_permissions.py
git commit -m "Concede permissao de listar cadastros ao papel atendente"
```

---

### Task 2: Domínio — validação de CPF/CNPJ e normalizações

**Files:**
- Create: `backend/src/sac/domain/documents.py`
- Test: `backend/tests/unit/domain/test_documents.py`

**Interfaces:**
- Consumes: `ValidationError` (domain/errors.py).
- Produces: `normalize_digits(value: str) -> str`; `is_valid_cpf(digits: str) -> bool`; `is_valid_cnpj(digits: str) -> bool`; `validate_document(value: str) -> str` (retorna só dígitos ou levanta `ValidationError`); `BR_STATES: frozenset[str]`; `validate_state(value: str) -> str` (uppercase ou `ValidationError`).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/domain/test_documents.py`:

```python
import pytest

from sac.domain.documents import (
    is_valid_cnpj,
    is_valid_cpf,
    normalize_digits,
    validate_document,
    validate_state,
)
from sac.domain.errors import ValidationError


def test_normalize_digits() -> None:
    assert normalize_digits("529.982.247-25") == "52998224725"
    assert normalize_digits("(54) 99982-3566") == "54999823566"
    assert normalize_digits("abc") == ""


def test_cpf_valido() -> None:
    assert is_valid_cpf("52998224725")


@pytest.mark.parametrize("digits", ["52998224724", "11111111111", "5299822472", ""])
def test_cpf_invalido(digits: str) -> None:
    assert not is_valid_cpf(digits)


def test_cnpj_valido() -> None:
    assert is_valid_cnpj("11222333000181")


@pytest.mark.parametrize("digits", ["11222333000180", "11111111111111", "1122233300018"])
def test_cnpj_invalido(digits: str) -> None:
    assert not is_valid_cnpj(digits)


def test_validate_document_normaliza_e_aceita() -> None:
    assert validate_document("529.982.247-25") == "52998224725"
    assert validate_document("11.222.333/0001-81") == "11222333000181"


@pytest.mark.parametrize("value", ["123", "529.982.247-24", "11.222.333/0001-80", ""])
def test_validate_document_rejeita(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_document(value)


def test_validate_state() -> None:
    assert validate_state(" rs ") == "RS"
    with pytest.raises(ValidationError):
        validate_state("XX")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/domain/test_documents.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/domain/documents.py`**

```python
import re

from sac.domain.errors import ValidationError

_NON_DIGITS = re.compile(r"\D")

BR_STATES = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
        "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
    }
)


def normalize_digits(value: str) -> str:
    return _NON_DIGITS.sub("", value)


def _cpf_digit(digits: str, start_weight: int) -> int:
    total = sum(int(d) * w for d, w in zip(digits, range(start_weight, 1, -1), strict=True))
    remainder = (total * 10) % 11
    return 0 if remainder == 10 else remainder


def is_valid_cpf(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    return int(digits[9]) == _cpf_digit(digits[:9], 10) and int(digits[10]) == _cpf_digit(
        digits[:10], 11
    )


def _cnpj_digit(digits: str, weights: list[int]) -> int:
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    first = _cnpj_digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _cnpj_digit(digits[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return int(digits[12]) == first and int(digits[13]) == second


def validate_document(value: str) -> str:
    digits = normalize_digits(value)
    if len(digits) == 11 and is_valid_cpf(digits):
        return digits
    if len(digits) == 14 and is_valid_cnpj(digits):
        return digits
    raise ValidationError(
        "documento invalido: informe um CPF ou CNPJ valido", details={"document": value}
    )


def validate_state(value: str) -> str:
    state = value.strip().upper()
    if state not in BR_STATES:
        raise ValidationError(f"UF invalida: {value}")
    return state
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain/test_documents.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/domain/documents.py backend/tests/unit/domain/test_documents.py
git commit -m "Adiciona validacao de CPF/CNPJ e normalizacoes de documento"
```

---

### Task 3: Domínio e ports — catálogo, Customer, Product

Entidades são dataclasses puras sem lógica; a cobertura de teste chega nas Tasks 6-7 (use cases). Esta task fecha com mypy e a suíte existente verde.

**Files:**
- Create: `backend/src/sac/domain/catalog.py`
- Create: `backend/src/sac/domain/cadastros.py`
- Create: `backend/src/sac/application/ports_cadastros.py`

**Interfaces:**
- Consumes: nada novo.
- Produces (exato, consumido pelas Tasks 4-11):
  - `CatalogKind` (StrEnum: BRAND="brand", DEFECT_TYPE="defect_type", SOLUTION_TYPE="solution_type", PURCHASE_CHANNEL="purchase_channel"); `CatalogItem(id: UUID, name: str, description: str | None = None, active: bool = True, deleted_at: datetime | None = None)`.
  - `Customer(id, name, document, phone=None, email=None, cep=None, street=None, number=None, complement=None, neighborhood=None, city=None, state=None, active=True, deleted_at=None)`; `Product(id, name, sku, segment=None, description=None, photo_key=None, active=True, deleted_at=None)`.
  - Ports (Protocol, todos async): `CatalogRepository` (`list(search, active) -> list[CatalogItem]`, `get(item_id) -> CatalogItem | None`, `get_by_name(name) -> CatalogItem | None`, `add(item)`, `update(item)`); `CustomerRepository` (`list(search, active, page, per_page) -> tuple[list[Customer], int]`, `get`, `get_by_document(document) -> Customer | None`, `add`, `update`); `ProductRepository` (igual com `get_by_sku`).

- [ ] **Step 1: Implementar `backend/src/sac/domain/catalog.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CatalogKind(StrEnum):
    BRAND = "brand"
    DEFECT_TYPE = "defect_type"
    SOLUTION_TYPE = "solution_type"
    PURCHASE_CHANNEL = "purchase_channel"


@dataclass
class CatalogItem:
    id: UUID
    name: str
    description: str | None = None
    active: bool = True
    deleted_at: datetime | None = None
```

- [ ] **Step 2: Implementar `backend/src/sac/domain/cadastros.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Customer:
    id: UUID
    name: str
    document: str
    phone: str | None = None
    email: str | None = None
    cep: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    active: bool = True
    deleted_at: datetime | None = None


@dataclass
class Product:
    id: UUID
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None
    photo_key: str | None = None
    active: bool = True
    deleted_at: datetime | None = None
```

- [ ] **Step 3: Implementar `backend/src/sac/application/ports_cadastros.py`**

```python
from typing import Protocol
from uuid import UUID

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem


class CatalogRepository(Protocol):
    async def list(self, search: str | None, active: bool | None) -> list[CatalogItem]: ...
    async def get(self, item_id: UUID) -> CatalogItem | None: ...
    async def get_by_name(self, name: str) -> CatalogItem | None: ...
    async def add(self, item: CatalogItem) -> None: ...
    async def update(self, item: CatalogItem) -> None: ...


class CustomerRepository(Protocol):
    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Customer], int]: ...
    async def get(self, customer_id: UUID) -> Customer | None: ...
    async def get_by_document(self, document: str) -> Customer | None: ...
    async def add(self, customer: Customer) -> None: ...
    async def update(self, customer: Customer) -> None: ...


class ProductRepository(Protocol):
    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Product], int]: ...
    async def get(self, product_id: UUID) -> Product | None: ...
    async def get_by_sku(self, sku: str) -> Product | None: ...
    async def add(self, product: Product) -> None: ...
    async def update(self, product: Product) -> None: ...
```

- [ ] **Step 4: Verificações completas e commit**

Run: `uv run mypy && uv run pytest -q` — esperado: sem erros, suíte verde.
Rodar as demais verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/domain/catalog.py backend/src/sac/domain/cadastros.py backend/src/sac/application/ports_cadastros.py
git commit -m "Adiciona entidades e ports dos cadastros por tenant"
```

---

### Task 4: Models do tenant + migration 0002 + isolamento

**Files:**
- Modify: `backend/src/sac/infrastructure/models_tenant.py` (substituir conteúdo)
- Create: `backend/migrations/tenant/versions/0002_cadastros.py`
- Test: `backend/tests/integration/test_tenant_schema.py`

**Interfaces:**
- Consumes: `TenantBase` existente; `AlembicTenantProvisioner` (provisiona e aplica head da árvore tenant); fixtures `engine`/`session` do conftest de integração.
- Produces: models `BrandModel`/`DefectTypeModel`/`SolutionTypeModel`/`PurchaseChannelModel` (herdam `CatalogModelBase` com colunas id/name unique/description/active/created_at/updated_at/deleted_at), `ProductModel` (name, sku unique, segment, description, photo_key), `CustomerModel` (name, document unique, phone, email, cep, street, number, complement, neighborhood, city, state) — todos com `__table_args__ = {"schema": "tenant"}` via mixin. `CatalogModelBase` é classe abstrata real (usada para tipagem do repositório genérico na Task 5).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_tenant_schema.py`:

```python
from uuid import uuid4

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.infrastructure.models_tenant import BrandModel
from sac.infrastructure.provisioning import AlembicTenantProvisioner

EXPECTED_TABLES = {
    "brands",
    "defect_types",
    "solution_types",
    "purchase_channels",
    "products",
    "customers",
}


def _tenant_sessionmaker(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


async def test_migration_tenant_cria_tabelas_de_cadastro(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_demo")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names(schema="t_demo"))
    assert EXPECTED_TABLES <= set(tables)


async def test_schema_translate_map_isola_tenants(engine: AsyncEngine) -> None:
    provisioner = AlembicTenantProvisioner(engine)
    await provisioner.provision("t_alfa")
    await provisioner.provision("t_beta")

    async with _tenant_sessionmaker(engine, "t_alfa")() as session:
        session.add(BrandModel(id=uuid4(), name="MARCA-ALFA"))
        await session.commit()

    async with _tenant_sessionmaker(engine, "t_alfa")() as session:
        names = list(await session.scalars(select(BrandModel.name)))
    assert "MARCA-ALFA" in names

    async with _tenant_sessionmaker(engine, "t_beta")() as session:
        names = list(await session.scalars(select(BrandModel.name)))
    assert "MARCA-ALFA" not in names
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_tenant_schema.py -v`
Esperado: FAIL (ImportError em BrandModel).

- [ ] **Step 3: Substituir `backend/src/sac/infrastructure/models_tenant.py`**

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TenantBase(DeclarativeBase):
    pass


class TenantTableMixin:
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogModelBase(TenantTableMixin, TenantBase):
    __abstract__ = True

    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class BrandModel(CatalogModelBase):
    __tablename__ = "brands"


class DefectTypeModel(CatalogModelBase):
    __tablename__ = "defect_types"


class SolutionTypeModel(CatalogModelBase):
    __tablename__ = "solution_types"


class PurchaseChannelModel(CatalogModelBase):
    __tablename__ = "purchase_channels"


class ProductModel(TenantTableMixin, TenantBase):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    segment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CustomerModel(TenantTableMixin, TenantBase):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200))
    document: Mapped[str] = mapped_column(String(14), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
```

- [ ] **Step 4: Criar `backend/migrations/tenant/versions/0002_cadastros.py`**

Migration escrita à mão (a árvore tenant não usa autogenerate): as tabelas usam `schema="tenant"` — o env.py da árvore traduz para o schema real via `schema_translate_map`.

```python
"""cadastros do tenant

Revision ID: 0002_cadastros
Revises: 0001_baseline
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_cadastros"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

CATALOG_TABLES = ("brands", "defect_types", "solution_types", "purchase_channels")


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for table in CATALOG_TABLES:
        op.create_table(
            table,
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            *_base_columns(),
            schema="tenant",
        )
    op.create_table(
        "products",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False, unique=True),
        sa.Column("segment", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_key", sa.String(255), nullable=True),
        *_base_columns(),
        schema="tenant",
    )
    op.create_table(
        "customers",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("document", sa.String(14), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("cep", sa.String(8), nullable=True),
        sa.Column("street", sa.String(200), nullable=True),
        sa.Column("number", sa.String(20), nullable=True),
        sa.Column("complement", sa.String(100), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        *_base_columns(),
        schema="tenant",
    )


def downgrade() -> None:
    for table in ("customers", "products", *reversed(CATALOG_TABLES)):
        op.drop_table(table, schema="tenant")
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_tenant_schema.py -v`
Esperado: PASS (2 testes).

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure/models_tenant.py backend/migrations/tenant/versions/0002_cadastros.py backend/tests/integration/test_tenant_schema.py
git commit -m "Adiciona tabelas de cadastros no schema do tenant com isolamento"
```

---

### Task 5: Repositórios SQL dos cadastros

**Files:**
- Create: `backend/src/sac/infrastructure/repositories_cadastros.py`
- Test: `backend/tests/integration/test_repositories_cadastros.py`

**Interfaces:**
- Consumes: models da Task 4, entidades/ports da Task 3, `normalize_digits` (Task 2), `ConflictError`/`NotFoundError`.
- Produces:
  - `CATALOG_MODELS: dict[CatalogKind, type[CatalogModelBase]]`.
  - `SqlCatalogRepository(session, kind)` implementando `CatalogRepository` (add/update levantam `ConflictError("nome ja cadastrado")` em unique; update/`NotFoundError`; list ordena por nome, filtra `deleted_at IS NULL`, busca `ilike` no nome).
  - `SqlCustomerRepository(session)` implementando `CustomerRepository` (busca: nome `ilike` OU documento contendo os dígitos da busca; paginação offset/limit; retorna `(items, total)`; conflito "documento ja cadastrado").
  - `SqlProductRepository(session)` implementando `ProductRepository` (busca nome OU sku `ilike`; conflito "SKU ja cadastrado").

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_repositories_cadastros.py`:

```python
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem, CatalogKind
from sac.domain.errors import ConflictError
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories_cadastros import (
    SqlCatalogRepository,
    SqlCustomerRepository,
    SqlProductRepository,
)


@pytest.fixture
async def tenant_session(engine: AsyncEngine):
    await AlembicTenantProvisioner(engine).provision("t_repo")
    translated = engine.execution_options(schema_translate_map={"tenant": "t_repo"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        yield session


def _item(name: str) -> CatalogItem:
    return CatalogItem(id=uuid4(), name=name)


def _customer(document: str = "52998224725", name: str = "Ana") -> Customer:
    return Customer(id=uuid4(), name=name, document=document)


def _product(sku: str = "PLN-10-7", name: str = "Alicate") -> Product:
    return Product(id=uuid4(), name=name, sku=sku)


async def test_catalogo_roundtrip_busca_e_conflito(tenant_session) -> None:
    repo = SqlCatalogRepository(tenant_session, CatalogKind.BRAND)
    await repo.add(_item("MARCA-X"))
    await tenant_session.commit()

    assert await repo.get_by_name("MARCA-X") is not None
    encontrados = await repo.list(search="marca-x", active=None)
    assert any(i.name == "MARCA-X" for i in encontrados)

    item = await repo.get_by_name("MARCA-X")
    assert item is not None
    item.name = "MARCA-Y"
    item.active = False
    await repo.update(item)
    await tenant_session.commit()
    atualizado = await repo.get(item.id)
    assert atualizado is not None and atualizado.name == "MARCA-Y" and not atualizado.active

    with pytest.raises(ConflictError):
        await repo.add(_item("MARCA-Y"))


async def test_catalogo_e_por_tabela(tenant_session) -> None:
    brands = SqlCatalogRepository(tenant_session, CatalogKind.BRAND)
    defects = SqlCatalogRepository(tenant_session, CatalogKind.DEFECT_TYPE)
    await brands.add(_item("SO-NA-MARCA"))
    await tenant_session.commit()
    assert await defects.get_by_name("SO-NA-MARCA") is None


async def test_cliente_roundtrip_busca_por_documento_e_paginacao(tenant_session) -> None:
    repo = SqlCustomerRepository(tenant_session)
    await repo.add(_customer("52998224725", "Ana Silva"))
    await repo.add(_customer("11222333000181", "Beauty Ltda"))
    await repo.add(_customer("15350946056", "Carla Souza"))
    await tenant_session.commit()

    por_documento, total = await repo.list(search="529.982", active=None, page=1, per_page=20)
    assert total == 1 and por_documento[0].name == "Ana Silva"

    pagina, total = await repo.list(search=None, active=None, page=1, per_page=2)
    assert total == 3 and len(pagina) == 2

    with pytest.raises(ConflictError):
        await repo.add(_customer("52998224725", "Duplicada"))


async def test_produto_roundtrip_busca_e_conflito(tenant_session) -> None:
    repo = SqlProductRepository(tenant_session)
    await repo.add(_product("PLN-10-7", "Alicate profissional"))
    await tenant_session.commit()

    por_sku, total = await repo.list(search="pln-10", active=None, page=1, per_page=20)
    assert total == 1

    with pytest.raises(ConflictError):
        await repo.add(_product("PLN-10-7", "Outro nome"))
```

Nota: o CPF "15350946056" e o CNPJ "11222333000181" sao validos; o repositorio nao valida documento (isso e do use case), mas os testes usam valores realistas.

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_repositories_cadastros.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/infrastructure/repositories_cadastros.py`**

```python
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem, CatalogKind
from sac.domain.documents import normalize_digits
from sac.domain.errors import ConflictError, NotFoundError
from sac.infrastructure.models_tenant import (
    BrandModel,
    CatalogModelBase,
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    PurchaseChannelModel,
    SolutionTypeModel,
)

CATALOG_MODELS: dict[CatalogKind, type[CatalogModelBase]] = {
    CatalogKind.BRAND: BrandModel,
    CatalogKind.DEFECT_TYPE: DefectTypeModel,
    CatalogKind.SOLUTION_TYPE: SolutionTypeModel,
    CatalogKind.PURCHASE_CHANNEL: PurchaseChannelModel,
}


def _catalog_entity(m: CatalogModelBase) -> CatalogItem:
    return CatalogItem(
        id=m.id, name=m.name, description=m.description, active=m.active, deleted_at=m.deleted_at
    )


class SqlCatalogRepository:
    def __init__(self, session: AsyncSession, kind: CatalogKind) -> None:
        self._session = session
        self._model = CATALOG_MODELS[kind]

    async def list(self, search: str | None, active: bool | None) -> list[CatalogItem]:
        stmt = (
            select(self._model)
            .where(self._model.deleted_at.is_(None))
            .order_by(self._model.name)
        )
        if search:
            stmt = stmt.where(self._model.name.ilike(f"%{search}%"))
        if active is not None:
            stmt = stmt.where(self._model.active == active)
        return [_catalog_entity(m) for m in await self._session.scalars(stmt)]

    async def get(self, item_id: UUID) -> CatalogItem | None:
        m = await self._session.get(self._model, item_id)
        return _catalog_entity(m) if m and m.deleted_at is None else None

    async def get_by_name(self, name: str) -> CatalogItem | None:
        m = await self._session.scalar(
            select(self._model).where(
                self._model.name == name, self._model.deleted_at.is_(None)
            )
        )
        return _catalog_entity(m) if m else None

    async def add(self, item: CatalogItem) -> None:
        self._session.add(
            self._model(
                id=item.id,
                name=item.name,
                description=item.description,
                active=item.active,
                deleted_at=item.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "nome ja cadastrado")

    async def update(self, item: CatalogItem) -> None:
        m = await self._session.get(self._model, item.id)
        if m is None:
            raise NotFoundError("registro nao encontrado")
        m.name = item.name
        m.description = item.description
        m.active = item.active
        m.deleted_at = item.deleted_at
        await _flush_or_conflict(self._session, "nome ja cadastrado")


async def _flush_or_conflict(session: AsyncSession, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(message) from exc


def _customer_entity(m: CustomerModel) -> Customer:
    return Customer(
        id=m.id,
        name=m.name,
        document=m.document,
        phone=m.phone,
        email=m.email,
        cep=m.cep,
        street=m.street,
        number=m.number,
        complement=m.complement,
        neighborhood=m.neighborhood,
        city=m.city,
        state=m.state,
        active=m.active,
        deleted_at=m.deleted_at,
    )


class SqlCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_stmt(self, search: str | None, active: bool | None) -> Select[tuple[CustomerModel]]:
        stmt = select(CustomerModel).where(CustomerModel.deleted_at.is_(None))
        if search:
            digits = normalize_digits(search)
            if digits:
                stmt = stmt.where(
                    or_(
                        CustomerModel.name.ilike(f"%{search}%"),
                        CustomerModel.document.like(f"%{digits}%"),
                    )
                )
            else:
                stmt = stmt.where(CustomerModel.name.ilike(f"%{search}%"))
        if active is not None:
            stmt = stmt.where(CustomerModel.active == active)
        return stmt

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Customer], int]:
        stmt = self._base_stmt(search, active)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(CustomerModel.name).offset((page - 1) * per_page).limit(per_page)
        )
        return [_customer_entity(m) for m in rows], int(total or 0)

    async def get(self, customer_id: UUID) -> Customer | None:
        m = await self._session.get(CustomerModel, customer_id)
        return _customer_entity(m) if m and m.deleted_at is None else None

    async def get_by_document(self, document: str) -> Customer | None:
        m = await self._session.scalar(
            select(CustomerModel).where(
                CustomerModel.document == document, CustomerModel.deleted_at.is_(None)
            )
        )
        return _customer_entity(m) if m else None

    async def add(self, customer: Customer) -> None:
        self._session.add(
            CustomerModel(
                id=customer.id,
                name=customer.name,
                document=customer.document,
                phone=customer.phone,
                email=customer.email,
                cep=customer.cep,
                street=customer.street,
                number=customer.number,
                complement=customer.complement,
                neighborhood=customer.neighborhood,
                city=customer.city,
                state=customer.state,
                active=customer.active,
                deleted_at=customer.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "documento ja cadastrado")

    async def update(self, customer: Customer) -> None:
        m = await self._session.get(CustomerModel, customer.id)
        if m is None:
            raise NotFoundError("cliente nao encontrado")
        m.name = customer.name
        m.document = customer.document
        m.phone = customer.phone
        m.email = customer.email
        m.cep = customer.cep
        m.street = customer.street
        m.number = customer.number
        m.complement = customer.complement
        m.neighborhood = customer.neighborhood
        m.city = customer.city
        m.state = customer.state
        m.active = customer.active
        m.deleted_at = customer.deleted_at
        await _flush_or_conflict(self._session, "documento ja cadastrado")


def _product_entity(m: ProductModel) -> Product:
    return Product(
        id=m.id,
        name=m.name,
        sku=m.sku,
        segment=m.segment,
        description=m.description,
        photo_key=m.photo_key,
        active=m.active,
        deleted_at=m.deleted_at,
    )


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_stmt(self, search: str | None, active: bool | None) -> Select[tuple[ProductModel]]:
        stmt = select(ProductModel).where(ProductModel.deleted_at.is_(None))
        if search:
            stmt = stmt.where(
                or_(
                    ProductModel.name.ilike(f"%{search}%"),
                    ProductModel.sku.ilike(f"%{search}%"),
                )
            )
        if active is not None:
            stmt = stmt.where(ProductModel.active == active)
        return stmt

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Product], int]:
        stmt = self._base_stmt(search, active)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(ProductModel.name).offset((page - 1) * per_page).limit(per_page)
        )
        return [_product_entity(m) for m in rows], int(total or 0)

    async def get(self, product_id: UUID) -> Product | None:
        m = await self._session.get(ProductModel, product_id)
        return _product_entity(m) if m and m.deleted_at is None else None

    async def get_by_sku(self, sku: str) -> Product | None:
        m = await self._session.scalar(
            select(ProductModel).where(
                ProductModel.sku == sku, ProductModel.deleted_at.is_(None)
            )
        )
        return _product_entity(m) if m else None

    async def add(self, product: Product) -> None:
        self._session.add(
            ProductModel(
                id=product.id,
                name=product.name,
                sku=product.sku,
                segment=product.segment,
                description=product.description,
                photo_key=product.photo_key,
                active=product.active,
                deleted_at=product.deleted_at,
            )
        )
        await _flush_or_conflict(self._session, "SKU ja cadastrado")

    async def update(self, product: Product) -> None:
        m = await self._session.get(ProductModel, product.id)
        if m is None:
            raise NotFoundError("produto nao encontrado")
        m.name = product.name
        m.sku = product.sku
        m.segment = product.segment
        m.description = product.description
        m.photo_key = product.photo_key
        m.active = product.active
        m.deleted_at = product.deleted_at
        await _flush_or_conflict(self._session, "SKU ja cadastrado")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_repositories_cadastros.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure/repositories_cadastros.py backend/tests/integration/test_repositories_cadastros.py
git commit -m "Adiciona repositorios SQL dos cadastros por tenant"
```

---

### Task 6: Use cases do catálogo genérico (unit)

**Files:**
- Create: `backend/src/sac/application/use_cases/catalog.py`
- Modify: `backend/tests/unit/fakes.py` (acrescentar `InMemoryCatalogRepository`)
- Test: `backend/tests/unit/application/test_catalog_use_cases.py`

**Interfaces:**
- Consumes: `CatalogItem` (Task 3), `CatalogRepository` (Task 3), `ValidationError`/`ConflictError`/`NotFoundError`.
- Produces:
  - `CatalogItemInput(name: str, description: str | None = None)` (frozen dataclass).
  - `ListCatalogUseCase(repo)` com `execute(search: str | None = None, active: bool | None = None) -> list[CatalogItem]`.
  - `CreateCatalogItemUseCase(repo)` com `execute(data: CatalogItemInput) -> CatalogItem` (nome strip obrigatório; conflito por `get_by_name`).
  - `UpdateCatalogItemUseCase(repo)` com `execute(item_id: UUID, data: CatalogItemInput) -> CatalogItem` (NotFound; conflito de nome com outro id).
  - `SetCatalogItemActiveUseCase(repo)` com `execute(item_id: UUID, active: bool) -> CatalogItem`.

- [ ] **Step 1: Acrescentar o fake em `backend/tests/unit/fakes.py`**

```python
from sac.domain.catalog import CatalogItem


class InMemoryCatalogRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, CatalogItem] = {}

    async def list(self, search: str | None, active: bool | None) -> list[CatalogItem]:
        result = [i for i in self.items.values() if i.deleted_at is None]
        if search:
            result = [i for i in result if search.lower() in i.name.lower()]
        if active is not None:
            result = [i for i in result if i.active == active]
        return sorted(result, key=lambda i: i.name)

    async def get(self, item_id: UUID) -> CatalogItem | None:
        item = self.items.get(item_id)
        return item if item and item.deleted_at is None else None

    async def get_by_name(self, name: str) -> CatalogItem | None:
        return next(
            (i for i in self.items.values() if i.name == name and i.deleted_at is None), None
        )

    async def add(self, item: CatalogItem) -> None:
        if await self.get_by_name(item.name):
            raise ConflictError("nome ja cadastrado")
        self.items[item.id] = item

    async def update(self, item: CatalogItem) -> None:
        if item.id not in self.items:
            raise NotFoundError("registro nao encontrado")
        self.items[item.id] = item
```

(Os imports `ConflictError`, `NotFoundError`, `UUID` já existem no arquivo.)

- [ ] **Step 2: Escrever o teste que falha**

`backend/tests/unit/application/test_catalog_use_cases.py`:

```python
from uuid import uuid4

import pytest

from sac.application.use_cases.catalog import (
    CatalogItemInput,
    CreateCatalogItemUseCase,
    ListCatalogUseCase,
    SetCatalogItemActiveUseCase,
    UpdateCatalogItemUseCase,
)
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from tests.unit.fakes import InMemoryCatalogRepository


async def test_criar_normaliza_nome_e_lista() -> None:
    repo = InMemoryCatalogRepository()
    item = await CreateCatalogItemUseCase(repo).execute(
        CatalogItemInput(name="  Oxidacao  ", description="Produto oxidado")
    )
    assert item.name == "Oxidacao"
    assert item.active is True

    listados = await ListCatalogUseCase(repo).execute()
    assert [i.name for i in listados] == ["Oxidacao"]


async def test_nome_vazio_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCatalogItemUseCase(InMemoryCatalogRepository()).execute(
            CatalogItemInput(name="   ")
        )


async def test_nome_duplicado_gera_conflito() -> None:
    repo = InMemoryCatalogRepository()
    use_case = CreateCatalogItemUseCase(repo)
    await use_case.execute(CatalogItemInput(name="Danificado"))
    with pytest.raises(ConflictError):
        await use_case.execute(CatalogItemInput(name="Danificado"))


async def test_atualizar_renomeia_e_detecta_conflito() -> None:
    repo = InMemoryCatalogRepository()
    create = CreateCatalogItemUseCase(repo)
    a = await create.execute(CatalogItemInput(name="A"))
    b = await create.execute(CatalogItemInput(name="B"))

    atualizado = await UpdateCatalogItemUseCase(repo).execute(
        a.id, CatalogItemInput(name="A2", description="desc")
    )
    assert atualizado.name == "A2" and atualizado.description == "desc"

    with pytest.raises(ConflictError):
        await UpdateCatalogItemUseCase(repo).execute(b.id, CatalogItemInput(name="A2"))


async def test_atualizar_mantendo_o_proprio_nome_nao_conflita() -> None:
    repo = InMemoryCatalogRepository()
    a = await CreateCatalogItemUseCase(repo).execute(CatalogItemInput(name="Mesmo"))
    atualizado = await UpdateCatalogItemUseCase(repo).execute(
        a.id, CatalogItemInput(name="Mesmo", description="nova desc")
    )
    assert atualizado.description == "nova desc"


async def test_ativar_inativar_e_filtrar() -> None:
    repo = InMemoryCatalogRepository()
    item = await CreateCatalogItemUseCase(repo).execute(CatalogItemInput(name="Voucher"))

    inativado = await SetCatalogItemActiveUseCase(repo).execute(item.id, False)
    assert inativado.active is False

    ativos = await ListCatalogUseCase(repo).execute(active=True)
    assert all(i.id != item.id for i in ativos)

    with pytest.raises(NotFoundError):
        await SetCatalogItemActiveUseCase(repo).execute(uuid4(), True)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_catalog_use_cases.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 4: Implementar `backend/src/sac/application/use_cases/catalog.py`**

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CatalogRepository
from sac.domain.catalog import CatalogItem
from sac.domain.errors import ConflictError, NotFoundError, ValidationError


@dataclass(frozen=True)
class CatalogItemInput:
    name: str
    description: str | None = None


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValidationError("nome obrigatorio")
    return name


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    description = value.strip()
    return description or None


class ListCatalogUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(
        self, search: str | None = None, active: bool | None = None
    ) -> list[CatalogItem]:
        return await self._repo.list(search, active)


class CreateCatalogItemUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, data: CatalogItemInput) -> CatalogItem:
        name = _clean_name(data.name)
        if await self._repo.get_by_name(name) is not None:
            raise ConflictError("nome ja cadastrado")
        item = CatalogItem(id=uuid4(), name=name, description=_clean_description(data.description))
        await self._repo.add(item)
        return item


class UpdateCatalogItemUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, item_id: UUID, data: CatalogItemInput) -> CatalogItem:
        item = await self._repo.get(item_id)
        if item is None:
            raise NotFoundError("registro nao encontrado")
        name = _clean_name(data.name)
        existing = await self._repo.get_by_name(name)
        if existing is not None and existing.id != item_id:
            raise ConflictError("nome ja cadastrado")
        item.name = name
        item.description = _clean_description(data.description)
        await self._repo.update(item)
        return item


class SetCatalogItemActiveUseCase:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    async def execute(self, item_id: UUID, active: bool) -> CatalogItem:
        item = await self._repo.get(item_id)
        if item is None:
            raise NotFoundError("registro nao encontrado")
        item.active = active
        await self._repo.update(item)
        return item
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_catalog_use_cases.py -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/application/use_cases/catalog.py backend/tests/unit
git commit -m "Adiciona use cases do catalogo generico de cadastros"
```

---

### Task 7: Use cases de clientes e produtos (unit)

**Files:**
- Create: `backend/src/sac/application/use_cases/customers.py`
- Create: `backend/src/sac/application/use_cases/products.py`
- Modify: `backend/tests/unit/fakes.py` (`InMemoryCustomerRepository`, `InMemoryProductRepository`)
- Test: `backend/tests/unit/application/test_customers_use_cases.py`, `backend/tests/unit/application/test_products_use_cases.py`

**Interfaces:**
- Consumes: entidades/ports (Task 3), `validate_document`/`normalize_digits`/`validate_state` (Task 2), erros de domínio.
- Produces:
  - `CustomerInput(name, document, phone=None, email=None, cep=None, street=None, number=None, complement=None, neighborhood=None, city=None, state=None)` (frozen dataclass).
  - `ListCustomersUseCase(repo).execute(search=None, active=None, page=1, per_page=20) -> tuple[list[Customer], int]` (clamp: page >= 1; per_page entre 1 e 100).
  - `CreateCustomerUseCase(repo).execute(data) -> Customer`; `UpdateCustomerUseCase(repo).execute(customer_id, data) -> Customer`; `SetCustomerActiveUseCase(repo).execute(customer_id, active) -> Customer`. Regras: nome strip obrigatório; documento validado/normalizado; telefone e CEP normalizados para dígitos (CEP com 8 dígitos senão `ValidationError`); UF validada; conflito de documento com outro id -> `ConflictError`.
  - `ProductInput(name, sku, segment=None, description=None)`; `ListProductsUseCase`, `CreateProductUseCase`, `UpdateProductUseCase`, `SetProductActiveUseCase` análogos (SKU strip obrigatório, conflito por `get_by_sku`; `photo_key` não é aceito no input — permanece o valor atual no update).

- [ ] **Step 1: Acrescentar fakes em `backend/tests/unit/fakes.py`**

```python
from sac.domain.cadastros import Customer, Product


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Customer] = {}

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Customer], int]:
        result = [c for c in self.items.values() if c.deleted_at is None]
        if search:
            lowered = search.lower()
            result = [
                c for c in result if lowered in c.name.lower() or lowered in c.document
            ]
        if active is not None:
            result = [c for c in result if c.active == active]
        result.sort(key=lambda c: c.name)
        start = (page - 1) * per_page
        return result[start : start + per_page], len(result)

    async def get(self, customer_id: UUID) -> Customer | None:
        customer = self.items.get(customer_id)
        return customer if customer and customer.deleted_at is None else None

    async def get_by_document(self, document: str) -> Customer | None:
        return next(
            (c for c in self.items.values() if c.document == document and c.deleted_at is None),
            None,
        )

    async def add(self, customer: Customer) -> None:
        if await self.get_by_document(customer.document):
            raise ConflictError("documento ja cadastrado")
        self.items[customer.id] = customer

    async def update(self, customer: Customer) -> None:
        if customer.id not in self.items:
            raise NotFoundError("cliente nao encontrado")
        self.items[customer.id] = customer


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Product] = {}

    async def list(
        self, search: str | None, active: bool | None, page: int, per_page: int
    ) -> tuple[list[Product], int]:
        result = [p for p in self.items.values() if p.deleted_at is None]
        if search:
            lowered = search.lower()
            result = [
                p for p in result if lowered in p.name.lower() or lowered in p.sku.lower()
            ]
        if active is not None:
            result = [p for p in result if p.active == active]
        result.sort(key=lambda p: p.name)
        start = (page - 1) * per_page
        return result[start : start + per_page], len(result)

    async def get(self, product_id: UUID) -> Product | None:
        product = self.items.get(product_id)
        return product if product and product.deleted_at is None else None

    async def get_by_sku(self, sku: str) -> Product | None:
        return next(
            (p for p in self.items.values() if p.sku == sku and p.deleted_at is None), None
        )

    async def add(self, product: Product) -> None:
        if await self.get_by_sku(product.sku):
            raise ConflictError("SKU ja cadastrado")
        self.items[product.id] = product

    async def update(self, product: Product) -> None:
        if product.id not in self.items:
            raise NotFoundError("produto nao encontrado")
        self.items[product.id] = product
```

- [ ] **Step 2: Escrever os testes que falham**

`backend/tests/unit/application/test_customers_use_cases.py`:

```python
import pytest

from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    ListCustomersUseCase,
    SetCustomerActiveUseCase,
    UpdateCustomerUseCase,
)
from sac.domain.errors import ConflictError, ValidationError
from tests.unit.fakes import InMemoryCustomerRepository


def _input(document: str = "529.982.247-25", **kwargs: str | None) -> CustomerInput:
    base: dict[str, str | None] = {
        "name": "Ana Silva",
        "document": document,
        "phone": "(54) 99982-3566",
        "cep": "95010-000",
        "state": "rs",
    }
    base.update(kwargs)
    return CustomerInput(**base)  # type: ignore[arg-type]


async def test_criar_normaliza_documento_telefone_cep_e_uf() -> None:
    repo = InMemoryCustomerRepository()
    customer = await CreateCustomerUseCase(repo).execute(_input())
    assert customer.document == "52998224725"
    assert customer.phone == "54999823566"
    assert customer.cep == "95010000"
    assert customer.state == "RS"


async def test_documento_invalido_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCustomerUseCase(InMemoryCustomerRepository()).execute(
            _input(document="123.456.789-00")
        )


async def test_cep_invalido_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateCustomerUseCase(InMemoryCustomerRepository()).execute(_input(cep="1234"))


async def test_documento_duplicado_gera_conflito() -> None:
    repo = InMemoryCustomerRepository()
    await CreateCustomerUseCase(repo).execute(_input())
    with pytest.raises(ConflictError):
        await CreateCustomerUseCase(repo).execute(_input(name="Outra"))


async def test_atualizar_preserva_id_e_detecta_conflito() -> None:
    repo = InMemoryCustomerRepository()
    create = CreateCustomerUseCase(repo)
    ana = await create.execute(_input())
    bia = await create.execute(_input(document="153.509.460-56", name="Bia"))

    atualizado = await UpdateCustomerUseCase(repo).execute(ana.id, _input(name="Ana Maria"))
    assert atualizado.id == ana.id and atualizado.name == "Ana Maria"

    with pytest.raises(ConflictError):
        await UpdateCustomerUseCase(repo).execute(bia.id, _input(document="529.982.247-25"))


async def test_listagem_paginada_e_clamp() -> None:
    repo = InMemoryCustomerRepository()
    create = CreateCustomerUseCase(repo)
    await create.execute(_input())
    await create.execute(_input(document="153.509.460-56", name="Bia"))
    await create.execute(_input(document="11.222.333/0001-81", name="Cia Ltda"))

    itens, total = await ListCustomersUseCase(repo).execute(page=1, per_page=2)
    assert total == 3 and len(itens) == 2

    itens, total = await ListCustomersUseCase(repo).execute(page=0, per_page=1000)
    assert total == 3 and len(itens) == 3


async def test_inativar_cliente() -> None:
    repo = InMemoryCustomerRepository()
    customer = await CreateCustomerUseCase(repo).execute(_input())
    inativado = await SetCustomerActiveUseCase(repo).execute(customer.id, False)
    assert inativado.active is False
```

`backend/tests/unit/application/test_products_use_cases.py`:

```python
import pytest

from sac.application.use_cases.products import (
    CreateProductUseCase,
    ListProductsUseCase,
    ProductInput,
    SetProductActiveUseCase,
    UpdateProductUseCase,
)
from sac.domain.errors import ConflictError, ValidationError
from tests.unit.fakes import InMemoryProductRepository


async def test_criar_produto_normaliza_sku() -> None:
    repo = InMemoryProductRepository()
    product = await CreateProductUseCase(repo).execute(
        ProductInput(name="Alicate", sku="  PLN-10-7  ", segment="Manicure")
    )
    assert product.sku == "PLN-10-7"
    assert product.photo_key is None


async def test_sku_vazio_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        await CreateProductUseCase(InMemoryProductRepository()).execute(
            ProductInput(name="Alicate", sku="  ")
        )


async def test_sku_duplicado_gera_conflito() -> None:
    repo = InMemoryProductRepository()
    await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    with pytest.raises(ConflictError):
        await CreateProductUseCase(repo).execute(ProductInput(name="B", sku="X-1"))


async def test_atualizar_produto_preserva_photo_key() -> None:
    repo = InMemoryProductRepository()
    product = await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    guardado = await repo.get(product.id)
    assert guardado is not None
    guardado.photo_key = "tenant/produto/foto.webp"
    await repo.update(guardado)

    atualizado = await UpdateProductUseCase(repo).execute(
        product.id, ProductInput(name="A2", sku="X-1")
    )
    assert atualizado.photo_key == "tenant/produto/foto.webp"
    assert atualizado.name == "A2"


async def test_listar_e_inativar() -> None:
    repo = InMemoryProductRepository()
    product = await CreateProductUseCase(repo).execute(ProductInput(name="A", sku="X-1"))
    itens, total = await ListProductsUseCase(repo).execute(search="x-1")
    assert total == 1 and itens[0].id == product.id

    inativado = await SetProductActiveUseCase(repo).execute(product.id, False)
    assert inativado.active is False
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_customers_use_cases.py tests/unit/application/test_products_use_cases.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 4: Implementar `backend/src/sac/application/use_cases/customers.py`**

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import CustomerRepository
from sac.domain.cadastros import Customer
from sac.domain.documents import normalize_digits, validate_document, validate_state
from sac.domain.errors import ConflictError, NotFoundError, ValidationError

MAX_PER_PAGE = 100


def clamp_page(page: int, per_page: int) -> tuple[int, int]:
    return max(page, 1), min(max(per_page, 1), MAX_PER_PAGE)


@dataclass(frozen=True)
class CustomerInput:
    name: str
    document: str
    phone: str | None = None
    email: str | None = None
    cep: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class _NormalizedCustomer:
    name: str
    document: str
    phone: str | None
    email: str | None
    cep: str | None
    street: str | None
    number: str | None
    complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize(data: CustomerInput) -> _NormalizedCustomer:
    name = data.name.strip()
    if not name:
        raise ValidationError("nome obrigatorio")
    document = validate_document(data.document)
    phone = normalize_digits(data.phone) or None if data.phone else None
    cep = None
    if _clean(data.cep):
        cep = normalize_digits(data.cep or "")
        if len(cep) != 8:
            raise ValidationError("CEP invalido: use 8 digitos")
    state = validate_state(data.state) if _clean(data.state) else None
    return _NormalizedCustomer(
        name=name,
        document=document,
        phone=phone,
        email=_clean(data.email),
        cep=cep,
        street=_clean(data.street),
        number=_clean(data.number),
        complement=_clean(data.complement),
        neighborhood=_clean(data.neighborhood),
        city=_clean(data.city),
        state=state,
    )


class ListCustomersUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        search: str | None = None,
        active: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Customer], int]:
        page, per_page = clamp_page(page, per_page)
        return await self._repo.list(search, active, page, per_page)


class CreateCustomerUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, data: CustomerInput) -> Customer:
        normalized = _normalize(data)
        if await self._repo.get_by_document(normalized.document) is not None:
            raise ConflictError("documento ja cadastrado")
        customer = Customer(
            id=uuid4(),
            name=normalized.name,
            document=normalized.document,
            phone=normalized.phone,
            email=normalized.email,
            cep=normalized.cep,
            street=normalized.street,
            number=normalized.number,
            complement=normalized.complement,
            neighborhood=normalized.neighborhood,
            city=normalized.city,
            state=normalized.state,
        )
        await self._repo.add(customer)
        return customer


class UpdateCustomerUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, customer_id: UUID, data: CustomerInput) -> Customer:
        customer = await self._repo.get(customer_id)
        if customer is None:
            raise NotFoundError("cliente nao encontrado")
        normalized = _normalize(data)
        existing = await self._repo.get_by_document(normalized.document)
        if existing is not None and existing.id != customer_id:
            raise ConflictError("documento ja cadastrado")
        customer.name = normalized.name
        customer.document = normalized.document
        customer.phone = normalized.phone
        customer.email = normalized.email
        customer.cep = normalized.cep
        customer.street = normalized.street
        customer.number = normalized.number
        customer.complement = normalized.complement
        customer.neighborhood = normalized.neighborhood
        customer.city = normalized.city
        customer.state = normalized.state
        await self._repo.update(customer)
        return customer


class SetCustomerActiveUseCase:
    def __init__(self, repo: CustomerRepository) -> None:
        self._repo = repo

    async def execute(self, customer_id: UUID, active: bool) -> Customer:
        customer = await self._repo.get(customer_id)
        if customer is None:
            raise NotFoundError("cliente nao encontrado")
        customer.active = active
        await self._repo.update(customer)
        return customer
```

- [ ] **Step 5: Implementar `backend/src/sac/application/use_cases/products.py`**

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports_cadastros import ProductRepository
from sac.application.use_cases.customers import clamp_page
from sac.domain.cadastros import Product
from sac.domain.errors import ConflictError, NotFoundError, ValidationError


@dataclass(frozen=True)
class ProductInput:
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize(data: ProductInput) -> tuple[str, str, str | None, str | None]:
    name = data.name.strip()
    if not name:
        raise ValidationError("nome obrigatorio")
    sku = data.sku.strip()
    if not sku:
        raise ValidationError("SKU obrigatorio")
    return name, sku, _clean(data.segment), _clean(data.description)


class ListProductsUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        search: str | None = None,
        active: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Product], int]:
        page, per_page = clamp_page(page, per_page)
        return await self._repo.list(search, active, page, per_page)


class CreateProductUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, data: ProductInput) -> Product:
        name, sku, segment, description = _normalize(data)
        if await self._repo.get_by_sku(sku) is not None:
            raise ConflictError("SKU ja cadastrado")
        product = Product(
            id=uuid4(), name=name, sku=sku, segment=segment, description=description
        )
        await self._repo.add(product)
        return product


class UpdateProductUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, product_id: UUID, data: ProductInput) -> Product:
        product = await self._repo.get(product_id)
        if product is None:
            raise NotFoundError("produto nao encontrado")
        name, sku, segment, description = _normalize(data)
        existing = await self._repo.get_by_sku(sku)
        if existing is not None and existing.id != product_id:
            raise ConflictError("SKU ja cadastrado")
        product.name = name
        product.sku = sku
        product.segment = segment
        product.description = description
        await self._repo.update(product)
        return product


class SetProductActiveUseCase:
    def __init__(self, repo: ProductRepository) -> None:
        self._repo = repo

    async def execute(self, product_id: UUID, active: bool) -> Product:
        product = await self._repo.get(product_id)
        if product is None:
            raise NotFoundError("produto nao encontrado")
        product.active = active
        await self._repo.update(product)
        return product
```

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/unit/application -v`
Esperado: PASS.

- [ ] **Step 7: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/application/use_cases backend/tests/unit
git commit -m "Adiciona use cases de clientes e produtos"
```

---

### Task 8: Interface — tenant session e API do catálogo

**Files:**
- Modify: `backend/src/sac/interface/deps.py` (get_tenant_session + factory de repositório de catálogo)
- Modify: `backend/src/sac/interface/schemas.py` (CatalogItemIn/Out, ActiveIn, catalog_out)
- Create: `backend/src/sac/interface/routers/cadastros_catalog.py`
- Modify: `backend/src/sac/interface/app.py` (registrar os 4 routers)
- Modify: `backend/tests/integration/helpers.py` (seed_provisioned_tenant)
- Test: `backend/tests/integration/test_cadastros_catalog_api.py`

**Interfaces:**
- Consumes: use cases (Task 6), `SqlCatalogRepository`/`CATALOG_MODELS` (Task 5), `require_permission`/`get_current_identity` (Fase 0), `AlembicTenantProvisioner`.
- Produces:
  - `get_tenant_session` (dependency async): exige `identity.tenant_slug` (senão `AuthError`), session com `schema_translate_map={"tenant": f"t_{slug}"}`, commit no sucesso/rollback no erro.
  - `get_catalog_repository(kind: CatalogKind)` -> dependency que retorna `SqlCatalogRepository`.
  - `build_catalog_router(kind: CatalogKind, path: str) -> APIRouter` com rotas `GET ""` (query `search`, `active`; permissão LISTAR_CADASTROS), `POST ""` 201 (CRIAR_LISTAR_CADASTROS), `PUT "/{item_id}"` (GERENCIAR_CADASTROS), `PATCH "/{item_id}/active"` (GERENCIAR_CADASTROS). Instâncias: marcas, defeitos, solucoes, canais sob `/api/cadastros/...`.
  - Schemas: `CatalogItemIn(name: str, description: str | None = None)`, `CatalogItemOut(id, name, description, active)`, `ActiveIn(active: bool)`, helper `catalog_out(item) -> CatalogItemOut`.
  - Helper de teste: `seed_provisioned_tenant(session, engine, *, slug) -> Tenant` (cria a linha do tenant e provisiona o schema).

- [ ] **Step 1: Acrescentar `get_tenant_session` e factory em `backend/src/sac/interface/deps.py`**

Imports adicionais: `from sqlalchemy.ext.asyncio import async_sessionmaker`, `from sac.domain.catalog import CatalogKind`, `from sac.infrastructure.repositories_cadastros import SqlCatalogRepository`.

```python
async def get_tenant_session(
    request: Request,
    identity: TokenPayload = Depends(get_current_identity),
) -> AsyncIterator[AsyncSession]:
    if identity.tenant_slug is None:
        raise AuthError("token sem tenant")
    schema = f"t_{identity.tenant_slug}"
    engine = request.app.state.engine.execution_options(
        schema_translate_map={"tenant": schema}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_catalog_repository(
    kind: CatalogKind,
) -> Callable[..., SqlCatalogRepository]:
    def factory(session: AsyncSession = Depends(get_tenant_session)) -> SqlCatalogRepository:
        return SqlCatalogRepository(session, kind)

    return factory
```

- [ ] **Step 2: Acrescentar schemas em `backend/src/sac/interface/schemas.py`**

```python
from sac.domain.catalog import CatalogItem


class CatalogItemIn(BaseModel):
    name: str
    description: str | None = None


class CatalogItemOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    active: bool


class ActiveIn(BaseModel):
    active: bool


def catalog_out(item: CatalogItem) -> CatalogItemOut:
    return CatalogItemOut(
        id=item.id, name=item.name, description=item.description, active=item.active
    )
```

- [ ] **Step 3: Criar `backend/src/sac/interface/routers/cadastros_catalog.py`**

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.catalog import (
    CatalogItemInput,
    CreateCatalogItemUseCase,
    ListCatalogUseCase,
    SetCatalogItemActiveUseCase,
    UpdateCatalogItemUseCase,
)
from sac.domain.catalog import CatalogKind
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository
from sac.interface.deps import get_catalog_repository, require_permission
from sac.interface.schemas import ActiveIn, CatalogItemIn, CatalogItemOut, catalog_out


def build_catalog_router(kind: CatalogKind, path: str) -> APIRouter:
    router = APIRouter(prefix=f"/cadastros/{path}", tags=["cadastros"])
    repo_dep = get_catalog_repository(kind)

    @router.get(
        "",
        response_model=list[CatalogItemOut],
        dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
    )
    async def list_items(
        search: str | None = None,
        active: bool | None = None,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> list[CatalogItemOut]:
        items = await ListCatalogUseCase(repo).execute(search, active)
        return [catalog_out(i) for i in items]

    @router.post(
        "",
        response_model=CatalogItemOut,
        status_code=201,
        dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
    )
    async def create_item(
        body: CatalogItemIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        item = await CreateCatalogItemUseCase(repo).execute(
            CatalogItemInput(name=body.name, description=body.description)
        )
        return catalog_out(item)

    @router.put(
        "/{item_id}",
        response_model=CatalogItemOut,
        dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
    )
    async def update_item(
        item_id: UUID,
        body: CatalogItemIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        item = await UpdateCatalogItemUseCase(repo).execute(
            item_id, CatalogItemInput(name=body.name, description=body.description)
        )
        return catalog_out(item)

    @router.patch(
        "/{item_id}/active",
        response_model=CatalogItemOut,
        dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
    )
    async def set_active(
        item_id: UUID,
        body: ActiveIn,
        repo: SqlCatalogRepository = Depends(repo_dep),
    ) -> CatalogItemOut:
        return catalog_out(await SetCatalogItemActiveUseCase(repo).execute(item_id, body.active))

    return router


marcas_router = build_catalog_router(CatalogKind.BRAND, "marcas")
defeitos_router = build_catalog_router(CatalogKind.DEFECT_TYPE, "defeitos")
solucoes_router = build_catalog_router(CatalogKind.SOLUTION_TYPE, "solucoes")
canais_router = build_catalog_router(CatalogKind.PURCHASE_CHANNEL, "canais")
```

Em `backend/src/sac/interface/app.py`:

```python
from sac.interface.routers import cadastros_catalog
...
    app.include_router(cadastros_catalog.marcas_router, prefix="/api")
    app.include_router(cadastros_catalog.defeitos_router, prefix="/api")
    app.include_router(cadastros_catalog.solucoes_router, prefix="/api")
    app.include_router(cadastros_catalog.canais_router, prefix="/api")
```

- [ ] **Step 4: Acrescentar helper em `backend/tests/integration/helpers.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine

from sac.infrastructure.provisioning import AlembicTenantProvisioner


async def seed_provisioned_tenant(
    session: AsyncSession, engine: AsyncEngine, *, slug: str
) -> Tenant:
    tenant = await seed_tenant(session, slug=slug)
    await AlembicTenantProvisioner(engine).provision(tenant.schema_name)
    return tenant
```

- [ ] **Step 5: Escrever o teste de integração que falha**

`backend/tests/integration/test_cadastros_catalog_api.py` (nota: tolerante a seeds — verifica presença/ausência por nome único, nunca contagens):

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def test_crud_de_marcas_pelo_admin(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="admin@b2.com")
    await seed_provisioned_tenant(session, engine, slug="alfa")
    headers = token_for(user, tenant_slug="alfa", role=Role.ADMIN)

    created = await client.post(
        "/api/cadastros/marcas", json={"name": "MARCA-NOVA"}, headers=headers
    )
    assert created.status_code == 201
    marca = created.json()

    listed = await client.get("/api/cadastros/marcas", headers=headers)
    assert listed.status_code == 200
    assert any(i["name"] == "MARCA-NOVA" for i in listed.json())

    updated = await client.put(
        f"/api/cadastros/marcas/{marca['id']}",
        json={"name": "MARCA-RENOMEADA", "description": "desc"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "MARCA-RENOMEADA"

    disabled = await client.patch(
        f"/api/cadastros/marcas/{marca['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False

    inativos = await client.get("/api/cadastros/marcas?active=false", headers=headers)
    assert any(i["name"] == "MARCA-RENOMEADA" for i in inativos.json())

    duplicada = await client.post(
        "/api/cadastros/marcas", json={"name": "MARCA-RENOMEADA"}, headers=headers
    )
    assert duplicada.status_code == 409


async def test_permissoes_por_papel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="user@b2.com")
    await seed_provisioned_tenant(session, engine, slug="beta")
    visualizador = token_for(user, tenant_slug="beta", role=Role.VISUALIZADOR)
    atendente = token_for(user, tenant_slug="beta", role=Role.ATENDENTE)

    assert (await client.get("/api/cadastros/defeitos", headers=visualizador)).status_code == 200
    assert (
        await client.post(
            "/api/cadastros/defeitos", json={"name": "X-VIS"}, headers=visualizador
        )
    ).status_code == 403

    criado = await client.post(
        "/api/cadastros/defeitos", json={"name": "X-ATD"}, headers=atendente
    )
    assert criado.status_code == 201
    assert (
        await client.put(
            f"/api/cadastros/defeitos/{criado.json()['id']}",
            json={"name": "X-ATD-2"},
            headers=atendente,
        )
    ).status_code == 403


async def test_super_admin_sem_papel_de_tenant_recebe_403(
    client: AsyncClient, session: AsyncSession
) -> None:
    sa = await seed_user(session, email="sa@b2.com", is_super_admin=True)
    response = await client.get("/api/cadastros/marcas", headers=token_for(sa))
    assert response.status_code == 403


async def test_sem_token_recebe_401(client: AsyncClient) -> None:
    assert (await client.get("/api/cadastros/marcas")).status_code == 401


async def test_isolamento_entre_tenants(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="iso@b2.com")
    await seed_provisioned_tenant(session, engine, slug="iso_a")
    await seed_provisioned_tenant(session, engine, slug="iso_b")
    headers_a = token_for(user, tenant_slug="iso_a", role=Role.ADMIN)
    headers_b = token_for(user, tenant_slug="iso_b", role=Role.ADMIN)

    created = await client.post(
        "/api/cadastros/canais", json={"name": "CANAL-SO-DO-A"}, headers=headers_a
    )
    assert created.status_code == 201

    no_a = await client.get("/api/cadastros/canais", headers=headers_a)
    no_b = await client.get("/api/cadastros/canais", headers=headers_b)
    assert any(i["name"] == "CANAL-SO-DO-A" for i in no_a.json())
    assert not any(i["name"] == "CANAL-SO-DO-A" for i in no_b.json())
```

- [ ] **Step 6: Rodar e ver falhar, depois passar**

Run: `uv run pytest tests/integration/test_cadastros_catalog_api.py -v`
Esperado: FAIL (404) antes do Step 3 aplicado; PASS depois de tudo implementado.

- [ ] **Step 7: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests
git commit -m "Adiciona session de tenant e API generica de catalogo de cadastros"
```

---

### Task 9: Interface — API de clientes e produtos

**Files:**
- Modify: `backend/src/sac/interface/schemas.py` (Customer/Product In/Out + páginas)
- Modify: `backend/src/sac/interface/deps.py` (factories de repositórios)
- Create: `backend/src/sac/interface/routers/cadastros_customers.py`
- Create: `backend/src/sac/interface/routers/cadastros_products.py`
- Modify: `backend/src/sac/interface/app.py` (registrar routers)
- Test: `backend/tests/integration/test_cadastros_customers_api.py`, `backend/tests/integration/test_cadastros_products_api.py`

**Interfaces:**
- Consumes: use cases (Task 7), `SqlCustomerRepository`/`SqlProductRepository` (Task 5), `get_tenant_session` (Task 8), `seed_provisioned_tenant`.
- Produces:
  - Rotas: `GET/POST /api/cadastros/clientes`, `PUT /api/cadastros/clientes/{id}`, `PATCH /api/cadastros/clientes/{id}/active`; idem `/api/cadastros/produtos`. GET com query `search`, `active`, `page` (default 1), `per_page` (default 20).
  - Schemas: `CustomerIn` (name, document, phone?, email?, cep?, street?, number?, complement?, neighborhood?, city?, state?), `CustomerOut` (idem + id, active), `CustomersPageOut(items, total, page, per_page)`; `ProductIn(name, sku, segment?, description?)`, `ProductOut(id, name, sku, segment, description, photo_key, active)`, `ProductsPageOut(items, total, page, per_page)`.
  - Permissões idênticas às do catálogo (listar/criar/gerenciar).

- [ ] **Step 1: Escrever os testes de integração que falham**

`backend/tests/integration/test_cadastros_customers_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def _admin_headers(
    session: AsyncSession, engine: AsyncEngine, slug: str
) -> dict[str, str]:
    user = await seed_user(session, email=f"admin-{slug}@b2.com")
    await seed_provisioned_tenant(session, engine, slug=slug)
    return token_for(user, tenant_slug=slug, role=Role.ADMIN)


async def test_crud_de_clientes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_a")

    created = await client.post(
        "/api/cadastros/clientes",
        json={
            "name": "Ana Silva",
            "document": "529.982.247-25",
            "phone": "(54) 99982-3566",
            "cep": "95010-000",
            "state": "rs",
        },
        headers=headers,
    )
    assert created.status_code == 201
    cliente = created.json()
    assert cliente["document"] == "52998224725"
    assert cliente["state"] == "RS"

    busca = await client.get("/api/cadastros/clientes?search=529.982", headers=headers)
    assert busca.status_code == 200
    assert busca.json()["total"] == 1

    updated = await client.put(
        f"/api/cadastros/clientes/{cliente['id']}",
        json={"name": "Ana Maria", "document": "529.982.247-25"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Ana Maria"

    disabled = await client.patch(
        f"/api/cadastros/clientes/{cliente['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False


async def test_documento_invalido_422_e_duplicado_409(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_b")
    payload = {"name": "Ana", "document": "529.982.247-25"}

    invalido = await client.post(
        "/api/cadastros/clientes",
        json={"name": "Ana", "document": "123.456.789-00"},
        headers=headers,
    )
    assert invalido.status_code == 422
    assert invalido.json()["code"] == "validation_error"

    assert (
        await client.post("/api/cadastros/clientes", json=payload, headers=headers)
    ).status_code == 201
    duplicado = await client.post("/api/cadastros/clientes", json=payload, headers=headers)
    assert duplicado.status_code == 409


async def test_paginacao_de_clientes(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    headers = await _admin_headers(session, engine, "cli_c")
    documentos = ["529.982.247-25", "153.509.460-56", "11.222.333/0001-81"]
    for i, doc in enumerate(documentos):
        response = await client.post(
            "/api/cadastros/clientes",
            json={"name": f"Cliente {i}", "document": doc},
            headers=headers,
        )
        assert response.status_code == 201

    pagina = await client.get(
        "/api/cadastros/clientes?page=1&per_page=2", headers=headers
    )
    body = pagina.json()
    assert body["total"] == 3 and len(body["items"]) == 2 and body["per_page"] == 2
```

`backend/tests/integration/test_cadastros_products_api.py`:

```python
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import seed_provisioned_tenant, seed_user, token_for


async def test_crud_de_produtos_e_conflito_de_sku(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="prod@b2.com")
    await seed_provisioned_tenant(session, engine, slug="prod_a")
    headers = token_for(user, tenant_slug="prod_a", role=Role.SUPERVISOR)

    created = await client.post(
        "/api/cadastros/produtos",
        json={"name": "Alicate", "sku": "PLN-10-7", "segment": "Manicure"},
        headers=headers,
    )
    assert created.status_code == 201
    produto = created.json()
    assert produto["photo_key"] is None

    duplicado = await client.post(
        "/api/cadastros/produtos",
        json={"name": "Outro", "sku": "PLN-10-7"},
        headers=headers,
    )
    assert duplicado.status_code == 409

    busca = await client.get("/api/cadastros/produtos?search=pln-10", headers=headers)
    assert busca.json()["total"] == 1

    updated = await client.put(
        f"/api/cadastros/produtos/{produto['id']}",
        json={"name": "Alicate Pro", "sku": "PLN-10-7", "segment": "Manicure"},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Alicate Pro"

    disabled = await client.patch(
        f"/api/cadastros/produtos/{produto['id']}/active",
        json={"active": False},
        headers=headers,
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False


async def test_atendente_cria_mas_nao_edita_produto(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    user = await seed_user(session, email="atd@b2.com")
    await seed_provisioned_tenant(session, engine, slug="prod_b")
    headers = token_for(user, tenant_slug="prod_b", role=Role.ATENDENTE)

    created = await client.post(
        "/api/cadastros/produtos", json={"name": "A", "sku": "SKU-ATD"}, headers=headers
    )
    assert created.status_code == 201
    assert (
        await client.put(
            f"/api/cadastros/produtos/{created.json()['id']}",
            json={"name": "B", "sku": "SKU-ATD"},
            headers=headers,
        )
    ).status_code == 403
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_cadastros_customers_api.py tests/integration/test_cadastros_products_api.py -v`
Esperado: FAIL (404).

- [ ] **Step 3: Schemas, deps e routers**

Acrescentar em `backend/src/sac/interface/schemas.py`:

```python
from sac.domain.cadastros import Customer, Product


class CustomerIn(BaseModel):
    name: str
    document: str
    phone: str | None = None
    email: str | None = None
    cep: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class CustomerOut(BaseModel):
    id: UUID
    name: str
    document: str
    phone: str | None
    email: str | None
    cep: str | None
    street: str | None
    number: str | None
    complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    active: bool


class CustomersPageOut(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    per_page: int


class ProductIn(BaseModel):
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None


class ProductOut(BaseModel):
    id: UUID
    name: str
    sku: str
    segment: str | None
    description: str | None
    photo_key: str | None
    active: bool


class ProductsPageOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    per_page: int


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut.model_validate(customer, from_attributes=True)


def product_out(product: Product) -> ProductOut:
    return ProductOut.model_validate(product, from_attributes=True)
```

Acrescentar em `backend/src/sac/interface/deps.py`:

```python
from sac.infrastructure.repositories_cadastros import (
    SqlCustomerRepository,
    SqlProductRepository,
)


def get_customer_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlCustomerRepository:
    return SqlCustomerRepository(session)


def get_product_repository(
    session: AsyncSession = Depends(get_tenant_session),
) -> SqlProductRepository:
    return SqlProductRepository(session)
```

Criar `backend/src/sac/interface/routers/cadastros_customers.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.customers import (
    CreateCustomerUseCase,
    CustomerInput,
    ListCustomersUseCase,
    SetCustomerActiveUseCase,
    UpdateCustomerUseCase,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlCustomerRepository
from sac.interface.deps import get_customer_repository, require_permission
from sac.interface.schemas import (
    ActiveIn,
    CustomerIn,
    CustomersPageOut,
    CustomerOut,
    customer_out,
)

router = APIRouter(prefix="/cadastros/clientes", tags=["cadastros"])


def _input(body: CustomerIn) -> CustomerInput:
    return CustomerInput(
        name=body.name,
        document=body.document,
        phone=body.phone,
        email=body.email,
        cep=body.cep,
        street=body.street,
        number=body.number,
        complement=body.complement,
        neighborhood=body.neighborhood,
        city=body.city,
        state=body.state,
    )


@router.get(
    "",
    response_model=CustomersPageOut,
    dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
)
async def list_customers(
    search: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 20,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomersPageOut:
    items, total = await ListCustomersUseCase(repo).execute(search, active, page, per_page)
    return CustomersPageOut(
        items=[customer_out(c) for c in items], total=total, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=CustomerOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
)
async def create_customer(
    body: CustomerIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await CreateCustomerUseCase(repo).execute(_input(body)))


@router.put(
    "/{customer_id}",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def update_customer(
    customer_id: UUID,
    body: CustomerIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await UpdateCustomerUseCase(repo).execute(customer_id, _input(body)))


@router.patch(
    "/{customer_id}/active",
    response_model=CustomerOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def set_customer_active(
    customer_id: UUID,
    body: ActiveIn,
    repo: SqlCustomerRepository = Depends(get_customer_repository),
) -> CustomerOut:
    return customer_out(await SetCustomerActiveUseCase(repo).execute(customer_id, body.active))
```

Criar `backend/src/sac/interface/routers/cadastros_products.py` (mesma estrutura):

```python
from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.products import (
    CreateProductUseCase,
    ListProductsUseCase,
    ProductInput,
    SetProductActiveUseCase,
    UpdateProductUseCase,
)
from sac.domain.permissions import Permission
from sac.infrastructure.repositories_cadastros import SqlProductRepository
from sac.interface.deps import get_product_repository, require_permission
from sac.interface.schemas import (
    ActiveIn,
    ProductIn,
    ProductOut,
    ProductsPageOut,
    product_out,
)

router = APIRouter(prefix="/cadastros/produtos", tags=["cadastros"])


@router.get(
    "",
    response_model=ProductsPageOut,
    dependencies=[Depends(require_permission(Permission.LISTAR_CADASTROS))],
)
async def list_products(
    search: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 20,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductsPageOut:
    items, total = await ListProductsUseCase(repo).execute(search, active, page, per_page)
    return ProductsPageOut(
        items=[product_out(p) for p in items], total=total, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=ProductOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CRIAR_LISTAR_CADASTROS))],
)
async def create_product(
    body: ProductIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(
        await CreateProductUseCase(repo).execute(
            ProductInput(
                name=body.name, sku=body.sku, segment=body.segment, description=body.description
            )
        )
    )


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def update_product(
    product_id: UUID,
    body: ProductIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(
        await UpdateProductUseCase(repo).execute(
            product_id,
            ProductInput(
                name=body.name, sku=body.sku, segment=body.segment, description=body.description
            ),
        )
    )


@router.patch(
    "/{product_id}/active",
    response_model=ProductOut,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def set_product_active(
    product_id: UUID,
    body: ActiveIn,
    repo: SqlProductRepository = Depends(get_product_repository),
) -> ProductOut:
    return product_out(await SetProductActiveUseCase(repo).execute(product_id, body.active))
```

Em `backend/src/sac/interface/app.py`, registrar `cadastros_customers.router` e `cadastros_products.router` com `prefix="/api"`.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_cadastros_customers_api.py tests/integration/test_cadastros_products_api.py -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests
git commit -m "Adiciona API de clientes e produtos com paginacao e busca"
```

---

### Task 10: Lookup de CEP pelo backend (ViaCEP)

**Files:**
- Modify: `backend/src/sac/domain/errors.py` (CepUnavailableError)
- Modify: `backend/src/sac/application/ports_cadastros.py` (CepAddress, CepGatewayPort)
- Create: `backend/src/sac/application/use_cases/cep.py`
- Create: `backend/src/sac/infrastructure/cep.py`
- Modify: `backend/src/sac/interface/errors.py` (STATUS_BY_CODE += 503)
- Modify: `backend/src/sac/interface/deps.py` (get_cep_gateway)
- Modify: `backend/src/sac/interface/schemas.py` (CepOut)
- Create: `backend/src/sac/interface/routers/cep.py`
- Modify: `backend/src/sac/interface/app.py` (registrar router)
- Modify: `backend/pyproject.toml` (httpx para dependências de runtime)
- Test: `backend/tests/unit/application/test_cep_use_case.py`, `backend/tests/integration/test_cep_api.py`

**Interfaces:**
- Consumes: `normalize_digits` (Task 2), `get_current_identity` (Fase 0).
- Produces:
  - `CepUnavailableError(DomainError)` code `"cep_indisponivel"` -> HTTP 503.
  - `CepAddress(cep: str, street: str, neighborhood: str, city: str, state: str)` (frozen dataclass); `CepGatewayPort(Protocol)` com `async lookup(cep: str) -> CepAddress | None` (levanta `CepUnavailableError` em falha de rede).
  - `LookupCepUseCase(gateway)` com `execute(cep: str) -> CepAddress` (formato inválido -> `ValidationError`; não encontrado -> `NotFoundError`).
  - `ViaCepGateway(timeout_seconds: float = 3.0)` implementando o port contra `https://viacep.com.br/ws/{cep}/json/`.
  - `get_cep_gateway() -> ViaCepGateway` (dependency importável — testes fazem override).
  - Rota `GET /api/cep/{cep}` (autenticada via `get_current_identity`) -> `CepOut(cep, street, neighborhood, city, state)`.

- [ ] **Step 1: Teste unitário do use case (falha primeiro)**

`backend/tests/unit/application/test_cep_use_case.py`:

```python
import pytest

from sac.application.ports_cadastros import CepAddress
from sac.application.use_cases.cep import LookupCepUseCase
from sac.domain.errors import CepUnavailableError, NotFoundError, ValidationError

ENDERECO = CepAddress(
    cep="95010000", street="Rua Sinimbu", neighborhood="Centro", city="Caxias do Sul", state="RS"
)


class StubGateway:
    def __init__(
        self, result: CepAddress | None = None, unavailable: bool = False
    ) -> None:
        self._result = result
        self._unavailable = unavailable
        self.chamado_com: str | None = None

    async def lookup(self, cep: str) -> CepAddress | None:
        self.chamado_com = cep
        if self._unavailable:
            raise CepUnavailableError("servico de CEP indisponivel")
        return self._result


async def test_lookup_normaliza_e_retorna() -> None:
    gateway = StubGateway(result=ENDERECO)
    result = await LookupCepUseCase(gateway).execute("95010-000")
    assert result == ENDERECO
    assert gateway.chamado_com == "95010000"


@pytest.mark.parametrize("cep", ["123", "abcdefgh", ""])
async def test_formato_invalido(cep: str) -> None:
    with pytest.raises(ValidationError):
        await LookupCepUseCase(StubGateway()).execute(cep)


async def test_nao_encontrado() -> None:
    with pytest.raises(NotFoundError):
        await LookupCepUseCase(StubGateway(result=None)).execute("95010000")


async def test_indisponivel_propaga() -> None:
    with pytest.raises(CepUnavailableError):
        await LookupCepUseCase(StubGateway(unavailable=True)).execute("95010000")
```

Run: `uv run pytest tests/unit/application/test_cep_use_case.py -v` — esperado FAIL.

- [ ] **Step 2: Implementar domínio/application**

Em `backend/src/sac/domain/errors.py`, acrescentar ao final:

```python
class CepUnavailableError(DomainError):
    code = "cep_indisponivel"
```

Em `backend/src/sac/application/ports_cadastros.py`, acrescentar:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CepAddress:
    cep: str
    street: str
    neighborhood: str
    city: str
    state: str


class CepGatewayPort(Protocol):
    async def lookup(self, cep: str) -> CepAddress | None: ...
```

Criar `backend/src/sac/application/use_cases/cep.py`:

```python
from sac.application.ports_cadastros import CepAddress, CepGatewayPort
from sac.domain.documents import normalize_digits
from sac.domain.errors import NotFoundError, ValidationError


class LookupCepUseCase:
    def __init__(self, gateway: CepGatewayPort) -> None:
        self._gateway = gateway

    async def execute(self, cep: str) -> CepAddress:
        digits = normalize_digits(cep)
        if len(digits) != 8:
            raise ValidationError("CEP invalido: use 8 digitos")
        result = await self._gateway.lookup(digits)
        if result is None:
            raise NotFoundError("CEP nao encontrado")
        return result
```

Run: `uv run pytest tests/unit/application/test_cep_use_case.py -v` — esperado PASS.

- [ ] **Step 3: Gateway, rota e mapeamento de erro**

Em `backend/pyproject.toml`, mover `"httpx>=0.27"` do grupo dev para `dependencies` (manter também no dev não é necessário; remover de dev). Rodar `uv sync`.

Criar `backend/src/sac/infrastructure/cep.py`:

```python
import httpx

from sac.application.ports_cadastros import CepAddress
from sac.domain.errors import CepUnavailableError

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"


class ViaCepGateway:
    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._timeout = timeout_seconds

    async def lookup(self, cep: str) -> CepAddress | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(VIACEP_URL.format(cep=cep))
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise CepUnavailableError("servico de CEP indisponivel") from exc
        if data.get("erro"):
            return None
        return CepAddress(
            cep=cep,
            street=data.get("logradouro", ""),
            neighborhood=data.get("bairro", ""),
            city=data.get("localidade", ""),
            state=data.get("uf", ""),
        )
```

Em `backend/src/sac/interface/errors.py`, acrescentar ao dicionário `STATUS_BY_CODE`:

```python
    "cep_indisponivel": 503,
```

Em `backend/src/sac/interface/deps.py`:

```python
from sac.infrastructure.cep import ViaCepGateway


def get_cep_gateway() -> ViaCepGateway:
    return ViaCepGateway()
```

Em `backend/src/sac/interface/schemas.py`:

```python
from sac.application.ports_cadastros import CepAddress


class CepOut(BaseModel):
    cep: str
    street: str
    neighborhood: str
    city: str
    state: str


def cep_out(address: CepAddress) -> CepOut:
    return CepOut(
        cep=address.cep,
        street=address.street,
        neighborhood=address.neighborhood,
        city=address.city,
        state=address.state,
    )
```

Criar `backend/src/sac/interface/routers/cep.py`:

```python
from fastapi import APIRouter, Depends

from sac.application.use_cases.cep import LookupCepUseCase
from sac.infrastructure.cep import ViaCepGateway
from sac.interface.deps import get_cep_gateway, get_current_identity
from sac.interface.schemas import CepOut, cep_out

router = APIRouter(prefix="/cep", tags=["cep"], dependencies=[Depends(get_current_identity)])


@router.get("/{cep}", response_model=CepOut)
async def lookup_cep(
    cep: str, gateway: ViaCepGateway = Depends(get_cep_gateway)
) -> CepOut:
    return cep_out(await LookupCepUseCase(gateway).execute(cep))
```

Em `backend/src/sac/interface/app.py`, registrar `cep.router` com `prefix="/api"`.

- [ ] **Step 4: Teste de integração com stub (sem rede)**

`backend/tests/integration/test_cep_api.py`:

```python
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_cadastros import CepAddress
from sac.domain.errors import CepUnavailableError
from sac.interface.deps import get_cep_gateway
from tests.integration.helpers import seed_user, token_for

ENDERECO = CepAddress(
    cep="95010000", street="Rua Sinimbu", neighborhood="Centro", city="Caxias do Sul", state="RS"
)


class StubGateway:
    def __init__(self, result: CepAddress | None = None, unavailable: bool = False) -> None:
        self._result = result
        self._unavailable = unavailable

    async def lookup(self, cep: str) -> CepAddress | None:
        if self._unavailable:
            raise CepUnavailableError("servico de CEP indisponivel")
        return self._result


@pytest.fixture
async def stubbed_client(app: FastAPI) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    app.dependency_overrides.clear()


async def test_cep_encontrado(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    user = await seed_user(session, email="cep@b2.com")

    response = await client.get("/api/cep/95010-000", headers=token_for(user))
    assert response.status_code == 200
    assert response.json() == {
        "cep": "95010000",
        "street": "Rua Sinimbu",
        "neighborhood": "Centro",
        "city": "Caxias do Sul",
        "state": "RS",
    }


async def test_cep_invalido_422(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    user = await seed_user(session, email="cep2@b2.com")
    assert (await client.get("/api/cep/123", headers=token_for(user))).status_code == 422


async def test_cep_nao_encontrado_404(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=None)
    user = await seed_user(session, email="cep3@b2.com")
    assert (await client.get("/api/cep/95010000", headers=token_for(user))).status_code == 404


async def test_cep_indisponivel_503(stubbed_client, session: AsyncSession) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(unavailable=True)
    user = await seed_user(session, email="cep4@b2.com")
    response = await client.get("/api/cep/95010000", headers=token_for(user))
    assert response.status_code == 503
    assert response.json()["code"] == "cep_indisponivel"


async def test_cep_sem_token_401(stubbed_client) -> None:
    client, app = stubbed_client
    app.dependency_overrides[get_cep_gateway] = lambda: StubGateway(result=ENDERECO)
    assert (await client.get("/api/cep/95010000")).status_code == 401
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_cep_use_case.py tests/integration/test_cep_api.py -v`
Esperado: PASS.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac backend/tests backend/pyproject.toml backend/uv.lock
git commit -m "Adiciona lookup de CEP pelo backend com gateway ViaCEP"
```

---

### Task 11: Seeds híbridos no provisionamento + CLI

**Files:**
- Create: `backend/src/sac/infrastructure/tenant_seeds.py`
- Modify: `backend/src/sac/infrastructure/provisioning.py` (semear após migrar)
- Create: `backend/src/sac/infrastructure/seed_tenant.py`
- Test: `backend/tests/integration/test_tenant_seeds.py`

**Interfaces:**
- Consumes: `SqlCatalogRepository`/`CATALOG_MODELS` (Task 5), `CatalogItem`/`CatalogKind` (Task 3), `validate_slug`, `SqlTenantRepository`, `build_engine`/`build_session_factory`, `Settings`.
- Produces:
  - Listas `DEFAULT_BRANDS`, `DEFAULT_DEFECT_TYPES`, `DEFAULT_SOLUTION_TYPES`, `DEFAULT_PURCHASE_CHANNELS` e `CATALOG_DEFAULTS: dict[CatalogKind, list[tuple[str, str | None]]]`.
  - `seed_tenant_defaults(session: AsyncSession) -> int` (idempotente por nome; retorna quantos criou).
  - `AlembicTenantProvisioner.provision` passa a semear defaults após aplicar as migrations (dentro do try de compensação).
  - CLI `python -m sac.infrastructure.seed_tenant <slug>` (tenant inexistente -> mensagem de orientação; sucesso -> "seeds aplicados: N itens criados").

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_tenant_seeds.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.catalog import CatalogKind
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository
from sac.infrastructure.seed_tenant import run as seed_tenant_run
from sac.infrastructure.tenant_seeds import seed_tenant_defaults
from tests.integration.helpers import seed_tenant


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def test_provisionamento_semeia_defaults(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_seed")

    async with _factory(engine, "t_seed")() as session:
        brands = SqlCatalogRepository(session, CatalogKind.BRAND)
        assert await brands.get_by_name("KODI") is not None
        assert await brands.get_by_name("STALEKS") is not None

        defects = await SqlCatalogRepository(session, CatalogKind.DEFECT_TYPE).list(None, None)
        assert {"Danificado", "Oxidacao", "Mau uso"} <= {d.name for d in defects}

        channels = await SqlCatalogRepository(session, CatalogKind.PURCHASE_CHANNEL).list(
            None, None
        )
        assert "Mercado Livre" in {c.name for c in channels}


async def test_seed_e_idempotente(engine: AsyncEngine) -> None:
    await AlembicTenantProvisioner(engine).provision("t_idem")
    async with _factory(engine, "t_idem")() as session:
        created = await seed_tenant_defaults(session)
        await session.commit()
    assert created == 0


async def test_cli_seed_tenant(engine: AsyncEngine, session: AsyncSession) -> None:
    assert "nao encontrado" in await seed_tenant_run("inexistente")

    await seed_tenant(session, slug="clitenant")
    await AlembicTenantProvisioner(engine).drop("t_clitenant")
    from sac.infrastructure.migrate import upgrade_tenant
    import asyncio

    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text('CREATE SCHEMA "t_clitenant"'))
    await asyncio.to_thread(upgrade_tenant, "t_clitenant")

    resultado = await seed_tenant_run("clitenant")
    assert "seeds aplicados" in resultado
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_tenant_seeds.py -v`
Esperado: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implementar `backend/src/sac/infrastructure/tenant_seeds.py`**

```python
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.catalog import CatalogItem, CatalogKind
from sac.infrastructure.repositories_cadastros import SqlCatalogRepository

DEFAULT_BRANDS: list[tuple[str, str | None]] = [("KODI", None), ("STALEKS", None)]

DEFAULT_DEFECT_TYPES: list[tuple[str, str | None]] = [
    ("Danificado", "Produto chegou danificado ou foi danificado no transporte."),
    ("Adaptacao/modelo errado", "Cliente solicita troca por outro modelo."),
    ("Nao recebeu", "Cliente nao recebeu o produto."),
    ("Sem afiacao/precisao", "Problema relacionado a falta de fio ou afiacao do produto."),
    ("Defeito de fabricacao", "Produto com defeito oriundo do processo de fabricacao."),
    ("Oxidacao", "Produto apresentou oxidacao."),
    ("Quebra da ferramenta", "Produto quebrou durante o uso."),
    ("Extraviado", "Produto extraviado no transporte."),
    ("Cancelado", "Reclamacao cancelada."),
    ("Arrependimento de compra", "Cliente deseja devolver o produto por arrependimento."),
    ("Produto divergente", "Produto recebido diferente do pedido."),
    ("Embalagem vazia", "Embalagem chegou sem o produto."),
    ("Mau uso", "Produto danificado por uso incorreto."),
    ("Fora do prazo", "Solicitacao fora do prazo de garantia."),
]

DEFAULT_SOLUTION_TYPES: list[tuple[str, str | None]] = [
    ("Troca pelo mesmo item", None),
    ("Troca por outro item", None),
    ("Envio de peca", None),
    ("Reembolso", None),
    ("50% off", None),
    ("100% off", None),
    ("Voucher", None),
    ("Desconto em nova compra", None),
    ("Orientado procurar marketplace/transportadora", None),
    ("Encaminhado para afiacao", None),
]

DEFAULT_PURCHASE_CHANNELS: list[tuple[str, str | None]] = [
    ("Site KODI", None),
    ("Site STALEKS", None),
    ("SAC", None),
    ("Beauty Show", None),
    ("Mercado Livre", None),
    ("Shopee", None),
    ("Revendedor", None),
]

CATALOG_DEFAULTS: dict[CatalogKind, list[tuple[str, str | None]]] = {
    CatalogKind.BRAND: DEFAULT_BRANDS,
    CatalogKind.DEFECT_TYPE: DEFAULT_DEFECT_TYPES,
    CatalogKind.SOLUTION_TYPE: DEFAULT_SOLUTION_TYPES,
    CatalogKind.PURCHASE_CHANNEL: DEFAULT_PURCHASE_CHANNELS,
}


async def seed_tenant_defaults(session: AsyncSession) -> int:
    created = 0
    for kind, defaults in CATALOG_DEFAULTS.items():
        repo = SqlCatalogRepository(session, kind)
        for name, description in defaults:
            if await repo.get_by_name(name) is None:
                await repo.add(CatalogItem(id=uuid4(), name=name, description=description))
                created += 1
    return created
```

- [ ] **Step 4: Integrar ao provisionamento e criar o CLI**

Em `backend/src/sac/infrastructure/provisioning.py`, dentro do `try` (após o `asyncio.to_thread(...)`):

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

from sac.infrastructure.tenant_seeds import seed_tenant_defaults

    async def provision(self, schema_name: str) -> None:
        # schema_name sempre deriva de slug validado por validate_slug
        async with self._engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        try:
            await asyncio.to_thread(migrate.upgrade_tenant, schema_name)
            translated = self._engine.execution_options(
                schema_translate_map={"tenant": schema_name}
            )
            factory = async_sessionmaker(translated, expire_on_commit=False)
            async with factory() as session:
                await seed_tenant_defaults(session)
                await session.commit()
        except Exception:
            await self.drop(schema_name)
            raise
```

Criar `backend/src/sac/infrastructure/seed_tenant.py`:

```python
import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from sac.domain.entities import validate_slug
from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.repositories import SqlTenantRepository
from sac.infrastructure.settings import Settings
from sac.infrastructure.tenant_seeds import seed_tenant_defaults


async def run(slug: str) -> str:
    validate_slug(slug)
    engine = build_engine(Settings().database_url)
    try:
        factory = build_session_factory(engine)
        async with factory() as session:
            tenant = await SqlTenantRepository(session).get_by_slug(slug)
            if tenant is None:
                return f"tenant nao encontrado: {slug}"
        translated = engine.execution_options(
            schema_translate_map={"tenant": f"t_{slug}"}
        )
        tenant_factory = async_sessionmaker(translated, expire_on_commit=False)
        async with tenant_factory() as session:
            created = await seed_tenant_defaults(session)
            await session.commit()
        return f"seeds aplicados: {created} itens criados"
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-seed-tenant")
    parser.add_argument("slug")
    args = parser.parse_args()
    print(asyncio.run(run(args.slug)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_tenant_seeds.py -v`
Esperado: PASS. Rodar também a suíte inteira (`uv run pytest`) — os testes de catálogo das Tasks 8-9 devem continuar verdes com os seeds presentes.

- [ ] **Step 6: Verificações completas e commit**

Rodar as verificações da seção Global Constraints (backend) e:

```bash
git add backend/src/sac/infrastructure backend/tests/integration/test_tenant_seeds.py
git commit -m "Adiciona seeds hibridos de cadastros no provisionamento e CLI"
```

---

### Task 12: Frontend — API client, formatos, guard e navegação

Antes de escrever UI, invocar o skill `frontend-design` e reler `docs/identidade-visual.md`.

**Files:**
- Create: `frontend/src/lib/cadastros.ts`
- Create: `frontend/src/lib/format.ts`
- Modify: `frontend/src/lib/guards.tsx` (RequireTenant)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (grupo Cadastros)
- Modify: `frontend/src/main.tsx` (rotas /cadastros/* — apontam para páginas criadas nas Tasks 13-15; nesta task registrar as rotas com placeholders `<p>` para o build passar, substituídos nas tasks seguintes)

**Interfaces:**
- Consumes: `api<T>` e `ApiError` de `@/lib/api`; `useAuth` de `@/lib/auth`.
- Produces (consumido pelas Tasks 13-15):
  - Tipos: `CatalogItem {id, name, description: string | null, active}`; `CatalogPath = "marcas" | "defeitos" | "solucoes" | "canais"`; `Customer` (todos os campos do backend + id/active); `Product {id, name, sku, segment, description, photo_key, active}`; `Page<T> {items: T[], total, page, per_page}`; `CepAddress {cep, street, neighborhood, city, state}`.
  - Funções: `listCatalog(path, params?: {search?, active?})`, `createCatalogItem(path, {name, description?})`, `updateCatalogItem(path, id, {name, description?})`, `setCatalogItemActive(path, id, active)`; `listCustomers({search?, active?, page?, perPage?})`, `createCustomer(input)`, `updateCustomer(id, input)`, `setCustomerActive(id, active)`; equivalentes de produtos; `lookupCep(cep)`.
  - Permissões de UI: `canCreateCadastros(role)` (role != "visualizador") e `canManageCadastros(role)` (admin ou supervisor).
  - `formatDocument(digits)` (11 -> 000.000.000-00; 14 -> 00.000.000/0000-00; senão retorna como veio), `formatPhone(digits)`, `formatCep(digits)`, `onlyDigits(value)`.
  - Guard `RequireTenant` (sessão com `tenantSlug` senão Navigate "/").
  - Sidebar: grupo "Cadastros" (Marcas, Produtos, Defeitos, Solucoes, Canais, Clientes) visível quando `session.tenantSlug != null`.

- [ ] **Step 1: Implementar `frontend/src/lib/format.ts`**

```ts
export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "")
}

export function formatDocument(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
  }
  if (digits.length === 14) {
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
  }
  return value
}

export function formatPhone(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 11) return digits.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3")
  if (digits.length === 10) return digits.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3")
  return value
}

export function formatCep(value: string): string {
  const digits = onlyDigits(value)
  if (digits.length === 8) return digits.replace(/(\d{5})(\d{3})/, "$1-$2")
  return value
}
```

- [ ] **Step 2: Implementar `frontend/src/lib/cadastros.ts`**

```ts
import { api } from "@/lib/api"

export type CatalogPath = "marcas" | "defeitos" | "solucoes" | "canais"

export type CatalogItem = {
  id: string
  name: string
  description: string | null
  active: boolean
}

export type CatalogItemInput = { name: string; description?: string | null }

export type Customer = {
  id: string
  name: string
  document: string
  phone: string | null
  email: string | null
  cep: string | null
  street: string | null
  number: string | null
  complement: string | null
  neighborhood: string | null
  city: string | null
  state: string | null
  active: boolean
}

export type CustomerInput = Omit<Customer, "id" | "active">

export type Product = {
  id: string
  name: string
  sku: string
  segment: string | null
  description: string | null
  photo_key: string | null
  active: boolean
}

export type ProductInput = Pick<Product, "name" | "sku" | "segment" | "description">

export type Page<T> = { items: T[]; total: number; page: number; per_page: number }

export type CepAddress = {
  cep: string
  street: string
  neighborhood: string
  city: string
  state: string
}

export function canCreateCadastros(role: string | null): boolean {
  return role !== null && role !== "visualizador"
}

export function canManageCadastros(role: string | null): boolean {
  return role === "admin" || role === "supervisor"
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}

export const listCatalog = (path: CatalogPath, params: { search?: string; active?: boolean } = {}) =>
  api<CatalogItem[]>(`/cadastros/${path}${query(params)}`)

export const createCatalogItem = (path: CatalogPath, input: CatalogItemInput) =>
  api<CatalogItem>(`/cadastros/${path}`, { method: "POST", body: input })

export const updateCatalogItem = (path: CatalogPath, id: string, input: CatalogItemInput) =>
  api<CatalogItem>(`/cadastros/${path}/${id}`, { method: "PUT", body: input })

export const setCatalogItemActive = (path: CatalogPath, id: string, active: boolean) =>
  api<CatalogItem>(`/cadastros/${path}/${id}/active`, { method: "PATCH", body: { active } })

export const listCustomers = (
  params: { search?: string; active?: boolean; page?: number; perPage?: number } = {},
) =>
  api<Page<Customer>>(
    `/cadastros/clientes${query({
      search: params.search,
      active: params.active,
      page: params.page,
      per_page: params.perPage,
    })}`,
  )

export const createCustomer = (input: CustomerInput) =>
  api<Customer>("/cadastros/clientes", { method: "POST", body: input })

export const updateCustomer = (id: string, input: CustomerInput) =>
  api<Customer>(`/cadastros/clientes/${id}`, { method: "PUT", body: input })

export const setCustomerActive = (id: string, active: boolean) =>
  api<Customer>(`/cadastros/clientes/${id}/active`, { method: "PATCH", body: { active } })

export const listProducts = (
  params: { search?: string; active?: boolean; page?: number; perPage?: number } = {},
) =>
  api<Page<Product>>(
    `/cadastros/produtos${query({
      search: params.search,
      active: params.active,
      page: params.page,
      per_page: params.perPage,
    })}`,
  )

export const createProduct = (input: ProductInput) =>
  api<Product>("/cadastros/produtos", { method: "POST", body: input })

export const updateProduct = (id: string, input: ProductInput) =>
  api<Product>(`/cadastros/produtos/${id}`, { method: "PUT", body: input })

export const setProductActive = (id: string, active: boolean) =>
  api<Product>(`/cadastros/produtos/${id}/active`, { method: "PATCH", body: { active } })

export const lookupCep = (cep: string) => api<CepAddress>(`/cep/${cep}`)
```

- [ ] **Step 3: Guard, sidebar e rotas**

Em `frontend/src/lib/guards.tsx`, acrescentar:

```tsx
export function RequireTenant() {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (!session.tenantSlug) return <Navigate to="/" replace />
  return <Outlet />
}
```

Em `frontend/src/components/layout/Sidebar.tsx`, acrescentar o grupo (imports de ícones lucide: `Tags, Package, Wrench, ClipboardCheck, Store, Contact`):

```tsx
  if (session?.tenantSlug) {
    groups.push({
      label: "Cadastros",
      items: [
        { to: "/cadastros/marcas", label: "Marcas", icon: Tags },
        { to: "/cadastros/produtos", label: "Produtos", icon: Package },
        { to: "/cadastros/defeitos", label: "Defeitos", icon: Wrench },
        { to: "/cadastros/solucoes", label: "Solucoes", icon: ClipboardCheck },
        { to: "/cadastros/canais", label: "Canais", icon: Store },
        { to: "/cadastros/clientes", label: "Clientes", icon: Contact },
      ],
    })
  }
```

Em `frontend/src/main.tsx`, dentro dos children do `AppShell`, acrescentar o bloco (placeholders substituídos nas Tasks 13-15):

```tsx
import { RequireTenant } from "@/lib/guards"

{
  element: <RequireTenant />,
  children: [
    { path: "/cadastros/marcas", element: <p>Marcas</p> },
    { path: "/cadastros/produtos", element: <p>Produtos</p> },
    { path: "/cadastros/defeitos", element: <p>Defeitos</p> },
    { path: "/cadastros/solucoes", element: <p>Solucoes</p> },
    { path: "/cadastros/canais", element: <p>Canais</p> },
    { path: "/cadastros/clientes", element: <p>Clientes</p> },
  ],
},
```

- [ ] **Step 4: Verificar e commitar**

Em `frontend/`: `pnpm lint && pnpm build` — esperado sucesso.

```bash
git add frontend
git commit -m "Adiciona client de cadastros, formatos, guard de tenant e navegacao"
```

---

### Task 13: Frontend — página genérica de catálogo (4 cadastros)

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md` (tabela densa, badge outline neutro, Paprika só no botão primário "Novo", empty state de texto direto, ícones lucide strokeWidth 1.5).

**Files:**
- Create: `frontend/src/pages/cadastros/CatalogPage.tsx`
- Modify: `frontend/src/main.tsx` (substituir os 4 placeholders)

**Interfaces:**
- Consumes: `listCatalog`/`createCatalogItem`/`updateCatalogItem`/`setCatalogItemActive`, `canCreateCadastros`/`canManageCadastros` (Task 12), `useAuth`, componentes shadcn existentes.
- Produces: `CatalogPage({ title, path }: { title: string; path: CatalogPath })` — usada nas rotas: marcas, defeitos, solucoes, canais.

- [ ] **Step 1: Implementar `CatalogPage.tsx`**

Estrutura funcional (refinamento visual pelo skill frontend-design):

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
import { ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import {
  canCreateCadastros,
  canManageCadastros,
  createCatalogItem,
  listCatalog,
  setCatalogItemActive,
  updateCatalogItem,
  type CatalogItem,
  type CatalogPath,
} from "@/lib/cadastros"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

export default function CatalogPage({ title, path }: { title: string; path: CatalogPath }) {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<CatalogItem | null>(null)

  const role = session?.role ?? null
  const podeCriar = canCreateCadastros(role)
  const podeGerenciar = canManageCadastros(role)

  const { data: items, isLoading } = useQuery({
    queryKey: ["catalog", path, search],
    queryFn: () => listCatalog(path, { search: search || undefined }),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["catalog", path] })

  const createMutation = useMutation({
    mutationFn: (input: { name: string; description?: string }) =>
      createCatalogItem(path, input),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      toast.success("Registro criado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, name, description }: { id: string; name: string; description?: string }) =>
      updateCatalogItem(path, id, { name, description }),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.success("Registro atualizado")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      setCatalogItemActive(path, id, active),
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  })

  function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    createMutation.mutate({
      name: String(form.get("name")),
      description: String(form.get("description")) || undefined,
    })
  }

  function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    const form = new FormData(event.currentTarget)
    updateMutation.mutate({
      id: editing.id,
      name: String(form.get("name")),
      description: String(form.get("description")) || undefined,
    })
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-semibold text-foreground">{title}</h1>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Buscar por nome"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-56"
          />
          {podeCriar && (
            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <Button>Novo</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Novo registro</DialogTitle>
                </DialogHeader>
                <form onSubmit={onCreate} className="flex flex-col gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="name">Nome</Label>
                    <Input id="name" name="name" required />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="description">Descricao</Label>
                    <Input id="description" name="description" />
                  </div>
                  <Button type="submit" disabled={createMutation.isPending}>
                    Criar
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (items ?? []).length === 0 ? (
        <p className="text-muted-foreground">Nenhum registro para este filtro</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Descricao</TableHead>
              <TableHead>Status</TableHead>
              {podeGerenciar && <TableHead className="w-40">Acoes</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(items ?? []).map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {item.description ?? ""}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{item.active ? "ativo" : "inativo"}</Badge>
                </TableCell>
                {podeGerenciar && (
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Switch
                        checked={item.active}
                        onCheckedChange={(checked) =>
                          activeMutation.mutate({ id: item.id, active: checked })
                        }
                      />
                      <Button variant="ghost" size="sm" onClick={() => setEditing(item)}>
                        Editar
                      </Button>
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={editing != null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar registro</DialogTitle>
          </DialogHeader>
          {editing && (
            <form onSubmit={onEdit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-name">Nome</Label>
                <Input id="edit-name" name="name" defaultValue={editing.name} required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="edit-description">Descricao</Label>
                <Input
                  id="edit-description"
                  name="description"
                  defaultValue={editing.description ?? ""}
                />
              </div>
              <Button type="submit" disabled={updateMutation.isPending}>
                Salvar
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
```

- [ ] **Step 2: Registrar as 4 rotas em `main.tsx`**

```tsx
import CatalogPage from "@/pages/cadastros/CatalogPage"

    { path: "/cadastros/marcas", element: <CatalogPage title="Marcas" path="marcas" /> },
    { path: "/cadastros/defeitos", element: <CatalogPage title="Defeitos" path="defeitos" /> },
    { path: "/cadastros/solucoes", element: <CatalogPage title="Solucoes" path="solucoes" /> },
    { path: "/cadastros/canais", element: <CatalogPage title="Canais de compra" path="canais" /> },
```

- [ ] **Step 3: Verificar e commitar**

`pnpm dev` com backend de pé: logar com usuário de tenant e exercitar marcas (criar, renomear, inativar, buscar). Em `frontend/`: `pnpm lint && pnpm build`.

```bash
git add frontend
git commit -m "Adiciona pagina generica de catalogo de cadastros"
```

---

### Task 14: Frontend — página de produtos

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md` (SKU em `font-mono`).

**Files:**
- Create: `frontend/src/pages/cadastros/ProdutosPage.tsx`
- Modify: `frontend/src/main.tsx` (substituir placeholder)

**Interfaces:**
- Consumes: `listProducts`/`createProduct`/`updateProduct`/`setProductActive`, `canCreateCadastros`/`canManageCadastros`, `Page<Product>` (Task 12).
- Produces: rota `/cadastros/produtos` funcional com busca, paginação (Anterior/Proxima + "X de Y"), dialog criar/editar (nome, SKU, segmento, descricao), switch ativo.

- [ ] **Step 1: Implementar `ProdutosPage.tsx`**

Mesma estrutura da CatalogPage com as diferenças: estado `page` (reset para 1 quando a busca muda); query `["produtos", search, page]` com `listProducts({search, page, perPage: 20})`; colunas Nome, SKU (`font-mono`), Segmento, Status, Acoes; forms com campos `name` (required), `sku` (required), `segment`, `description`; rodapé de paginação:

```tsx
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {data ? `${data.total} produto(s)` : ""}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </Button>
          <span>
            Pagina {page} de {data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={!data || page >= Math.ceil(data.total / data.per_page)}
            onClick={() => setPage((p) => p + 1)}
          >
            Proxima
          </Button>
        </div>
      </div>
```

Mutations chamam `createProduct({name, sku, segment: segment || null, description: description || null})` e `updateProduct(id, ...)`; toasts e invalidation da queryKey `["produtos"]` como nas demais páginas.

- [ ] **Step 2: Registrar rota e verificar**

Em `main.tsx`: `{ path: "/cadastros/produtos", element: <ProdutosPage /> }`.
`pnpm dev`: criar produto, buscar por SKU, paginar (criar 21+ se quiser ver a paginação real), editar, inativar. Em `frontend/`: `pnpm lint && pnpm build`.

```bash
git add frontend
git commit -m "Adiciona pagina de produtos com busca e paginacao"
```

---

### Task 15: Frontend — página de clientes com CEP autofill

Antes de escrever UI, invocar o skill `frontend-design` e seguir `docs/identidade-visual.md` (documento/telefone/CEP em `font-mono` na tabela).

**Files:**
- Create: `frontend/src/pages/cadastros/ClientesPage.tsx`
- Modify: `frontend/src/main.tsx` (substituir placeholder)

**Interfaces:**
- Consumes: `listCustomers`/`createCustomer`/`updateCustomer`/`setCustomerActive`/`lookupCep`, `formatDocument`/`formatPhone`/`formatCep`/`onlyDigits` (Task 12).
- Produces: rota `/cadastros/clientes` com busca (nome ou documento), paginação (mesmo padrão da Task 14), form completo com autofill de CEP.

- [ ] **Step 1: Implementar `ClientesPage.tsx`**

Mesma estrutura de página das Tasks 13-14 (busca + paginação + dialogs + switch). Especificidades:

- Colunas: Nome, Documento (`font-mono`, via `formatDocument`), Telefone (`font-mono`, `formatPhone`), Cidade/UF, Status, Acoes.
- Form (criar e editar compartilham o componente `ClienteForm`): campos name (required), document (required), phone, email, cep, street, number, complement, neighborhood, city, state. Enviar sempre os campos vazios como `null`.
- Autofill de CEP no `onBlur` do campo cep, quando tiver 8 dígitos:

```tsx
const [cepLoading, setCepLoading] = useState(false)

async function onCepBlur(event: FocusEvent<HTMLInputElement>) {
  const digits = onlyDigits(event.target.value)
  if (digits.length !== 8) return
  setCepLoading(true)
  try {
    const address = await lookupCep(digits)
    setForm((current) => ({
      ...current,
      cep: digits,
      street: address.street || current.street,
      neighborhood: address.neighborhood || current.neighborhood,
      city: address.city || current.city,
      state: address.state || current.state,
    }))
  } catch {
    toast.message("CEP nao localizado, preencha o endereco manualmente")
  } finally {
    setCepLoading(false)
  }
}
```

- O `ClienteForm` usa estado controlado (`useState` de um objeto `CustomerInput`) em vez de FormData, porque o autofill precisa escrever nos campos; inputs de documento/telefone/cep aplicam as máscaras de exibição no onChange (`formatDocument`/`formatPhone`/`formatCep`) e o submit envia `onlyDigits` desses campos.
- Erros da API (documento inválido 422, duplicado 409) aparecem como toast com a mensagem do backend.

- [ ] **Step 2: Registrar rota e verificar**

Em `main.tsx`: `{ path: "/cadastros/clientes", element: <ClientesPage /> }`.
`pnpm dev`: criar cliente com CPF válido (ex.: 529.982.247-25), testar CEP real com backend de pé, testar CPF inválido (toast 422) e duplicado (409). Em `frontend/`: `pnpm lint && pnpm build`.

```bash
git add frontend
git commit -m "Adiciona pagina de clientes com mascaras e autofill de CEP"
```

---

### Task 16: Verificação final integrada da Fase 1

**Files:**
- Modify: `README.md` (documentação: spec e plano da Fase 1 na seção Documentação)

**Interfaces:**
- Consumes: tudo anterior; ambiente dev (`dev.ps1`, containers, tenant `b2pro` existente do banco dev — pode estar com status suspensa de testes anteriores).

- [ ] **Step 1: Migrar e semear os tenants existentes do banco dev**

```bash
docker compose up -d db
cd backend
uv run python -m sac.infrastructure.migrate tenants
uv run python -m sac.infrastructure.seed_tenant b2pro
```

Esperado: migration 0002 aplicada em todos os schemas `t_*`; seeds do b2pro criados.

- [ ] **Step 2: Subir tudo e validar o fluxo manual**

`./dev.ps1` na raiz (ou containers + `pnpm dev`). Roteiro:

1. Login como super admin; se o tenant `b2pro` estiver suspenso (estado deixado por testes da Fase 0), reativar pelo painel da plataforma; conferir vínculo da usuária `ana` como admin.
2. Login como `ana` com slug `b2pro`: sidebar mostra o grupo Cadastros.
3. Marcas: KODI e STALEKS já presentes (seed); criar/renomear/inativar uma marca de teste.
4. Defeitos/Solucoes/Canais: valores default presentes; busca funciona.
5. Produtos: criar produto com SKU, buscar, paginar, inativar.
6. Clientes: criar com CPF válido e CEP real (autofill preenche endereço); CPF inválido -> toast de validação; documento duplicado -> toast 409.
7. Papéis: logar com um usuário visualizador (criar/vincular pelo painel se necessário) e confirmar leitura sem botões de ação.

- [ ] **Step 3: Verificações completas**

Backend (em `backend/`): `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest` — tudo verde.
Frontend (em `frontend/`): `pnpm lint && pnpm build` — tudo verde.

- [ ] **Step 4: Atualizar `README.md` e commit final**

Na seção Documentação do README, acrescentar:

```markdown
- `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-1-design.md` — design técnico da Fase 1 (cadastros).
- `docs/superpowers/plans/2026-07-28-fase-1-cadastros.md` — plano de implementação da Fase 1.
```

```bash
git add README.md
git commit -m "Atualiza README com documentacao da Fase 1"
```
