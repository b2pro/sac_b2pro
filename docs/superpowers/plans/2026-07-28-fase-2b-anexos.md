# Fase 2B (Anexos, previews e membros do tenant) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anexos de ticket no Wasabi S3 com upload direto por presigned URL e previews gerados por worker, mais a foto de catálogo do produto e o endpoint de membros do tenant (que destrava o seletor de supervisor).

**Architecture:** Um `StoragePort` único (dois clients boto3: interno para HEAD/download, público para assinar URLs que vão ao navegador) e uma fila `public.preview_jobs` servem os dois casos de uso; `ticket_attachments` é tabela própria no schema do tenant, e a foto do produto grava `photo_key`/`photo_preview_key` na própria linha. O worker é um processo separado (`python -m sac.worker`) que consome a fila com `FOR UPDATE SKIP LOCKED`.

**Tech Stack:** o existente (FastAPI, SQLAlchemy 2 async, Alembic, pytest; React + TanStack Query + shadcn/ui). Novas dependências de backend: `boto3` e `Pillow`. Novo serviço de dev: MinIO (compatível com S3) no docker-compose.

**Spec:** `docs/superpowers/specs/2026-07-28-sac-b2pro-fase-2b-anexos-design.md`.

## Global Constraints

- PROIBIDO usar emojis em código, comentários, commits, UI, documentação e mensagens.
- Clean Architecture: `domain` e `application` são Python puro (sem FastAPI/SQLAlchemy/Pydantic/boto3); `infrastructure` implementa os ports.
- TDD no backend: teste antes da implementação em toda tarefa de backend.
- SEM CI. Antes de CADA commit rodar localmente e exigir sucesso:
  - Backend (em `backend/`): `uv run ruff format .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
  - Frontend (em `frontend/`): `pnpm lint` e `pnpm build`.
- Testes de integração exigem Postgres E MinIO de pé (`docker compose up -d db minio minio-init` na raiz).
- Toda tarefa de frontend (Tasks 11-14) DEVE invocar o skill `frontend-design` antes de escrever UI e seguir `docs/identidade-visual.md` (dado técnico em `font-mono`; Paprika só na ação primária; lucide `strokeWidth={1.5}`, 16px em tabelas / 20px em botões; empty states de texto direto; zero sombra decorativa).
- Commits em português, imperativo, sem prefixo convencional, corpo terminando com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tipos aceitos: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`, `video/mp4`, `video/quicktime`, `video/webm`. Limite de **52428800 bytes (50 MB)** por arquivo e **10 anexos por ticket**.
- **Vídeo nunca é processado no servidor**: sem ffmpeg, sem transcodificação. A thumb do vídeo vem do navegador; se não vier, o anexo fica `sem_preview`.
- **A assinatura do presigned cobre o header `Host`**: nunca reescrever o host de uma URL já assinada. URLs para o navegador são geradas pelo client público; HEAD/download/upload do servidor usam o client interno.
- Soft delete de anexo NUNCA apaga o objeto do bucket.
- Chaves de objeto são sempre geradas no servidor; o nome do arquivo enviado pelo client nunca compõe a chave (só a extensão derivada do mime).

## Mapa de arquivos novos/modificados

```
backend/src/sac/
  domain/
    attachments.py            # AttachmentKind/Status, PreviewStatus, entidades, kind_for,
                              # validate_size, build_object_key, preview_keys_for, next_backoff
    errors.py                 # +StorageUnavailableError
  application/
    ports_attachments.py      # StoragePort, ObjectHead, AttachmentRepository,
                              # PreviewJobRepository, ProductPhotoRepository, TenantMemberDirectory
    use_cases/
      attachments.py          # RequestUpload, ConfirmUpload, ListAttachments,
                              # GetAttachmentUrl, DeleteAttachment, ExpirePending
      product_photo.py        # RequestProductPhotoUpload, ConfirmProductPhoto, DeleteProductPhoto
      members.py              # ListTenantMembers
      previews.py             # ProcessNextPreviewJob (usado pelo worker)
  infrastructure/
    models.py                 # +PreviewJobModel (public)
    models_tenant.py          # +TicketAttachmentModel; ProductModel += photo_preview_key
    storage.py                # S3Storage (boto3, dois clients) + build_storage
    repositories_attachments.py  # SqlAttachmentRepository, SqlPreviewJobRepository,
                                 # SqlProductPhotoRepository, SqlTenantMemberDirectory
    images.py                 # generate_previews(data: bytes) -> tuple[bytes, bytes] (Pillow)
    settings.py               # +variaveis de S3 e limites
    worker.py                 # loop do worker (python -m sac.worker)
  interface/
    errors.py                 # STATUS_BY_CODE += storage_indisponivel: 503
    schemas.py                # +schemas de anexo, foto e membro
    deps.py                   # +get_storage, get_attachment_repos, get_member_directory
    routers/
      tickets.py              # +rotas de anexos
      cadastros_products.py   # +rotas de foto
      members.py              # GET /api/membros
    app.py                    # include_router(members)
backend/migrations/public/versions/0002_preview_jobs.py
backend/migrations/tenant/versions/0004_anexos.py
backend/tests/unit/domain/test_attachments.py
backend/tests/unit/fakes_attachments.py
backend/tests/unit/application/test_attachments_use_cases.py
backend/tests/unit/application/test_previews_use_case.py
backend/tests/integration/conftest.py       # +fixtures de MinIO (bucket descartavel)
backend/tests/integration/test_storage.py
backend/tests/integration/test_attachments_api.py
backend/tests/integration/test_worker.py
backend/tests/integration/test_members_api.py
docker-compose.yml, dev.ps1, backend/pyproject.toml, README.md
frontend/src/
  lib/media.ts                # compressImage, captureVideoThumb, kindOf
  lib/attachments.ts          # client da API + PUT com progresso (XMLHttpRequest)
  lib/members.ts              # listMembers
  components/tickets/AttachmentsCard.tsx
  components/tickets/AttachmentsCard.upload.ts  # fila de upload (estado por arquivo)
  pages/tickets/TicketDetailPage.tsx            # troca o placeholder pelo card real
  pages/tickets/TicketCreatePage.tsx            # seletor de supervisor
  components/tickets/ActionPanel.tsx            # seletor de supervisor no dialog de editar
  pages/cadastros/ProdutosPage.tsx              # upload da foto + thumb na tabela
  e2e/05-anexos.spec.ts
```

---

### Task 1: Domínio de anexos

**Files:**
- Create: `backend/src/sac/domain/attachments.py`
- Modify: `backend/src/sac/domain/errors.py`
- Modify: `backend/src/sac/interface/errors.py`
- Test: `backend/tests/unit/domain/test_attachments.py`

**Interfaces:**
- Consumes: `DomainError`, `ValidationError` (`domain/errors.py`).
- Produces: `AttachmentKind` (StrEnum: `imagem`, `pdf`, `video`), `AttachmentStatus` (StrEnum: `pendente`, `disponivel`, `expirado`), `PreviewStatus` (StrEnum: `sem_preview`, `pendente`, `pronto`, `falhou`), `PreviewJobStatus` (StrEnum: `pendente`, `processando`, `pronto`, `falhou`), `ALLOWED_CONTENT_TYPES: dict[str, tuple[AttachmentKind, str]]` (mime -> (kind, extensão)), `MAX_ATTACHMENT_BYTES = 52_428_800`, `MAX_ATTACHMENTS_PER_TICKET = 10`, `MAX_PREVIEW_ATTEMPTS = 5`, `kind_for(content_type: str) -> AttachmentKind`, `extension_for(content_type: str) -> str`, `validate_size(size_bytes: int) -> None`, `build_object_key(tenant_slug: str, ticket_id: UUID, content_type: str, uid: UUID) -> str`, `build_product_photo_key(tenant_slug: str, product_id: UUID, content_type: str, uid: UUID) -> str`, `preview_keys_for(object_key: str) -> tuple[str, str]` (thumb, médio), `next_backoff(attempts: int) -> timedelta`, dataclasses `TicketAttachment` e `PreviewJob`, `StorageUnavailableError` (code `storage_indisponivel`, HTTP 503).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/unit/domain/test_attachments.py`:

```python
from datetime import timedelta
from uuid import UUID

import pytest

from sac.domain.attachments import (
    ALLOWED_CONTENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_TICKET,
    MAX_PREVIEW_ATTEMPTS,
    AttachmentKind,
    build_object_key,
    build_product_photo_key,
    extension_for,
    kind_for,
    next_backoff,
    preview_keys_for,
    validate_size,
)
from sac.domain.errors import ValidationError

TICKET = UUID("11111111-1111-1111-1111-111111111111")
UID = UUID("22222222-2222-2222-2222-222222222222")


def test_tipos_aceitos_e_seus_kinds() -> None:
    assert kind_for("image/jpeg") is AttachmentKind.IMAGEM
    assert kind_for("image/png") is AttachmentKind.IMAGEM
    assert kind_for("image/webp") is AttachmentKind.IMAGEM
    assert kind_for("application/pdf") is AttachmentKind.PDF
    assert kind_for("video/mp4") is AttachmentKind.VIDEO
    assert kind_for("video/quicktime") is AttachmentKind.VIDEO
    assert kind_for("video/webm") is AttachmentKind.VIDEO
    assert len(ALLOWED_CONTENT_TYPES) == 7


def test_tipo_recusado() -> None:
    for mime in ("image/gif", "application/zip", "text/html", ""):
        with pytest.raises(ValidationError) as exc:
            kind_for(mime)
        assert exc.value.details == {"field": "content_type"}


def test_extensao_vem_do_mime() -> None:
    assert extension_for("image/jpeg") == "jpg"
    assert extension_for("image/png") == "png"
    assert extension_for("image/webp") == "webp"
    assert extension_for("application/pdf") == "pdf"
    assert extension_for("video/mp4") == "mp4"
    assert extension_for("video/quicktime") == "mov"
    assert extension_for("video/webm") == "webm"


def test_limite_de_tamanho() -> None:
    assert MAX_ATTACHMENT_BYTES == 52_428_800
    assert MAX_ATTACHMENTS_PER_TICKET == 10
    validate_size(1)
    validate_size(MAX_ATTACHMENT_BYTES)
    for invalido in (0, -1, MAX_ATTACHMENT_BYTES + 1):
        with pytest.raises(ValidationError) as exc:
            validate_size(invalido)
        assert exc.value.details == {"field": "size_bytes"}


def test_chave_gerada_no_servidor_ignora_o_nome_do_arquivo() -> None:
    chave = build_object_key("acme", TICKET, "image/jpeg", UID)
    assert chave == f"acme/{TICKET}/{UID}.jpg"
    foto = build_product_photo_key("acme", UID, "image/png", TICKET)
    assert foto == f"acme/catalogo/produtos/{UID}/{TICKET}.png"


def test_chaves_de_preview_derivam_do_original() -> None:
    thumb, medio = preview_keys_for(f"acme/{TICKET}/{UID}.jpg")
    assert thumb == f"acme/{TICKET}/previews/{UID}.webp"
    assert medio == f"acme/{TICKET}/previews/{UID}_medium.webp"


def test_backoff_exponencial_limitado() -> None:
    assert MAX_PREVIEW_ATTEMPTS == 5
    assert next_backoff(1) == timedelta(minutes=1)
    assert next_backoff(2) == timedelta(minutes=2)
    assert next_backoff(3) == timedelta(minutes=4)
    assert next_backoff(4) == timedelta(minutes=8)
    assert next_backoff(5) == timedelta(minutes=16)
    assert next_backoff(9) == timedelta(minutes=16)
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `backend/`): `uv run pytest tests/unit/domain/test_attachments.py -v`
Esperado: FAIL (ImportError: `sac.domain.attachments` não existe).

- [ ] **Step 3: Implementar o domínio**

Em `backend/src/sac/domain/errors.py`, ao final:

```python
class StorageUnavailableError(DomainError):
    code = "storage_indisponivel"
```

Em `backend/src/sac/interface/errors.py`, acrescentar em `STATUS_BY_CODE`:

```python
    "storage_indisponivel": 503,
```

Criar `backend/src/sac/domain/attachments.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sac.domain.errors import ValidationError


class AttachmentKind(StrEnum):
    IMAGEM = "imagem"
    PDF = "pdf"
    VIDEO = "video"


class AttachmentStatus(StrEnum):
    PENDENTE = "pendente"
    DISPONIVEL = "disponivel"
    EXPIRADO = "expirado"


class PreviewStatus(StrEnum):
    SEM_PREVIEW = "sem_preview"
    PENDENTE = "pendente"
    PRONTO = "pronto"
    FALHOU = "falhou"


class PreviewJobStatus(StrEnum):
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    PRONTO = "pronto"
    FALHOU = "falhou"


ALLOWED_CONTENT_TYPES: dict[str, tuple[AttachmentKind, str]] = {
    "image/jpeg": (AttachmentKind.IMAGEM, "jpg"),
    "image/png": (AttachmentKind.IMAGEM, "png"),
    "image/webp": (AttachmentKind.IMAGEM, "webp"),
    "application/pdf": (AttachmentKind.PDF, "pdf"),
    "video/mp4": (AttachmentKind.VIDEO, "mp4"),
    "video/quicktime": (AttachmentKind.VIDEO, "mov"),
    "video/webm": (AttachmentKind.VIDEO, "webm"),
}

MAX_ATTACHMENT_BYTES = 52_428_800
MAX_ATTACHMENTS_PER_TICKET = 10
MAX_PREVIEW_ATTEMPTS = 5
_BACKOFF_MINUTES = (1, 2, 4, 8, 16)


def _entry(content_type: str) -> tuple[AttachmentKind, str]:
    entry = ALLOWED_CONTENT_TYPES.get(content_type.strip().lower())
    if entry is None:
        raise ValidationError(
            "tipo de arquivo nao aceito", details={"field": "content_type"}
        )
    return entry


def kind_for(content_type: str) -> AttachmentKind:
    return _entry(content_type)[0]


def extension_for(content_type: str) -> str:
    return _entry(content_type)[1]


def validate_size(size_bytes: int) -> None:
    if size_bytes < 1 or size_bytes > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            "tamanho de arquivo invalido", details={"field": "size_bytes"}
        )


def build_object_key(
    tenant_slug: str, ticket_id: UUID, content_type: str, uid: UUID
) -> str:
    return f"{tenant_slug}/{ticket_id}/{uid}.{extension_for(content_type)}"


def build_product_photo_key(
    tenant_slug: str, product_id: UUID, content_type: str, uid: UUID
) -> str:
    return (
        f"{tenant_slug}/catalogo/produtos/{product_id}/{uid}."
        f"{extension_for(content_type)}"
    )


def preview_keys_for(object_key: str) -> tuple[str, str]:
    prefixo, _, arquivo = object_key.rpartition("/")
    nome = arquivo.rpartition(".")[0]
    return f"{prefixo}/previews/{nome}.webp", f"{prefixo}/previews/{nome}_medium.webp"


def next_backoff(attempts: int) -> timedelta:
    indice = min(max(attempts, 1), len(_BACKOFF_MINUTES)) - 1
    return timedelta(minutes=_BACKOFF_MINUTES[indice])


@dataclass
class TicketAttachment:
    id: UUID
    ticket_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    object_key: str
    kind: AttachmentKind
    status: AttachmentStatus
    preview_status: PreviewStatus
    author_user_id: UUID
    preview_key: str | None = None
    preview_medium_key: str | None = None
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    deleted_at: datetime | None = None


@dataclass
class PreviewJob:
    id: UUID
    tenant_slug: str
    object_key: str
    kind: AttachmentKind
    status: PreviewJobStatus
    attempts: int
    next_attempt_at: datetime
    attachment_id: UUID | None = None
    product_id: UUID | None = None
    last_error: str | None = None
```

Nota: `build_product_photo_key` recebe o `uid` no lugar do quarto argumento do teste (`TICKET`) apenas porque o teste reaproveita os UUIDs disponíveis — a assinatura é `(tenant_slug, product_id, content_type, uid)`.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/domain/test_attachments.py -v`
Esperado: PASS (7 testes).

- [ ] **Step 5: Verificações completas e commit**

Rodar as verificações do backend (Global Constraints) e:

```bash
git add backend/src/sac/domain/attachments.py backend/src/sac/domain/errors.py backend/src/sac/interface/errors.py backend/tests/unit/domain/test_attachments.py
git commit -m "Adiciona dominio de anexos com tipos, limites e chaves de objeto"
```

---

### Task 2: MinIO no compose, settings de S3 e gateway de storage

**Files:**
- Modify: `docker-compose.yml`
- Modify: `dev.ps1`
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/sac/infrastructure/settings.py`
- Create: `backend/src/sac/application/ports_attachments.py` (só `ObjectHead` e `StoragePort` nesta task)
- Create: `backend/src/sac/infrastructure/storage.py`
- Modify: `backend/tests/integration/conftest.py`
- Test: `backend/tests/integration/test_storage.py`

**Interfaces:**
- Consumes: `Settings` (`infrastructure/settings.py`), `StorageUnavailableError` (Task 1).
- Produces:
  - `ObjectHead(content_type: str, size_bytes: int)` (frozen dataclass) e `StoragePort` (Protocol) com `presigned_put(key: str, content_type: str, max_bytes: int, ttl_seconds: int) -> str`, `presigned_get(key: str, ttl_seconds: int) -> str`, `head(key: str) -> ObjectHead | None`, `put_bytes(key: str, data: bytes, content_type: str) -> None`, `get_bytes(key: str) -> bytes`.
  - `S3Storage(internal_client, public_client, bucket)` implementando o port, e `build_storage(settings: Settings) -> S3Storage`.
  - Settings novos: `s3_endpoint_url: str = "http://localhost:9000"`, `s3_public_endpoint_url: str = ""` (vazio = usa o interno), `s3_region: str = "us-east-1"`, `s3_bucket: str = "sac-dev"`, `s3_access_key: str = "sacminio"`, `s3_secret_key: str = "sacminio123"`, `presigned_ttl_seconds: int = 300`, `pending_expiration_minutes: int = 30`, `attachment_max_bytes: int = 52_428_800`, `attachment_max_per_ticket: int = 10`.
  - Fixtures de integração `storage` (S3Storage apontando para um bucket descartável por sessão) e `storage_settings`.

- [ ] **Step 1: Acrescentar MinIO ao compose**

Em `docker-compose.yml`, antes de `volumes:`, acrescentar os dois serviços e o volume:

```yaml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: sacminio
      MINIO_ROOT_PASSWORD: sacminio123
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 3s
      timeout: 3s
      retries: 20

  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 sacminio sacminio123 &&
      mc mb --ignore-existing local/sac-dev &&
      mc anonymous set none local/sac-dev
      "
```

E no bloco `volumes:` ao final do arquivo, acrescentar `miniodata:`.

No serviço `backend`, acrescentar ao `environment`:

```yaml
      SAC_S3_ENDPOINT_URL: http://minio:9000
      SAC_S3_PUBLIC_ENDPOINT_URL: http://localhost:9000
      SAC_S3_BUCKET: sac-dev
      SAC_S3_ACCESS_KEY: sacminio
      SAC_S3_SECRET_KEY: sacminio123
```

E `depends_on` do backend passa a incluir `minio` (condition `service_healthy`).

Em `dev.ps1`, trocar a linha `docker compose up -d --build db backend` por:

```powershell
docker compose up -d --build db minio minio-init backend worker
```

(o serviço `worker` é criado na Task 8; se ele ainda não existir no arquivo quando esta task rodar, deixe `worker` fora e acrescente na Task 8.)

- [ ] **Step 2: Dependências**

Em `backend/pyproject.toml`, acrescentar em `dependencies`:

```toml
    "boto3>=1.34",
    "pillow>=10.3",
```

Rodar: `cd backend && uv sync`

- [ ] **Step 3: Escrever o teste que falha**

`backend/tests/integration/test_storage.py`:

```python
import httpx
import pytest

from sac.domain.errors import StorageUnavailableError
from sac.infrastructure.storage import S3Storage


async def test_presigned_put_e_head(storage: S3Storage) -> None:
    chave = "acme/teste/arquivo.png"
    url = storage.presigned_put(chave, "image/png", max_bytes=1_000_000, ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.put(url, content=b"conteudo-fake", headers={"Content-Type": "image/png"})
    assert res.status_code == 200

    head = storage.head(chave)
    assert head is not None
    assert head.content_type == "image/png"
    assert head.size_bytes == len(b"conteudo-fake")


async def test_head_de_objeto_inexistente_e_none(storage: S3Storage) -> None:
    assert storage.head("acme/teste/nao-existe.png") is None


async def test_put_com_content_type_diferente_do_assinado_e_recusado(
    storage: S3Storage,
) -> None:
    chave = "acme/teste/mismatch.png"
    url = storage.presigned_put(chave, "image/png", max_bytes=1_000_000, ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.put(url, content=b"x", headers={"Content-Type": "application/pdf"})
    assert res.status_code >= 400
    assert storage.head(chave) is None


async def test_put_bytes_get_bytes_e_presigned_get(storage: S3Storage) -> None:
    chave = "acme/teste/servidor.webp"
    storage.put_bytes(chave, b"bytes-do-servidor", "image/webp")
    assert storage.get_bytes(chave) == b"bytes-do-servidor"

    url = storage.presigned_get(chave, ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
    assert res.status_code == 200
    assert res.content == b"bytes-do-servidor"


def test_url_publica_usa_o_endpoint_publico(storage_public: S3Storage) -> None:
    url = storage_public.presigned_get("acme/teste/qualquer.png", ttl_seconds=60)
    assert url.startswith("http://127.0.0.1:9000/")


def test_storage_fora_do_ar_vira_erro_de_dominio() -> None:
    quebrado = S3Storage.from_values(
        endpoint_url="http://localhost:9",
        public_endpoint_url="http://localhost:9",
        region="us-east-1",
        bucket="inexistente",
        access_key="x",
        secret_key="y",
    )
    with pytest.raises(StorageUnavailableError):
        quebrado.head("qualquer/chave.png")
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_storage.py -v`
Esperado: FAIL (módulo `sac.infrastructure.storage` não existe).

- [ ] **Step 5: Implementar settings, port e gateway**

Em `backend/src/sac/infrastructure/settings.py`, acrescentar à classe `Settings`:

```python
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "sac-dev"
    s3_access_key: str = "sacminio"
    s3_secret_key: str = "sacminio123"
    presigned_ttl_seconds: int = 300
    pending_expiration_minutes: int = 30
    attachment_max_bytes: int = 52_428_800
    attachment_max_per_ticket: int = 10
```

Criar `backend/src/sac/application/ports_attachments.py`:

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectHead:
    content_type: str
    size_bytes: int


class StoragePort(Protocol):
    def presigned_put(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> str: ...
    def presigned_get(self, key: str, ttl_seconds: int) -> str: ...
    def head(self, key: str) -> ObjectHead | None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
```

Criar `backend/src/sac/infrastructure/storage.py`:

```python
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from sac.application.ports_attachments import ObjectHead
from sac.domain.errors import StorageUnavailableError
from sac.infrastructure.settings import Settings

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def _client(endpoint_url: str, region: str, access_key: str, secret_key: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class S3Storage:
    """Gateway S3. Mantem dois clients: o interno faz HEAD/download/upload do
    servidor; o publico assina as URLs entregues ao navegador. A assinatura cobre
    o header Host, por isso trocar o endpoint depois de assinar invalidaria a URL.
    """

    def __init__(self, internal: Any, public: Any, bucket: str) -> None:
        self._internal = internal
        self._public = public
        self._bucket = bucket

    @classmethod
    def from_values(
        cls,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3Storage":
        internal = _client(endpoint_url, region, access_key, secret_key)
        public = (
            internal
            if not public_endpoint_url or public_endpoint_url == endpoint_url
            else _client(public_endpoint_url, region, access_key, secret_key)
        )
        return cls(internal, public, bucket)

    def presigned_put(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> str:
        try:
            return str(
                self._public.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket,
                        "Key": key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=ttl_seconds,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        try:
            return str(
                self._public.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=ttl_seconds,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def head(self, key: str) -> ObjectHead | None:
        try:
            res = self._internal.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND_CODES:
                return None
            raise StorageUnavailableError("storage indisponivel") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError("storage indisponivel") from exc
        return ObjectHead(
            content_type=str(res.get("ContentType", "")),
            size_bytes=int(res.get("ContentLength", 0)),
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._internal.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            res = self._internal.get_object(Bucket=self._bucket, Key=key)
            return bytes(res["Body"].read())
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc


def build_storage(settings: Settings) -> S3Storage:
    return S3Storage.from_values(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
```

Nota sobre o `max_bytes`: `generate_presigned_url` de `put_object` não suporta `content-length-range` (isso é POST policy). O limite de tamanho é garantido em duas camadas: validação do `size_bytes` declarado na intenção e o HEAD na confirmação, que rejeita se o objeto real passar do limite. O parâmetro fica na assinatura do port para o dia em que trocarmos por POST policy — documente isso num comentário de uma linha no método.

- [ ] **Step 6: Fixtures de MinIO**

Em `backend/tests/integration/conftest.py`, acrescentar ao final:

```python
@pytest.fixture(scope="session")
def storage_settings() -> Settings:
    return Settings(
        s3_endpoint_url="http://localhost:9000",
        s3_public_endpoint_url="http://127.0.0.1:9000",
        s3_bucket=f"sac-test-{uuid4().hex[:8]}",
        s3_access_key="sacminio",
        s3_secret_key="sacminio123",
    )


@pytest.fixture(scope="session")
def storage(storage_settings: Settings) -> Iterator[S3Storage]:
    from sac.infrastructure.storage import build_storage

    gateway = build_storage(storage_settings)
    gateway._internal.create_bucket(Bucket=storage_settings.s3_bucket)  # noqa: SLF001
    yield gateway
    # bucket descartavel: limpa objetos e remove
    paginator = gateway._internal.get_paginator("list_objects_v2")  # noqa: SLF001
    for page in paginator.paginate(Bucket=storage_settings.s3_bucket):
        for obj in page.get("Contents", []):
            gateway._internal.delete_object(  # noqa: SLF001
                Bucket=storage_settings.s3_bucket, Key=obj["Key"]
            )
    gateway._internal.delete_bucket(Bucket=storage_settings.s3_bucket)  # noqa: SLF001


@pytest.fixture(scope="session")
def storage_public(storage: S3Storage) -> S3Storage:
    return storage
```

Imports novos no topo do conftest: `from collections.abc import Iterator`, `from uuid import uuid4`, `from sac.infrastructure.storage import S3Storage`. Se o ruff reclamar do acesso a `_internal` nas fixtures, mantenha os `noqa` como acima.

- [ ] **Step 7: Rodar e ver passar**

Run: `docker compose up -d db minio minio-init` (na raiz) e depois, em `backend/`: `uv run pytest tests/integration/test_storage.py -v`
Esperado: PASS (6 testes).

- [ ] **Step 8: Verificações completas e commit**

```bash
git add docker-compose.yml dev.ps1 backend/pyproject.toml backend/uv.lock backend/src/sac/infrastructure/settings.py backend/src/sac/application/ports_attachments.py backend/src/sac/infrastructure/storage.py backend/tests/integration/conftest.py backend/tests/integration/test_storage.py
git commit -m "Adiciona MinIO no compose e gateway de storage S3 com dois clients"
```

---

### Task 3: Models e migrations (anexos, preview_jobs, foto do produto)

**Files:**
- Modify: `backend/src/sac/infrastructure/models_tenant.py`
- Modify: `backend/src/sac/infrastructure/models.py`
- Create: `backend/migrations/tenant/versions/0004_anexos.py`
- Create: `backend/migrations/public/versions/0002_preview_jobs.py`
- Test: `backend/tests/integration/test_attachments_schema.py`

**Interfaces:**
- Consumes: `TenantBase`/`TenantTableMixin` (`models_tenant.py`), `Base` (`models.py`), enums da Task 1, fixtures `session`/`engine` e `seed_provisioned_tenant` (`tests/integration/helpers.py`).
- Produces:
  - `TicketAttachmentModel` (tabela `ticket_attachments` no schema `tenant`) com constraints NOMEADAS: `fk_ticket_attachments_ticket_id`, `ck_ticket_attachments_size`, e índices `ix_ticket_attachments_ticket_id`, `ix_ticket_attachments_status`.
  - `ProductModel.photo_preview_key` (String(255), nullable).
  - `PreviewJobModel` (tabela `preview_jobs` no schema público) com `ck_preview_jobs_owner` (exatamente um de `attachment_id`/`product_id`) e índice `ix_preview_jobs_pendentes` em `(status, next_attempt_at)`.
  - Migrations: tenant `0004_anexos` (down_revision `0003_tickets`), public `0002_preview_jobs` (down_revision `677496d18d74`).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_attachments_schema.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.infrastructure.models import PreviewJobModel
from sac.infrastructure.models_tenant import BrandModel, ProductModel, TicketAttachmentModel, TicketModel
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket(ts: AsyncSession, attendant: UUID) -> TicketModel:
    brand_id = (await ts.scalars(select(BrandModel.id))).first()
    assert brand_id is not None
    ticket = TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=attendant,
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    ts.add(ticket)
    await ts.flush()
    return ticket


async def test_anexo_persiste_com_defaults(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexschema")
    user = await seed_user(session, email="anex@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket = await _ticket(ts, user.id)
        anexo = TicketAttachmentModel(
            id=uuid4(),
            ticket_id=ticket.id,
            filename="foto.jpg",
            content_type="image/jpeg",
            size_bytes=1234,
            object_key=f"{tenant.slug}/{ticket.id}/{uuid4()}.jpg",
            kind="imagem",
            status="pendente",
            preview_status="pendente",
            author_user_id=user.id,
        )
        ts.add(anexo)
        await ts.flush()
        assert anexo.created_at is not None
        assert anexo.deleted_at is None
        await ts.commit()


async def test_tamanho_zero_e_recusado_pelo_check(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexcheck")
    user = await seed_user(session, email="anexcheck@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket = await _ticket(ts, user.id)
        ts.add(
            TicketAttachmentModel(
                id=uuid4(),
                ticket_id=ticket.id,
                filename="vazio.pdf",
                content_type="application/pdf",
                size_bytes=0,
                object_key="x/y/z.pdf",
                kind="pdf",
                status="pendente",
                preview_status="sem_preview",
                author_user_id=user.id,
            )
        )
        with pytest.raises(IntegrityError):
            await ts.flush()


async def test_produto_tem_coluna_de_preview(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="anexfoto")
    async with _factory(engine, tenant.schema_name)() as ts:
        produto = ProductModel(
            id=uuid4(),
            name="Produto com foto",
            sku="FOTO-1",
            photo_key="acme/catalogo/produtos/x/y.png",
            photo_preview_key="acme/catalogo/produtos/x/previews/y.webp",
        )
        ts.add(produto)
        await ts.flush()
        assert produto.photo_preview_key is not None
        await ts.commit()


async def test_preview_job_global_exige_exatamente_um_dono(session: AsyncSession) -> None:
    job = PreviewJobModel(
        id=uuid4(),
        tenant_slug="acme",
        attachment_id=uuid4(),
        object_key="acme/t/x.jpg",
        kind="imagem",
        status="pendente",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    session.add(
        PreviewJobModel(
            id=uuid4(),
            tenant_slug="acme",
            attachment_id=uuid4(),
            product_id=uuid4(),
            object_key="acme/t/y.jpg",
            kind="imagem",
            status="pendente",
            attempts=0,
            next_attempt_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_indice_da_fila_existe(session: AsyncSession) -> None:
    nomes = (
        await session.scalars(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'preview_jobs'")
        )
    ).all()
    assert "ix_preview_jobs_pendentes" in nomes
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_attachments_schema.py -v`
Esperado: FAIL (models não existem).

- [ ] **Step 3: Implementar os models**

Em `backend/src/sac/infrastructure/models_tenant.py`, acrescentar à `ProductModel` (junto de `photo_key`):

```python
    photo_preview_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

E ao final do arquivo:

```python
class TicketAttachmentModel(TenantBase):
    __tablename__ = "ticket_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_ticket_attachments_size"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_attachments_ticket_id"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(400), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    preview_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    preview_medium_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    preview_status: Mapped[str] = mapped_column(String(12), nullable=False)
    author_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Em `backend/src/sac/infrastructure/models.py`, ao final (imports novos: `BigInteger`, `CheckConstraint`, `DateTime`, `Integer`, `String`, `Text`, `func` conforme já existirem):

```python
class PreviewJobModel(Base):
    __tablename__ = "preview_jobs"
    __table_args__ = (
        CheckConstraint(
            "(attachment_id IS NOT NULL)::int + (product_id IS NOT NULL)::int = 1",
            name="ck_preview_jobs_owner",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_slug: Mapped[str] = mapped_column(String(63), nullable=False)
    attachment_id: Mapped[UUID | None] = mapped_column(nullable=True)
    product_id: Mapped[UUID | None] = mapped_column(nullable=True)
    object_key: Mapped[str] = mapped_column(String(400), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 4: Migration do tenant**

`backend/migrations/tenant/versions/0004_anexos.py`:

```python
"""anexos de ticket e preview da foto do produto

Revision ID: 0004_anexos
Revises: 0003_tickets
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0004_anexos"
down_revision = "0003_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("preview_key", sa.String(400), nullable=True),
        sa.Column("preview_medium_key", sa.String(400), nullable=True),
        sa.Column("preview_status", sa.String(12), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes > 0", name="ck_ticket_attachments_size"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_attachments_ticket_id"
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_ticket_attachments_ticket_id", "ticket_attachments", ["ticket_id"], schema="tenant"
    )
    op.create_index(
        "ix_ticket_attachments_status", "ticket_attachments", ["status"], schema="tenant"
    )
    op.add_column(
        "products",
        sa.Column("photo_preview_key", sa.String(255), nullable=True),
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_column("products", "photo_preview_key", schema="tenant")
    op.drop_table("ticket_attachments", schema="tenant")
```

- [ ] **Step 5: Migration do schema público**

`backend/migrations/public/versions/0002_preview_jobs.py`:

```python
"""fila global de previews

Revision ID: 0002_preview_jobs
Revises: 677496d18d74
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_preview_jobs"
down_revision = "677496d18d74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preview_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_slug", sa.String(63), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(attachment_id IS NOT NULL)::int + (product_id IS NOT NULL)::int = 1",
            name="ck_preview_jobs_owner",
        ),
    )
    op.create_index(
        "ix_preview_jobs_pendentes", "preview_jobs", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("preview_jobs")
```

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_attachments_schema.py tests/integration/test_migrations.py tests/integration/test_provisioning.py -v`
Esperado: PASS. A fixture `database` do conftest roda `upgrade_public`, então a migration pública nova é aplicada automaticamente no banco de teste.

- [ ] **Step 7: Verificações completas e commit**

```bash
git add backend/src/sac/infrastructure/models_tenant.py backend/src/sac/infrastructure/models.py backend/migrations/tenant/versions/0004_anexos.py backend/migrations/public/versions/0002_preview_jobs.py backend/tests/integration/test_attachments_schema.py
git commit -m "Adiciona tabelas de anexos, fila de previews e coluna de preview do produto"
```

---

### Task 4: Ports e repositórios SQL de anexos, fila, foto e membros

**Files:**
- Modify: `backend/src/sac/application/ports_attachments.py`
- Create: `backend/src/sac/infrastructure/repositories_attachments.py`
- Test: `backend/tests/integration/test_repositories_attachments.py`

**Interfaces:**
- Consumes: models da Task 3, entidades e enums da Task 1, `flush_tickets` (`infrastructure/repositories_tickets.py`), `UserModel`/`UserTenantModel`/`TenantModel` (`infrastructure/models.py`), `Role` (`domain/permissions.py`).
- Produces (ports):
  - `AttachmentRepository`: `add(a: TicketAttachment) -> None`, `get(attachment_id: UUID) -> TicketAttachment | None`, `list_by_ticket(ticket_id: UUID) -> list[TicketAttachment]` (só `disponivel` e não deletados, ordem `created_at`), `count_active(ticket_id: UUID) -> int` (pendentes + disponíveis não deletados), `update(a: TicketAttachment) -> None`, `list_pending_before(moment: datetime) -> list[TicketAttachment]`.
  - `PreviewJobRepository`: `add(job: PreviewJob) -> None`, `claim_next(now: datetime) -> PreviewJob | None` (usa `FOR UPDATE SKIP LOCKED` e marca `processando`), `mark_done(job_id: UUID) -> None`, `mark_failed(job_id: UUID, error: str, next_attempt_at: datetime, exhausted: bool) -> None`, `get(job_id: UUID) -> PreviewJob | None`.
  - `ProductPhotoRepository`: `set_photo(product_id: UUID, photo_key: str | None, preview_key: str | None) -> None`, `get_photo(product_id: UUID) -> tuple[str | None, str | None] | None`.
  - `TenantMemberDirectory`: `list_members(tenant_slug: str) -> list[TenantMember]`, com `TenantMember(id: UUID, name: str, role: Role, active: bool)` (frozen dataclass).
- Produces (infra): `SqlAttachmentRepository(session)`, `SqlPreviewJobRepository(session)`, `SqlProductPhotoRepository(session)`, `SqlTenantMemberDirectory(session)`, `AttachmentRepos` (dataclass com `attachments`, `jobs`, `photos`) e `build_attachment_repos(session) -> AttachmentRepos`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_repositories_attachments.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
)
from sac.domain.permissions import Role
from sac.infrastructure.models_tenant import BrandModel, ProductModel, TicketModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    SqlTenantMemberDirectory,
    build_attachment_repos,
)
from tests.integration.helpers import seed_link, seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket_id(ts: AsyncSession, attendant: UUID) -> UUID:
    brand_id = (await ts.scalars(select(BrandModel.id))).first()
    assert brand_id is not None
    ticket = TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=attendant,
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    ts.add(ticket)
    await ts.flush()
    return ticket.id


def _anexo(ticket_id: UUID, author: UUID, **over: object) -> TicketAttachment:
    base: dict[str, object] = {
        "id": uuid4(),
        "ticket_id": ticket_id,
        "filename": "foto.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 999,
        "object_key": f"acme/{ticket_id}/{uuid4()}.jpg",
        "kind": AttachmentKind.IMAGEM,
        "status": AttachmentStatus.PENDENTE,
        "preview_status": PreviewStatus.PENDENTE,
        "author_user_id": author,
    }
    base.update(over)
    return TicketAttachment(**base)  # type: ignore[arg-type]


async def test_lista_traz_apenas_disponiveis_e_nao_deletados(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanex")
    user = await seed_user(session, email="repoanex@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        disponivel = _anexo(ticket_id, user.id, status=AttachmentStatus.DISPONIVEL)
        pendente = _anexo(ticket_id, user.id)
        deletado = _anexo(
            ticket_id,
            user.id,
            status=AttachmentStatus.DISPONIVEL,
            deleted_at=datetime.now(UTC),
        )
        for a in (disponivel, pendente, deletado):
            await repos.attachments.add(a)
        await ts.flush()

        listados = await repos.attachments.list_by_ticket(ticket_id)
        assert [a.id for a in listados] == [disponivel.id]
        # cota conta pendentes tambem, mas nao deletados
        assert await repos.attachments.count_active(ticket_id) == 2
        await ts.commit()


async def test_update_e_get_preservam_campos(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanexupd")
    user = await seed_user(session, email="repoanexupd@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = _anexo(ticket_id, user.id)
        await repos.attachments.add(anexo)
        await ts.flush()

        anexo.status = AttachmentStatus.DISPONIVEL
        anexo.confirmed_at = datetime.now(UTC)
        anexo.preview_key = "acme/x/previews/y.webp"
        anexo.preview_medium_key = "acme/x/previews/y_medium.webp"
        anexo.preview_status = PreviewStatus.PRONTO
        await repos.attachments.update(anexo)
        await ts.flush()

        lido = await repos.attachments.get(anexo.id)
        assert lido is not None
        assert lido.status is AttachmentStatus.DISPONIVEL
        assert lido.preview_status is PreviewStatus.PRONTO
        assert lido.preview_medium_key == "acme/x/previews/y_medium.webp"
        assert lido.confirmed_at is not None
        await ts.commit()


async def test_pendentes_antigos_sao_encontrados(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanexexp")
    user = await seed_user(session, email="repoanexexp@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        antigo = _anexo(ticket_id, user.id)
        await repos.attachments.add(antigo)
        await ts.flush()
        # envelhece o registro direto no banco
        await ts.execute(
            select(ProductModel.id).limit(0)
        )  # no-op para manter a sessao ativa
        from sqlalchemy import text

        await ts.execute(
            text(
                "UPDATE tenant.ticket_attachments SET created_at = now() - interval '2 hours'"
            )
        )
        encontrados = await repos.attachments.list_pending_before(
            datetime.now(UTC) - timedelta(minutes=30)
        )
        assert [a.id for a in encontrados] == [antigo.id]
        await ts.commit()


async def test_fila_claim_marca_processando_e_pula_travado(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    job = PreviewJob(
        id=uuid4(),
        tenant_slug="acme",
        object_key="acme/t/x.jpg",
        kind=AttachmentKind.IMAGEM,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=agora - timedelta(seconds=1),
        attachment_id=uuid4(),
    )
    await jobs.add(job)
    await session.flush()

    pego = await jobs.claim_next(agora)
    assert pego is not None and pego.id == job.id
    assert pego.status is PreviewJobStatus.PROCESSANDO
    # ja em processamento: nao volta
    assert await jobs.claim_next(agora) is None


async def test_fila_respeita_next_attempt_at(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    await jobs.add(
        PreviewJob(
            id=uuid4(),
            tenant_slug="acme",
            object_key="acme/t/futuro.jpg",
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=1,
            next_attempt_at=agora + timedelta(minutes=5),
            attachment_id=uuid4(),
        )
    )
    await session.flush()
    assert await jobs.claim_next(agora) is None


async def test_mark_failed_reagenda_e_esgota(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    job = PreviewJob(
        id=uuid4(),
        tenant_slug="acme",
        object_key="acme/t/falha.jpg",
        kind=AttachmentKind.IMAGEM,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=agora - timedelta(seconds=1),
        attachment_id=uuid4(),
    )
    await jobs.add(job)
    await session.flush()
    await jobs.claim_next(agora)

    await jobs.mark_failed(
        job.id, "boom", agora + timedelta(minutes=1), exhausted=False
    )
    await session.flush()
    relido = await jobs.get(job.id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.PENDENTE
    assert relido.attempts == 1
    assert relido.last_error == "boom"

    await jobs.mark_failed(job.id, "boom final", agora, exhausted=True)
    await session.flush()
    final = await jobs.get(job.id)
    assert final is not None and final.status is PreviewJobStatus.FALHOU


async def test_foto_do_produto_grava_e_le(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repofoto")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        produto = ProductModel(id=uuid4(), name="Com foto", sku="CF-1")
        ts.add(produto)
        await ts.flush()

        await repos.photos.set_photo(produto.id, "k/original.png", "k/previews/original.webp")
        await ts.flush()
        assert await repos.photos.get_photo(produto.id) == (
            "k/original.png",
            "k/previews/original.webp",
        )

        await repos.photos.set_photo(produto.id, None, None)
        await ts.flush()
        assert await repos.photos.get_photo(produto.id) == (None, None)
        assert await repos.photos.get_photo(uuid4()) is None
        await ts.commit()


async def test_membros_do_tenant_com_nome_e_papel(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repomembros")
    outro = await seed_provisioned_tenant(session, engine, slug="repooutro")
    admin = await seed_user(session, email="admin@repomembros.com", name="Ana Admin")
    atendente = await seed_user(session, email="att@repomembros.com", name="Bruno Atendente")
    de_fora = await seed_user(session, email="fora@repooutro.com", name="Carlos Fora")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=atendente, tenant=tenant, role=Role.ATENDENTE)
    await seed_link(session, user=de_fora, tenant=outro, role=Role.ADMIN)

    membros = await SqlTenantMemberDirectory(session).list_members(tenant.slug)
    assert [(m.name, m.role) for m in membros] == [
        ("Ana Admin", Role.ADMIN),
        ("Bruno Atendente", Role.ATENDENTE),
    ]
    assert all(m.active for m in membros)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_repositories_attachments.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 3: Completar os ports**

Acrescentar em `backend/src/sac/application/ports_attachments.py` (imports: `datetime`, `UUID`, `Protocol`, entidades da Task 1, `Role`):

```python
@dataclass(frozen=True)
class TenantMember:
    id: UUID
    name: str
    role: Role
    active: bool


class AttachmentRepository(Protocol):
    async def add(self, attachment: TicketAttachment) -> None: ...
    async def get(self, attachment_id: UUID) -> TicketAttachment | None: ...
    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketAttachment]: ...
    async def count_active(self, ticket_id: UUID) -> int: ...
    async def update(self, attachment: TicketAttachment) -> None: ...
    async def list_pending_before(self, moment: datetime) -> list[TicketAttachment]: ...


class PreviewJobRepository(Protocol):
    async def add(self, job: PreviewJob) -> None: ...
    async def get(self, job_id: UUID) -> PreviewJob | None: ...
    async def claim_next(self, now: datetime) -> PreviewJob | None: ...
    async def mark_done(self, job_id: UUID) -> None: ...
    async def mark_failed(
        self, job_id: UUID, error: str, next_attempt_at: datetime, exhausted: bool
    ) -> None: ...


class ProductPhotoRepository(Protocol):
    async def set_photo(
        self, product_id: UUID, photo_key: str | None, preview_key: str | None
    ) -> None: ...
    async def get_photo(self, product_id: UUID) -> tuple[str | None, str | None] | None: ...


class TenantMemberDirectory(Protocol):
    async def list_members(self, tenant_slug: str) -> list[TenantMember]: ...
```

- [ ] **Step 4: Implementar os repositórios**

Criar `backend/src/sac/infrastructure/repositories_attachments.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_attachments import TenantMember
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
)
from sac.domain.errors import NotFoundError
from sac.domain.permissions import Role
from sac.infrastructure.models import PreviewJobModel, TenantModel, UserModel, UserTenantModel
from sac.infrastructure.models_tenant import ProductModel, TicketAttachmentModel
from sac.infrastructure.repositories_tickets import flush_tickets


def _entity(m: TicketAttachmentModel) -> TicketAttachment:
    return TicketAttachment(
        id=m.id,
        ticket_id=m.ticket_id,
        filename=m.filename,
        content_type=m.content_type,
        size_bytes=m.size_bytes,
        object_key=m.object_key,
        kind=AttachmentKind(m.kind),
        status=AttachmentStatus(m.status),
        preview_status=PreviewStatus(m.preview_status),
        author_user_id=m.author_user_id,
        preview_key=m.preview_key,
        preview_medium_key=m.preview_medium_key,
        created_at=m.created_at,
        confirmed_at=m.confirmed_at,
        deleted_at=m.deleted_at,
    )


class SqlAttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attachment: TicketAttachment) -> None:
        self._session.add(
            TicketAttachmentModel(
                id=attachment.id,
                ticket_id=attachment.ticket_id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                object_key=attachment.object_key,
                kind=str(attachment.kind),
                status=str(attachment.status),
                preview_key=attachment.preview_key,
                preview_medium_key=attachment.preview_medium_key,
                preview_status=str(attachment.preview_status),
                author_user_id=attachment.author_user_id,
                confirmed_at=attachment.confirmed_at,
                deleted_at=attachment.deleted_at,
            )
        )
        await flush_tickets(self._session)

    async def get(self, attachment_id: UUID) -> TicketAttachment | None:
        m = await self._session.get(TicketAttachmentModel, attachment_id)
        return _entity(m) if m is not None else None

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketAttachment]:
        rows = await self._session.scalars(
            select(TicketAttachmentModel)
            .where(
                TicketAttachmentModel.ticket_id == ticket_id,
                TicketAttachmentModel.status == str(AttachmentStatus.DISPONIVEL),
                TicketAttachmentModel.deleted_at.is_(None),
            )
            .order_by(TicketAttachmentModel.created_at)
        )
        return [_entity(m) for m in rows]

    async def count_active(self, ticket_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(
                TicketAttachmentModel.ticket_id == ticket_id,
                TicketAttachmentModel.status.in_(
                    [str(AttachmentStatus.PENDENTE), str(AttachmentStatus.DISPONIVEL)]
                ),
                TicketAttachmentModel.deleted_at.is_(None),
            )
        )
        return int(total or 0)

    async def update(self, attachment: TicketAttachment) -> None:
        m = await self._session.get(TicketAttachmentModel, attachment.id)
        if m is None:
            raise NotFoundError("anexo nao encontrado")
        m.status = str(attachment.status)
        m.preview_status = str(attachment.preview_status)
        m.preview_key = attachment.preview_key
        m.preview_medium_key = attachment.preview_medium_key
        m.confirmed_at = attachment.confirmed_at
        m.deleted_at = attachment.deleted_at
        m.size_bytes = attachment.size_bytes
        m.content_type = attachment.content_type
        await flush_tickets(self._session)

    async def list_pending_before(self, moment: datetime) -> list[TicketAttachment]:
        rows = await self._session.scalars(
            select(TicketAttachmentModel).where(
                TicketAttachmentModel.status == str(AttachmentStatus.PENDENTE),
                TicketAttachmentModel.created_at < moment,
            )
        )
        return [_entity(m) for m in rows]


def _job_entity(m: PreviewJobModel) -> PreviewJob:
    return PreviewJob(
        id=m.id,
        tenant_slug=m.tenant_slug,
        object_key=m.object_key,
        kind=AttachmentKind(m.kind),
        status=PreviewJobStatus(m.status),
        attempts=m.attempts,
        next_attempt_at=m.next_attempt_at,
        attachment_id=m.attachment_id,
        product_id=m.product_id,
        last_error=m.last_error,
    )


class SqlPreviewJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: PreviewJob) -> None:
        self._session.add(
            PreviewJobModel(
                id=job.id,
                tenant_slug=job.tenant_slug,
                attachment_id=job.attachment_id,
                product_id=job.product_id,
                object_key=job.object_key,
                kind=str(job.kind),
                status=str(job.status),
                attempts=job.attempts,
                next_attempt_at=job.next_attempt_at,
                last_error=job.last_error,
            )
        )
        await self._session.flush()

    async def get(self, job_id: UUID) -> PreviewJob | None:
        m = await self._session.get(PreviewJobModel, job_id)
        return _job_entity(m) if m is not None else None

    async def claim_next(self, now: datetime) -> PreviewJob | None:
        m = await self._session.scalar(
            select(PreviewJobModel)
            .where(
                PreviewJobModel.status == str(PreviewJobStatus.PENDENTE),
                PreviewJobModel.next_attempt_at <= now,
            )
            .order_by(PreviewJobModel.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if m is None:
            return None
        m.status = str(PreviewJobStatus.PROCESSANDO)
        await self._session.flush()
        return _job_entity(m)

    async def mark_done(self, job_id: UUID) -> None:
        await self._session.execute(
            update(PreviewJobModel)
            .where(PreviewJobModel.id == job_id)
            .values(status=str(PreviewJobStatus.PRONTO), last_error=None)
        )
        await self._session.flush()

    async def mark_failed(
        self, job_id: UUID, error: str, next_attempt_at: datetime, exhausted: bool
    ) -> None:
        status = PreviewJobStatus.FALHOU if exhausted else PreviewJobStatus.PENDENTE
        await self._session.execute(
            update(PreviewJobModel)
            .where(PreviewJobModel.id == job_id)
            .values(
                status=str(status),
                attempts=PreviewJobModel.attempts + 1,
                next_attempt_at=next_attempt_at,
                last_error=error[:500],
            )
        )
        await self._session.flush()


class SqlProductPhotoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_photo(
        self, product_id: UUID, photo_key: str | None, preview_key: str | None
    ) -> None:
        m = await self._session.get(ProductModel, product_id)
        if m is None:
            raise NotFoundError("produto nao encontrado")
        m.photo_key = photo_key
        m.photo_preview_key = preview_key
        await self._session.flush()

    async def get_photo(self, product_id: UUID) -> tuple[str | None, str | None] | None:
        m = await self._session.get(ProductModel, product_id)
        if m is None:
            return None
        return m.photo_key, m.photo_preview_key


class SqlTenantMemberDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_members(self, tenant_slug: str) -> list[TenantMember]:
        rows = await self._session.execute(
            select(UserModel.id, UserModel.name, UserTenantModel.role, UserTenantModel.active)
            .join(UserTenantModel, UserTenantModel.user_id == UserModel.id)
            .join(TenantModel, TenantModel.id == UserTenantModel.tenant_id)
            .where(
                TenantModel.slug == tenant_slug,
                UserTenantModel.active.is_(True),
                UserModel.active.is_(True),
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.name)
        )
        return [
            TenantMember(id=row[0], name=row[1], role=Role(row[2]), active=row[3])
            for row in rows.all()
        ]


@dataclass
class AttachmentRepos:
    attachments: SqlAttachmentRepository
    jobs: SqlPreviewJobRepository
    photos: SqlProductPhotoRepository


def build_attachment_repos(session: AsyncSession) -> AttachmentRepos:
    return AttachmentRepos(
        attachments=SqlAttachmentRepository(session),
        jobs=SqlPreviewJobRepository(session),
        photos=SqlProductPhotoRepository(session),
    )
```

Nota: `datetime`/`UTC` podem ficar sem uso no módulo — remova o import se o ruff acusar. `SqlTenantMemberDirectory` roda no schema público, então recebe a sessão global (`get_session`), não a do tenant.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_repositories_attachments.py -v`
Esperado: PASS (8 testes).

- [ ] **Step 6: Verificações completas e commit**

```bash
git add backend/src/sac/application/ports_attachments.py backend/src/sac/infrastructure/repositories_attachments.py backend/tests/integration/test_repositories_attachments.py
git commit -m "Adiciona repositorios de anexos, fila de previews, foto e membros"
```

---

### Task 5: Use cases de anexos

**Files:**
- Create: `backend/src/sac/application/use_cases/attachments.py`
- Create: `backend/tests/unit/fakes_attachments.py`
- Test: `backend/tests/unit/application/test_attachments_use_cases.py`

**Interfaces:**
- Consumes: domínio da Task 1; ports da Task 4; `TicketActor`, `TicketRepository` (`ports_tickets.py`); `get_ticket_or_404` (`use_cases/tickets_shared.py`); `is_closed` (`domain/tickets.py`); `Permission`/`has_permission`; `InMemoryTicketRepository` (`tests/unit/fakes_tickets.py`).
- Produces:
  - `UploadIntentInput(filename: str, content_type: str, size_bytes: int, with_preview: bool = False)` (frozen)
  - `UploadIntent(attachment_id: UUID, object_key: str, upload_url: str, expires_in: int, preview_upload_url: str | None)` (frozen)
  - `AttachmentView(attachment: TicketAttachment, preview_url: str | None)` (frozen)
  - `RequestUploadUseCase(tickets, attachments, storage, tenant_slug: str, ttl_seconds: int = 300, max_per_ticket: int = MAX_ATTACHMENTS_PER_TICKET).execute(actor, ticket_id, data) -> UploadIntent`
  - `ConfirmUploadUseCase(tickets, attachments, jobs, storage, tenant_slug: str).execute(actor, ticket_id, attachment_id) -> TicketAttachment`
  - `ListAttachmentsUseCase(tickets, attachments, storage, ttl_seconds: int = 300).execute(actor, ticket_id) -> list[AttachmentView]`
  - `GetAttachmentUrlUseCase(tickets, attachments, storage, ttl_seconds: int = 300).execute(actor, ticket_id, attachment_id, variant: str = "medio") -> str`
  - `DeleteAttachmentUseCase(tickets, attachments).execute(actor, ticket_id, attachment_id) -> None`
  - `ExpirePendingUseCase(attachments, minutes: int = 30).execute() -> int`
- Produces (fakes): `InMemoryAttachmentRepository`, `InMemoryPreviewJobRepository` (expõe `items`), `InMemoryProductPhotoRepository`, `InMemoryTenantMemberDirectory`, `FakeStorage` com `objects: dict[str, tuple[bytes, str]]`, `simulate_upload(key, data, content_type)` e URLs previsíveis (`https://fake/put/{key}` e `https://fake/get/{key}`).

- [ ] **Step 1: Escrever os fakes**

`backend/tests/unit/fakes_attachments.py`:

```python
from datetime import datetime
from uuid import UUID

from sac.application.ports_attachments import ObjectHead, TenantMember
from sac.domain.attachments import (
    PreviewJob,
    PreviewJobStatus,
    TicketAttachment,
)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.assinaturas: list[tuple[str, str]] = []

    def simulate_upload(self, key: str, data: bytes, content_type: str) -> None:
        """Faz o papel do navegador: grava no bucket sem passar pelo backend."""
        self.objects[key] = (data, content_type)

    def presigned_put(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> str:
        self.assinaturas.append(("put", key))
        return f"https://fake/put/{key}"

    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        self.assinaturas.append(("get", key))
        return f"https://fake/get/{key}"

    def head(self, key: str) -> ObjectHead | None:
        found = self.objects.get(key)
        if found is None:
            return None
        data, content_type = found
        return ObjectHead(content_type=content_type, size_bytes=len(data))

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key][0]


class InMemoryAttachmentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, TicketAttachment] = {}

    async def add(self, attachment: TicketAttachment) -> None:
        self.items[attachment.id] = attachment

    async def get(self, attachment_id: UUID) -> TicketAttachment | None:
        return self.items.get(attachment_id)

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketAttachment]:
        from sac.domain.attachments import AttachmentStatus

        return [
            a
            for a in self.items.values()
            if a.ticket_id == ticket_id
            and a.status is AttachmentStatus.DISPONIVEL
            and a.deleted_at is None
        ]

    async def count_active(self, ticket_id: UUID) -> int:
        from sac.domain.attachments import AttachmentStatus

        return sum(
            1
            for a in self.items.values()
            if a.ticket_id == ticket_id
            and a.deleted_at is None
            and a.status in (AttachmentStatus.PENDENTE, AttachmentStatus.DISPONIVEL)
        )

    async def update(self, attachment: TicketAttachment) -> None:
        self.items[attachment.id] = attachment

    async def list_pending_before(self, moment: datetime) -> list[TicketAttachment]:
        from sac.domain.attachments import AttachmentStatus

        return [
            a
            for a in self.items.values()
            if a.status is AttachmentStatus.PENDENTE
            and a.created_at is not None
            and a.created_at < moment
        ]


class InMemoryPreviewJobRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, PreviewJob] = {}

    async def add(self, job: PreviewJob) -> None:
        self.items[job.id] = job

    async def get(self, job_id: UUID) -> PreviewJob | None:
        return self.items.get(job_id)

    async def claim_next(self, now: datetime) -> PreviewJob | None:
        for job in self.items.values():
            if job.status is PreviewJobStatus.PENDENTE and job.next_attempt_at <= now:
                job.status = PreviewJobStatus.PROCESSANDO
                return job
        return None

    async def mark_done(self, job_id: UUID) -> None:
        self.items[job_id].status = PreviewJobStatus.PRONTO

    async def mark_failed(
        self, job_id: UUID, error: str, next_attempt_at: datetime, exhausted: bool
    ) -> None:
        job = self.items[job_id]
        job.attempts += 1
        job.last_error = error
        job.next_attempt_at = next_attempt_at
        job.status = PreviewJobStatus.FALHOU if exhausted else PreviewJobStatus.PENDENTE


class InMemoryProductPhotoRepository:
    def __init__(self) -> None:
        self.photos: dict[UUID, tuple[str | None, str | None]] = {}

    async def set_photo(
        self, product_id: UUID, photo_key: str | None, preview_key: str | None
    ) -> None:
        self.photos[product_id] = (photo_key, preview_key)

    async def get_photo(self, product_id: UUID) -> tuple[str | None, str | None] | None:
        return self.photos.get(product_id)


class InMemoryTenantMemberDirectory:
    def __init__(self, members: dict[str, list[TenantMember]] | None = None) -> None:
        self.members = members or {}

    async def list_members(self, tenant_slug: str) -> list[TenantMember]:
        return self.members.get(tenant_slug, [])
```

- [ ] **Step 2: Escrever o teste que falha**

`backend/tests/unit/application/test_attachments_use_cases.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.attachments import (
    ConfirmUploadUseCase,
    DeleteAttachmentUseCase,
    ExpirePendingUseCase,
    GetAttachmentUrlUseCase,
    ListAttachmentsUseCase,
    RequestUploadUseCase,
    UploadIntentInput,
)
from sac.domain.attachments import (
    AttachmentStatus,
    PreviewStatus,
)
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketPriority, TicketStatus
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryAttachmentRepository,
    InMemoryPreviewJobRepository,
)
from tests.unit.fakes_tickets import InMemoryTicketRepository

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)
SLUG = "acme"


class Env:
    def __init__(self) -> None:
        self.tickets = InMemoryTicketRepository()
        self.attachments = InMemoryAttachmentRepository()
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()

    async def ticket(self, actor: TicketActor = ADMIN, **over: object) -> Ticket:
        agora = datetime.now(UTC)
        base: dict[str, object] = {
            "id": uuid4(),
            "number": 0,
            "brand_id": uuid4(),
            "status": TicketStatus.ABERTO,
            "priority": TicketPriority.MEDIA,
            "attendant_user_id": actor.user_id,
            "opened_at": agora,
            "due_at": agora + timedelta(hours=72),
            "last_activity_at": agora,
        }
        base.update(over)
        return await self.tickets.add(Ticket(**base))  # type: ignore[arg-type]

    def request_uc(self) -> RequestUploadUseCase:
        return RequestUploadUseCase(
            self.tickets, self.attachments, self.storage, tenant_slug=SLUG
        )

    def confirm_uc(self) -> ConfirmUploadUseCase:
        return ConfirmUploadUseCase(
            self.tickets, self.attachments, self.jobs, self.storage, tenant_slug=SLUG
        )


async def test_intencao_gera_chave_no_servidor_e_url_assinada() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput(filename="../etc/passwd.jpg", content_type="image/jpeg", size_bytes=1000),
    )
    assert intent.object_key.startswith(f"{SLUG}/{ticket.id}/")
    assert intent.object_key.endswith(".jpg")
    assert "passwd" not in intent.object_key
    assert intent.upload_url == f"https://fake/put/{intent.object_key}"
    assert intent.preview_upload_url is None
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    assert anexo.status is AttachmentStatus.PENDENTE
    assert anexo.preview_status is PreviewStatus.PENDENTE
    assert anexo.filename == "../etc/passwd.jpg"


async def test_intencao_de_video_com_preview_devolve_duas_urls() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput(
            filename="clipe.mp4",
            content_type="video/mp4",
            size_bytes=5_000_000,
            with_preview=True,
        ),
    )
    assert intent.preview_upload_url is not None
    assert "/previews/" in intent.preview_upload_url


async def test_intencao_recusa_tipo_tamanho_e_cota() -> None:
    env = Env()
    ticket = await env.ticket()
    uc = env.request_uc()
    with pytest.raises(ValidationError):
        await uc.execute(
            ADMIN, ticket.id, UploadIntentInput("x.gif", "image/gif", 100)
        )
    with pytest.raises(ValidationError):
        await uc.execute(
            ADMIN, ticket.id, UploadIntentInput("x.jpg", "image/jpeg", 52_428_801)
        )
    for _ in range(10):
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("ok.jpg", "image/jpeg", 10))
    with pytest.raises(ConflictError) as exc:
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("ok.jpg", "image/jpeg", 10))
    assert exc.value.details == {"limite": 10}


async def test_intencao_bloqueada_em_ticket_encerrado_e_para_alheio() -> None:
    env = Env()
    encerrado = await env.ticket(status=TicketStatus.FINALIZADO)
    with pytest.raises(ConflictError):
        await env.request_uc().execute(
            ADMIN, encerrado.id, UploadIntentInput("x.jpg", "image/jpeg", 10)
        )
    do_admin = await env.ticket()
    with pytest.raises(NotFoundError):
        await env.request_uc().execute(
            ATENDENTE, do_admin.id, UploadIntentInput("x.jpg", "image/jpeg", 10)
        )


async def test_confirmacao_de_imagem_enfileira_preview() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 12)
    )
    env.storage.simulate_upload(intent.object_key, b"123456789012", "image/jpeg")

    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.status is AttachmentStatus.DISPONIVEL
    assert anexo.confirmed_at is not None
    assert anexo.preview_status is PreviewStatus.PENDENTE
    assert len(env.jobs.items) == 1
    job = next(iter(env.jobs.items.values()))
    assert job.tenant_slug == SLUG
    assert job.attachment_id == anexo.id
    assert job.object_key == anexo.object_key


async def test_confirmacao_de_pdf_nao_gera_job() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("nota.pdf", "application/pdf", 5)
    )
    env.storage.simulate_upload(intent.object_key, b"12345", "application/pdf")
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.SEM_PREVIEW
    assert env.jobs.items == {}


async def test_confirmacao_de_video_usa_thumb_do_navegador() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput("clipe.mp4", "video/mp4", 9, with_preview=True),
    )
    env.storage.simulate_upload(intent.object_key, b"123456789", "video/mp4")
    assert intent.preview_upload_url is not None
    preview_key = intent.preview_upload_url.removeprefix("https://fake/put/")
    env.storage.simulate_upload(preview_key, b"webp", "image/webp")

    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.PRONTO
    assert anexo.preview_key == preview_key
    assert env.jobs.items == {}


async def test_confirmacao_de_video_sem_thumb_fica_sem_preview() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput("clipe.mp4", "video/mp4", 9, with_preview=True),
    )
    env.storage.simulate_upload(intent.object_key, b"123456789", "video/mp4")
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.SEM_PREVIEW


async def test_confirmacao_falha_sem_objeto_ou_com_head_divergente() -> None:
    env = Env()
    ticket = await env.ticket()
    uc = env.confirm_uc()

    sem_objeto = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, sem_objeto.attachment_id)
    assert exc.value.details == {"field": "object_key"}

    grande = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(grande.object_key, b"x" * 52_428_801, "image/jpeg")
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, grande.attachment_id)
    assert exc.value.details == {"field": "size_bytes"}

    mime_errado = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(mime_errado.object_key, b"1234567890", "application/pdf")
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, mime_errado.attachment_id)
    assert exc.value.details == {"field": "content_type"}


async def test_listagem_traz_url_de_preview_apenas_quando_pronto() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

    vistas = await ListAttachmentsUseCase(
        env.tickets, env.attachments, env.storage
    ).execute(ADMIN, ticket.id)
    assert len(vistas) == 1
    assert vistas[0].preview_url is None

    anexo.preview_status = PreviewStatus.PRONTO
    anexo.preview_key = "acme/t/previews/x.webp"
    await env.attachments.update(anexo)
    vistas = await ListAttachmentsUseCase(
        env.tickets, env.attachments, env.storage
    ).execute(ADMIN, ticket.id)
    assert vistas[0].preview_url == "https://fake/get/acme/t/previews/x.webp"


async def test_url_por_variante() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    anexo.preview_status = PreviewStatus.PRONTO
    anexo.preview_medium_key = "acme/t/previews/x_medium.webp"
    await env.attachments.update(anexo)

    uc = GetAttachmentUrlUseCase(env.tickets, env.attachments, env.storage)
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "medio") == (
        "https://fake/get/acme/t/previews/x_medium.webp"
    )
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "original") == (
        f"https://fake/get/{anexo.object_key}"
    )
    # sem preview medio, medio cai no original
    anexo.preview_medium_key = None
    await env.attachments.update(anexo)
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "medio") == (
        f"https://fake/get/{anexo.object_key}"
    )


async def test_exclusao_por_autor_e_por_papel() -> None:
    env = Env()
    ticket = await env.ticket(actor=ATENDENTE)
    intent = await env.request_uc().execute(
        ATENDENTE, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    anexo = await env.confirm_uc().execute(ATENDENTE, ticket.id, intent.attachment_id)

    uc = DeleteAttachmentUseCase(env.tickets, env.attachments)
    # admin pode excluir anexo de outro autor
    await uc.execute(ADMIN, ticket.id, anexo.id)
    apagado = await env.attachments.get(anexo.id)
    assert apagado is not None and apagado.deleted_at is not None
    # o objeto permanece no bucket
    assert anexo.object_key in env.storage.objects


async def test_atendente_nao_exclui_anexo_de_outro_autor() -> None:
    env = Env()
    ticket = await env.ticket(actor=ATENDENTE)
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

    with pytest.raises(PermissionDeniedError):
        await DeleteAttachmentUseCase(env.tickets, env.attachments).execute(
            ATENDENTE, ticket.id, anexo.id
        )


async def test_pendentes_antigos_expiram() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    anexo.created_at = datetime.now(UTC) - timedelta(hours=2)
    await env.attachments.update(anexo)

    total = await ExpirePendingUseCase(env.attachments, minutes=30).execute()
    assert total == 1
    expirado = await env.attachments.get(anexo.id)
    assert expirado is not None and expirado.status is AttachmentStatus.EXPIRADO
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_attachments_use_cases.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 4: Implementar os use cases**

`backend/src/sac/application/use_cases/attachments.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sac.application.ports_attachments import (
    AttachmentRepository,
    PreviewJobRepository,
    StoragePort,
)
from sac.application.ports_tickets import TicketActor, TicketRepository
from sac.application.use_cases.tickets_shared import get_ticket_or_404
from sac.domain.attachments import (
    MAX_ATTACHMENTS_PER_TICKET,
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    build_object_key,
    kind_for,
    preview_keys_for,
    validate_size,
)
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import is_closed


@dataclass(frozen=True)
class UploadIntentInput:
    filename: str
    content_type: str
    size_bytes: int
    with_preview: bool = False


@dataclass(frozen=True)
class UploadIntent:
    attachment_id: UUID
    object_key: str
    upload_url: str
    expires_in: int
    preview_upload_url: str | None


@dataclass(frozen=True)
class AttachmentView:
    attachment: TicketAttachment
    preview_url: str | None


def _ensure_open(ticket_status: object) -> None:
    if is_closed(ticket_status):  # type: ignore[arg-type]
        raise ConflictError("ticket encerrado nao aceita alteracao de anexos")


async def _attachment_of_ticket(
    attachments: AttachmentRepository, ticket_id: UUID, attachment_id: UUID
) -> TicketAttachment:
    anexo = await attachments.get(attachment_id)
    if anexo is None or anexo.ticket_id != ticket_id or anexo.deleted_at is not None:
        raise NotFoundError("anexo nao encontrado")
    return anexo


class RequestUploadUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        attachments: AttachmentRepository,
        storage: StoragePort,
        tenant_slug: str,
        ttl_seconds: int = 300,
        max_per_ticket: int = MAX_ATTACHMENTS_PER_TICKET,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._ttl = ttl_seconds
        self._max_per_ticket = max_per_ticket
        self._max_bytes = max_bytes

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, data: UploadIntentInput
    ) -> UploadIntent:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita anexos")
        kind = kind_for(data.content_type)
        validate_size(data.size_bytes)
        if await self._attachments.count_active(ticket.id) >= self._max_per_ticket:
            raise ConflictError(
                "limite de anexos por ticket atingido",
                details={"limite": self._max_per_ticket},
            )
        attachment_id = uuid4()
        object_key = build_object_key(
            self._tenant_slug, ticket.id, data.content_type, attachment_id
        )
        thumb_key, _ = preview_keys_for(object_key)
        preview_url: str | None = None
        preview_key: str | None = None
        if data.with_preview and kind is AttachmentKind.VIDEO:
            preview_key = thumb_key
            preview_url = self._storage.presigned_put(
                thumb_key, "image/webp", self._max_bytes, self._ttl
            )
        preview_status = (
            PreviewStatus.PENDENTE if kind is AttachmentKind.IMAGEM else PreviewStatus.SEM_PREVIEW
        )
        await self._attachments.add(
            TicketAttachment(
                id=attachment_id,
                ticket_id=ticket.id,
                filename=data.filename,
                content_type=data.content_type,
                size_bytes=data.size_bytes,
                object_key=object_key,
                kind=kind,
                status=AttachmentStatus.PENDENTE,
                preview_status=preview_status,
                author_user_id=actor.user_id,
                preview_key=preview_key,
                created_at=datetime.now(UTC),
            )
        )
        return UploadIntent(
            attachment_id=attachment_id,
            object_key=object_key,
            upload_url=self._storage.presigned_put(
                object_key, data.content_type, self._max_bytes, self._ttl
            ),
            expires_in=self._ttl,
            preview_upload_url=preview_url,
        )


class ConfirmUploadUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        attachments: AttachmentRepository,
        jobs: PreviewJobRepository,
        storage: StoragePort,
        tenant_slug: str,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._jobs = jobs
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._max_bytes = max_bytes

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID
    ) -> TicketAttachment:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita anexos")
        anexo = await _attachment_of_ticket(self._attachments, ticket.id, attachment_id)

        head = self._storage.head(anexo.object_key)
        if head is None:
            raise ValidationError(
                "objeto nao encontrado no storage", details={"field": "object_key"}
            )
        if head.size_bytes < 1 or head.size_bytes > self._max_bytes:
            raise ValidationError(
                "tamanho real do objeto invalido", details={"field": "size_bytes"}
            )
        if head.content_type != anexo.content_type:
            raise ValidationError(
                "tipo real do objeto diferente do declarado",
                details={"field": "content_type"},
            )

        anexo.size_bytes = head.size_bytes
        anexo.status = AttachmentStatus.DISPONIVEL
        anexo.confirmed_at = datetime.now(UTC)

        if anexo.kind is AttachmentKind.IMAGEM:
            anexo.preview_status = PreviewStatus.PENDENTE
        elif anexo.kind is AttachmentKind.VIDEO and anexo.preview_key is not None:
            if self._storage.head(anexo.preview_key) is not None:
                anexo.preview_status = PreviewStatus.PRONTO
            else:
                anexo.preview_key = None
                anexo.preview_status = PreviewStatus.SEM_PREVIEW
        else:
            anexo.preview_status = PreviewStatus.SEM_PREVIEW

        await self._attachments.update(anexo)

        if anexo.kind is AttachmentKind.IMAGEM:
            await self._jobs.add(
                PreviewJob(
                    id=uuid4(),
                    tenant_slug=self._tenant_slug,
                    object_key=anexo.object_key,
                    kind=anexo.kind,
                    status=PreviewJobStatus.PENDENTE,
                    attempts=0,
                    next_attempt_at=datetime.now(UTC),
                    attachment_id=anexo.id,
                )
            )
        return anexo


class ListAttachmentsUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        attachments: AttachmentRepository,
        storage: StoragePort,
        ttl_seconds: int = 300,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage
        self._ttl = ttl_seconds

    async def execute(self, actor: TicketActor, ticket_id: UUID) -> list[AttachmentView]:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        anexos = await self._attachments.list_by_ticket(ticket.id)
        vistas: list[AttachmentView] = []
        for anexo in anexos:
            url = (
                self._storage.presigned_get(anexo.preview_key, self._ttl)
                if anexo.preview_status is PreviewStatus.PRONTO and anexo.preview_key
                else None
            )
            vistas.append(AttachmentView(attachment=anexo, preview_url=url))
        return vistas


class GetAttachmentUrlUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        attachments: AttachmentRepository,
        storage: StoragePort,
        ttl_seconds: int = 300,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage
        self._ttl = ttl_seconds

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID, variant: str = "medio"
    ) -> str:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        anexo = await _attachment_of_ticket(self._attachments, ticket.id, attachment_id)
        chave = anexo.object_key
        if variant == "medio" and anexo.preview_medium_key:
            chave = anexo.preview_medium_key
        return self._storage.presigned_get(chave, self._ttl)


class DeleteAttachmentUseCase:
    def __init__(
        self, tickets: TicketRepository, attachments: AttachmentRepository
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID
    ) -> None:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        if is_closed(ticket):
            raise ConflictError("ticket encerrado nao aceita alteracao de anexos")
        anexo = await _attachment_of_ticket(self._attachments, ticket.id, attachment_id)
        if anexo.author_user_id != actor.user_id and not has_permission(
            actor.role, Permission.DECIDIR_TICKET
        ):
            raise PermissionDeniedError("sem permissao para excluir anexo de outro autor")
        anexo.deleted_at = datetime.now(UTC)
        await self._attachments.update(anexo)


class ExpirePendingUseCase:
    def __init__(self, attachments: AttachmentRepository, minutes: int = 30) -> None:
        self._attachments = attachments
        self._minutes = minutes

    async def execute(self) -> int:
        limite = datetime.now(UTC) - timedelta(minutes=self._minutes)
        pendentes = await self._attachments.list_pending_before(limite)
        for anexo in pendentes:
            anexo.status = AttachmentStatus.EXPIRADO
            await self._attachments.update(anexo)
        return len(pendentes)
```

Nota: apague o helper `_ensure_open` mostrado no início do arquivo — cada use case chama `is_closed(ticket)` direto, que é mais claro e evita o `type: ignore`.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/application/test_attachments_use_cases.py -v`
Esperado: PASS (13 testes).

- [ ] **Step 6: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/attachments.py backend/tests/unit/fakes_attachments.py backend/tests/unit/application/test_attachments_use_cases.py
git commit -m "Adiciona use cases de anexo com intencao, confirmacao e expiracao"
```

---

### Task 6: Geração de previews (Pillow) e use case do worker

**Files:**
- Create: `backend/src/sac/infrastructure/images.py`
- Create: `backend/src/sac/application/use_cases/previews.py`
- Test: `backend/tests/unit/infrastructure/test_images.py`
- Test: `backend/tests/unit/application/test_previews_use_case.py`

**Interfaces:**
- Consumes: `StoragePort`, `AttachmentRepository`, `PreviewJobRepository`, `ProductPhotoRepository` (Task 4); `next_backoff`, `MAX_PREVIEW_ATTEMPTS`, `preview_keys_for`, `PreviewStatus` (Task 1); fakes da Task 5.
- Produces:
  - `generate_previews(data: bytes, thumb_px: int = 400, medium_px: int = 1200) -> tuple[bytes, bytes]` (WebP; levanta `ValidationError` se os bytes não forem imagem decodificável) e `PreviewGenerator` (Protocol em `ports_attachments.py`: `__call__(data: bytes) -> tuple[bytes, bytes]`).
  - `ProcessPreviewJobUseCase(jobs, storage, generate, attachments_for, photos_for).execute(now: datetime) -> bool` — devolve `True` se processou algo. `attachments_for`/`photos_for` são callables `(tenant_slug) -> repo`, porque cada tenant tem seu schema e o worker atravessa tenants.

- [ ] **Step 1: Escrever o teste de imagens**

`backend/tests/unit/infrastructure/test_images.py`:

```python
import io

import pytest
from PIL import Image

from sac.domain.errors import ValidationError
from sac.infrastructure.images import generate_previews


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 100, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_gera_thumb_e_media_em_webp_respeitando_proporcao() -> None:
    thumb, medio = generate_previews(_png(3000, 1500))
    with Image.open(io.BytesIO(thumb)) as img:
        assert img.format == "WEBP"
        assert img.width == 400
        assert img.height == 200
    with Image.open(io.BytesIO(medio)) as img:
        assert img.format == "WEBP"
        assert img.width == 1200
        assert img.height == 600


def test_imagem_menor_que_o_alvo_nao_e_ampliada() -> None:
    thumb, medio = generate_previews(_png(200, 100))
    with Image.open(io.BytesIO(thumb)) as img:
        assert (img.width, img.height) == (200, 100)
    with Image.open(io.BytesIO(medio)) as img:
        assert (img.width, img.height) == (200, 100)


def test_bytes_que_nao_sao_imagem_viram_erro_de_validacao() -> None:
    with pytest.raises(ValidationError):
        generate_previews(b"isto nao e uma imagem")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/infrastructure/test_images.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar `images.py`**

```python
import io

from PIL import Image, UnidentifiedImageError

from sac.domain.errors import ValidationError

# Limite defensivo: uma imagem gigante nao pode derrubar o worker por memoria.
Image.MAX_IMAGE_PIXELS = 80_000_000


def _resize(source: Image.Image, largest_side: int) -> bytes:
    copy = source.copy()
    copy.thumbnail((largest_side, largest_side), Image.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="WEBP", quality=82, method=4)
    return buffer.getvalue()


def generate_previews(
    data: bytes, thumb_px: int = 400, medium_px: int = 1200
) -> tuple[bytes, bytes]:
    try:
        with Image.open(io.BytesIO(data)) as original:
            original.load()
            rgb = original.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("arquivo nao e uma imagem valida") from exc
    return _resize(rgb, thumb_px), _resize(rgb, medium_px)
```

- [ ] **Step 4: Escrever o teste do use case**

`backend/tests/unit/application/test_previews_use_case.py`:

```python
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sac.application.use_cases.previews import ProcessPreviewJobUseCase
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryAttachmentRepository,
    InMemoryPreviewJobRepository,
    InMemoryProductPhotoRepository,
)

SLUG = "acme"


def _fake_generate(data: bytes) -> tuple[bytes, bytes]:
    return b"thumb:" + data, b"medium:" + data


class Env:
    def __init__(self) -> None:
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()
        self.attachments = InMemoryAttachmentRepository()
        self.photos = InMemoryProductPhotoRepository()

    def use_case(self, generate=_fake_generate) -> ProcessPreviewJobUseCase:
        return ProcessPreviewJobUseCase(
            jobs=self.jobs,
            storage=self.storage,
            generate=generate,
            attachments_for=lambda slug: self.attachments,
            photos_for=lambda slug: self.photos,
        )

    async def anexo_com_job(self) -> tuple[TicketAttachment, PreviewJob]:
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=uuid4(),
            filename="foto.jpg",
            content_type="image/jpeg",
            size_bytes=10,
            object_key=f"{SLUG}/t/{uuid4()}.jpg",
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=uuid4(),
        )
        await self.attachments.add(anexo)
        self.storage.simulate_upload(anexo.object_key, b"original", "image/jpeg")
        job = PreviewJob(
            id=uuid4(),
            tenant_slug=SLUG,
            object_key=anexo.object_key,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=anexo.id,
        )
        await self.jobs.add(job)
        return anexo, job


async def test_processa_job_e_grava_os_dois_previews() -> None:
    env = Env()
    anexo, job = await env.anexo_com_job()
    processou = await env.use_case().execute(datetime.now(UTC))
    assert processou is True

    thumb_key, medium_key = preview_keys_for(anexo.object_key)
    assert env.storage.objects[thumb_key] == (b"thumb:original", "image/webp")
    assert env.storage.objects[medium_key] == (b"medium:original", "image/webp")

    atualizado = await env.attachments.get(anexo.id)
    assert atualizado is not None
    assert atualizado.preview_status is PreviewStatus.PRONTO
    assert atualizado.preview_key == thumb_key
    assert atualizado.preview_medium_key == medium_key
    assert env.jobs.items[job.id].status is PreviewJobStatus.PRONTO


async def test_fila_vazia_devolve_false() -> None:
    env = Env()
    assert await env.use_case().execute(datetime.now(UTC)) is False


async def test_falha_reagenda_com_backoff_e_esgota_na_quinta() -> None:
    env = Env()
    anexo, job = await env.anexo_com_job()

    def explode(data: bytes) -> tuple[bytes, bytes]:
        raise RuntimeError("pillow quebrou")

    agora = datetime.now(UTC)
    for tentativa in range(1, 6):
        job.status = PreviewJobStatus.PENDENTE
        job.next_attempt_at = agora - timedelta(seconds=1)
        assert await env.use_case(generate=explode).execute(agora) is True
        assert env.jobs.items[job.id].attempts == tentativa
        assert "pillow quebrou" in (env.jobs.items[job.id].last_error or "")

    assert env.jobs.items[job.id].status is PreviewJobStatus.FALHOU
    final = await env.attachments.get(anexo.id)
    assert final is not None and final.preview_status is PreviewStatus.FALHOU


async def test_job_de_produto_grava_no_repositorio_de_fotos() -> None:
    env = Env()
    produto_id = uuid4()
    chave = f"{SLUG}/catalogo/produtos/{produto_id}/{uuid4()}.png"
    env.storage.simulate_upload(chave, b"original", "image/png")
    await env.photos.set_photo(produto_id, chave, None)
    await env.jobs.add(
        PreviewJob(
            id=uuid4(),
            tenant_slug=SLUG,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            product_id=produto_id,
        )
    )
    assert await env.use_case().execute(datetime.now(UTC)) is True
    thumb_key, _ = preview_keys_for(chave)
    assert await env.photos.get_photo(produto_id) == (chave, thumb_key)
```

- [ ] **Step 5: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_previews_use_case.py -v`
Esperado: FAIL (módulo inexistente).

- [ ] **Step 6: Implementar o use case**

Acrescentar em `backend/src/sac/application/ports_attachments.py`:

```python
class PreviewGenerator(Protocol):
    def __call__(self, data: bytes) -> tuple[bytes, bytes]: ...
```

Criar `backend/src/sac/application/use_cases/previews.py`:

```python
from collections.abc import Callable
from datetime import datetime

from sac.application.ports_attachments import (
    AttachmentRepository,
    PreviewGenerator,
    PreviewJobRepository,
    ProductPhotoRepository,
    StoragePort,
)
from sac.domain.attachments import (
    MAX_PREVIEW_ATTEMPTS,
    PreviewStatus,
    next_backoff,
    preview_keys_for,
)


class ProcessPreviewJobUseCase:
    """Processa no maximo um job por chamada. O worker chama em laco; os testes
    chamam uma vez. Idempotente: reprocessar sobrescreve os mesmos objetos.
    """

    def __init__(
        self,
        jobs: PreviewJobRepository,
        storage: StoragePort,
        generate: PreviewGenerator,
        attachments_for: Callable[[str], AttachmentRepository],
        photos_for: Callable[[str], ProductPhotoRepository],
    ) -> None:
        self._jobs = jobs
        self._storage = storage
        self._generate = generate
        self._attachments_for = attachments_for
        self._photos_for = photos_for

    async def execute(self, now: datetime) -> bool:
        job = await self._jobs.claim_next(now)
        if job is None:
            return False
        thumb_key, medium_key = preview_keys_for(job.object_key)
        try:
            original = self._storage.get_bytes(job.object_key)
            thumb, medium = self._generate(original)
            self._storage.put_bytes(thumb_key, thumb, "image/webp")
            self._storage.put_bytes(medium_key, medium, "image/webp")
            if job.attachment_id is not None:
                repo = self._attachments_for(job.tenant_slug)
                anexo = await repo.get(job.attachment_id)
                if anexo is not None:
                    anexo.preview_key = thumb_key
                    anexo.preview_medium_key = medium_key
                    anexo.preview_status = PreviewStatus.PRONTO
                    await repo.update(anexo)
            elif job.product_id is not None:
                photos = self._photos_for(job.tenant_slug)
                atual = await photos.get_photo(job.product_id)
                if atual is not None:
                    await photos.set_photo(job.product_id, atual[0], thumb_key)
            await self._jobs.mark_done(job.id)
        except Exception as exc:  # noqa: BLE001 - qualquer falha reagenda o job
            tentativas = job.attempts + 1
            esgotou = tentativas >= MAX_PREVIEW_ATTEMPTS
            await self._jobs.mark_failed(
                job.id,
                f"{type(exc).__name__}: {exc}",
                now + next_backoff(tentativas),
                exhausted=esgotou,
            )
            if esgotou and job.attachment_id is not None:
                repo = self._attachments_for(job.tenant_slug)
                anexo = await repo.get(job.attachment_id)
                if anexo is not None:
                    anexo.preview_status = PreviewStatus.FALHOU
                    await repo.update(anexo)
        return True
```

- [ ] **Step 7: Rodar e ver passar**

Run: `uv run pytest tests/unit/infrastructure/test_images.py tests/unit/application/test_previews_use_case.py -v`
Esperado: PASS (7 testes).

- [ ] **Step 8: Verificações completas e commit**

```bash
git add backend/src/sac/infrastructure/images.py backend/src/sac/application/use_cases/previews.py backend/src/sac/application/ports_attachments.py backend/tests/unit/infrastructure/test_images.py backend/tests/unit/application/test_previews_use_case.py
git commit -m "Adiciona geracao de previews com Pillow e use case do worker"
```

---

### Task 7: Use cases de foto do produto e de membros do tenant

**Files:**
- Create: `backend/src/sac/application/use_cases/product_photo.py`
- Create: `backend/src/sac/application/use_cases/members.py`
- Test: `backend/tests/unit/application/test_product_photo_use_cases.py`
- Test: `backend/tests/unit/application/test_members_use_case.py`

**Interfaces:**
- Consumes: `ProductRepository` (`ports_cadastros.py`, tem `get(product_id) -> Product | None`), `ProductPhotoRepository`, `PreviewJobRepository`, `StoragePort`, `TenantMemberDirectory` (Task 4); `build_product_photo_key`, `kind_for`, `validate_size`, `AttachmentKind`, `preview_keys_for` (Task 1); fakes da Task 5 e `InMemoryProductRepository` (`tests/unit/fakes.py`).
- Produces:
  - `PhotoIntentInput(content_type: str, size_bytes: int)` (frozen) e `PhotoIntent(object_key: str, upload_url: str, expires_in: int)` (frozen).
  - `RequestProductPhotoUploadUseCase(products, storage, tenant_slug, ttl_seconds=300, max_bytes=52_428_800).execute(product_id) -> PhotoIntent` — só imagem; PDF/vídeo recusados com `ValidationError`.
  - `ConfirmProductPhotoUseCase(products, photos, jobs, storage, tenant_slug).execute(product_id, object_key) -> None` — valida que a chave pertence ao prefixo do produto, faz HEAD, grava `photo_key` e enfileira o job de preview.
  - `DeleteProductPhotoUseCase(products, photos).execute(product_id) -> None`.
  - `ListTenantMembersUseCase(directory).execute(tenant_slug) -> list[TenantMember]`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/unit/application/test_product_photo_use_cases.py`:

```python
from uuid import uuid4

import pytest

from sac.application.use_cases.product_photo import (
    ConfirmProductPhotoUseCase,
    DeleteProductPhotoUseCase,
    PhotoIntentInput,
    RequestProductPhotoUploadUseCase,
)
from sac.domain.attachments import preview_keys_for
from sac.domain.cadastros import Product
from sac.domain.errors import NotFoundError, ValidationError
from tests.unit.fakes import InMemoryProductRepository
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryPreviewJobRepository,
    InMemoryProductPhotoRepository,
)

SLUG = "acme"


class Env:
    def __init__(self) -> None:
        self.products = InMemoryProductRepository()
        self.photos = InMemoryProductPhotoRepository()
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()

    async def produto(self) -> Product:
        produto = Product(id=uuid4(), name="Alicate", sku=f"SKU-{uuid4().hex[:6]}")
        await self.products.add(produto)
        return produto

    def request_uc(self) -> RequestProductPhotoUploadUseCase:
        return RequestProductPhotoUploadUseCase(
            self.products, self.storage, tenant_slug=SLUG
        )

    def confirm_uc(self) -> ConfirmProductPhotoUseCase:
        return ConfirmProductPhotoUseCase(
            self.products, self.photos, self.jobs, self.storage, tenant_slug=SLUG
        )


async def test_intencao_gera_chave_no_prefixo_do_produto() -> None:
    env = Env()
    produto = await env.produto()
    intent = await env.request_uc().execute(
        produto.id, PhotoIntentInput(content_type="image/png", size_bytes=5000)
    )
    assert intent.object_key.startswith(f"{SLUG}/catalogo/produtos/{produto.id}/")
    assert intent.object_key.endswith(".png")
    assert intent.upload_url == f"https://fake/put/{intent.object_key}"


async def test_intencao_recusa_nao_imagem_e_produto_inexistente() -> None:
    env = Env()
    produto = await env.produto()
    uc = env.request_uc()
    for mime in ("application/pdf", "video/mp4"):
        with pytest.raises(ValidationError):
            await uc.execute(produto.id, PhotoIntentInput(mime, 1000))
    with pytest.raises(NotFoundError):
        await uc.execute(uuid4(), PhotoIntentInput("image/png", 1000))


async def test_confirmacao_grava_chave_e_enfileira_preview() -> None:
    env = Env()
    produto = await env.produto()
    intent = await env.request_uc().execute(
        produto.id, PhotoIntentInput("image/png", 100)
    )
    env.storage.simulate_upload(intent.object_key, b"x" * 100, "image/png")

    await env.confirm_uc().execute(produto.id, intent.object_key)
    assert await env.photos.get_photo(produto.id) == (intent.object_key, None)
    assert len(env.jobs.items) == 1
    job = next(iter(env.jobs.items.values()))
    assert job.product_id == produto.id
    assert job.attachment_id is None
    assert job.object_key == intent.object_key


async def test_confirmacao_recusa_chave_de_outro_produto_ou_sem_objeto() -> None:
    env = Env()
    produto = await env.produto()
    outro = await env.produto()
    intent = await env.request_uc().execute(
        outro.id, PhotoIntentInput("image/png", 100)
    )
    env.storage.simulate_upload(intent.object_key, b"x" * 100, "image/png")

    with pytest.raises(ValidationError) as exc:
        await env.confirm_uc().execute(produto.id, intent.object_key)
    assert exc.value.details == {"field": "object_key"}

    valida = await env.request_uc().execute(produto.id, PhotoIntentInput("image/png", 100))
    with pytest.raises(ValidationError):
        await env.confirm_uc().execute(produto.id, valida.object_key)


async def test_exclusao_limpa_as_duas_chaves() -> None:
    env = Env()
    produto = await env.produto()
    thumb, _ = preview_keys_for(f"{SLUG}/catalogo/produtos/{produto.id}/x.png")
    await env.photos.set_photo(produto.id, "chave.png", thumb)

    await DeleteProductPhotoUseCase(env.products, env.photos).execute(produto.id)
    assert await env.photos.get_photo(produto.id) == (None, None)

    with pytest.raises(NotFoundError):
        await DeleteProductPhotoUseCase(env.products, env.photos).execute(uuid4())
```

`backend/tests/unit/application/test_members_use_case.py`:

```python
from uuid import uuid4

from sac.application.ports_attachments import TenantMember
from sac.application.use_cases.members import ListTenantMembersUseCase
from sac.domain.permissions import Role
from tests.unit.fakes_attachments import InMemoryTenantMemberDirectory


async def test_lista_membros_do_tenant_do_token() -> None:
    ana = TenantMember(id=uuid4(), name="Ana", role=Role.ADMIN, active=True)
    bruno = TenantMember(id=uuid4(), name="Bruno", role=Role.ATENDENTE, active=True)
    de_outro = TenantMember(id=uuid4(), name="Carlos", role=Role.ADMIN, active=True)
    directory = InMemoryTenantMemberDirectory({"acme": [ana, bruno], "outro": [de_outro]})

    membros = await ListTenantMembersUseCase(directory).execute("acme")
    assert [m.name for m in membros] == ["Ana", "Bruno"]
    assert await ListTenantMembersUseCase(directory).execute("inexistente") == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/application/test_product_photo_use_cases.py tests/unit/application/test_members_use_case.py -v`
Esperado: FAIL (módulos inexistentes).

- [ ] **Step 3: Implementar**

`backend/src/sac/application/use_cases/product_photo.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sac.application.ports_attachments import (
    PreviewJobRepository,
    ProductPhotoRepository,
    StoragePort,
)
from sac.application.ports_cadastros import ProductRepository
from sac.domain.attachments import (
    AttachmentKind,
    PreviewJob,
    PreviewJobStatus,
    build_product_photo_key,
    kind_for,
    validate_size,
)
from sac.domain.errors import NotFoundError, ValidationError


@dataclass(frozen=True)
class PhotoIntentInput:
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class PhotoIntent:
    object_key: str
    upload_url: str
    expires_in: int


def _prefix_for(tenant_slug: str, product_id: UUID) -> str:
    return f"{tenant_slug}/catalogo/produtos/{product_id}/"


class RequestProductPhotoUploadUseCase:
    def __init__(
        self,
        products: ProductRepository,
        storage: StoragePort,
        tenant_slug: str,
        ttl_seconds: int = 300,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._products = products
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._ttl = ttl_seconds
        self._max_bytes = max_bytes

    async def execute(self, product_id: UUID, data: PhotoIntentInput) -> PhotoIntent:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        if kind_for(data.content_type) is not AttachmentKind.IMAGEM:
            raise ValidationError(
                "foto de catalogo aceita apenas imagem", details={"field": "content_type"}
            )
        validate_size(data.size_bytes)
        object_key = build_product_photo_key(
            self._tenant_slug, product_id, data.content_type, uuid4()
        )
        return PhotoIntent(
            object_key=object_key,
            upload_url=self._storage.presigned_put(
                object_key, data.content_type, self._max_bytes, self._ttl
            ),
            expires_in=self._ttl,
        )


class ConfirmProductPhotoUseCase:
    def __init__(
        self,
        products: ProductRepository,
        photos: ProductPhotoRepository,
        jobs: PreviewJobRepository,
        storage: StoragePort,
        tenant_slug: str,
        max_bytes: int = 52_428_800,
    ) -> None:
        self._products = products
        self._photos = photos
        self._jobs = jobs
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._max_bytes = max_bytes

    async def execute(self, product_id: UUID, object_key: str) -> None:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        # a chave vem do client, entao precisa pertencer ao prefixo deste produto
        if not object_key.startswith(_prefix_for(self._tenant_slug, product_id)):
            raise ValidationError(
                "chave de objeto nao pertence a este produto",
                details={"field": "object_key"},
            )
        head = self._storage.head(object_key)
        if head is None:
            raise ValidationError(
                "objeto nao encontrado no storage", details={"field": "object_key"}
            )
        if kind_for(head.content_type) is not AttachmentKind.IMAGEM:
            raise ValidationError(
                "objeto nao e imagem", details={"field": "content_type"}
            )
        if head.size_bytes < 1 or head.size_bytes > self._max_bytes:
            raise ValidationError(
                "tamanho real do objeto invalido", details={"field": "size_bytes"}
            )
        await self._photos.set_photo(product_id, object_key, None)
        await self._jobs.add(
            PreviewJob(
                id=uuid4(),
                tenant_slug=self._tenant_slug,
                object_key=object_key,
                kind=AttachmentKind.IMAGEM,
                status=PreviewJobStatus.PENDENTE,
                attempts=0,
                next_attempt_at=datetime.now(UTC),
                product_id=product_id,
            )
        )


class DeleteProductPhotoUseCase:
    def __init__(
        self, products: ProductRepository, photos: ProductPhotoRepository
    ) -> None:
        self._products = products
        self._photos = photos

    async def execute(self, product_id: UUID) -> None:
        if await self._products.get(product_id) is None:
            raise NotFoundError("produto nao encontrado")
        await self._photos.set_photo(product_id, None, None)
```

`backend/src/sac/application/use_cases/members.py`:

```python
from sac.application.ports_attachments import TenantMember, TenantMemberDirectory


class ListTenantMembersUseCase:
    def __init__(self, directory: TenantMemberDirectory) -> None:
        self._directory = directory

    async def execute(self, tenant_slug: str) -> list[TenantMember]:
        return await self._directory.list_members(tenant_slug)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/application -v`
Esperado: PASS.

- [ ] **Step 5: Verificações completas e commit**

```bash
git add backend/src/sac/application/use_cases/product_photo.py backend/src/sac/application/use_cases/members.py backend/tests/unit/application/test_product_photo_use_cases.py backend/tests/unit/application/test_members_use_case.py
git commit -m "Adiciona use cases de foto do produto e de membros do tenant"
```

---

### Task 8: Worker de previews (processo e serviço do compose)

**Files:**
- Create: `backend/src/sac/infrastructure/worker.py`
- Modify: `docker-compose.yml`
- Modify: `dev.ps1` (se a Task 2 deixou o serviço `worker` de fora)
- Test: `backend/tests/integration/test_worker.py`

**Interfaces:**
- Consumes: `ProcessPreviewJobUseCase` (Task 6), `build_storage` (Task 2), `SqlPreviewJobRepository`/`SqlAttachmentRepository`/`SqlProductPhotoRepository` (Task 4), `generate_previews` (Task 6), `build_engine` (`infrastructure/db.py`), `ExpirePendingUseCase` (Task 5), `Settings`.
- Produces:
  - `async def run_once(engine: AsyncEngine, storage: StoragePort, settings: Settings) -> bool` — processa no máximo um job (a sessão é aberta com `schema_translate_map` do tenant do próximo job, para que a atualização da tabela do tenant e a baixa do job caiam na MESMA transação).
  - `async def run_forever(engine, storage, settings, interval_seconds: float = 2.0) -> None`.
  - `def main() -> None` — entrada de `python -m sac.worker`; aceita `--once`.
  - `backend/src/sac/worker.py` (módulo fino que chama `sac.infrastructure.worker.main`) para o comando `python -m sac.worker` funcionar.

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_worker.py`:

```python
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_attachments import ObjectHead
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from sac.infrastructure.models_tenant import BrandModel, TicketModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    build_attachment_repos,
)
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.infrastructure.worker import run_once
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _png(width: int = 1000, height: int = 500) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket_id(ts: AsyncSession, attendant: UUID) -> UUID:
    brand_id = (await ts.scalars(select(BrandModel.id))).first()
    assert brand_id is not None
    ticket = TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=attendant,
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    ts.add(ticket)
    await ts.flush()
    return ticket.id


async def test_worker_gera_os_dois_previews_e_marca_pronto(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="workerok")
    user = await seed_user(session, email="worker@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        chave = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="foto.png",
            content_type="image/png",
            size_bytes=len(_png()),
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
            confirmed_at=datetime.now(UTC),
        )
        await repos.attachments.add(anexo)
        await ts.commit()

    storage.put_bytes(chave, _png(), "image/png")
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=uuid4(),
            tenant_slug=tenant.slug,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=anexo.id,
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    thumb_key, medium_key = preview_keys_for(chave)
    head_thumb = storage.head(thumb_key)
    head_medium = storage.head(medium_key)
    assert isinstance(head_thumb, ObjectHead) and head_thumb.content_type == "image/webp"
    assert isinstance(head_medium, ObjectHead)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        atualizado = await repos.attachments.get(anexo.id)
        assert atualizado is not None
        assert atualizado.preview_status is PreviewStatus.PRONTO
        assert atualizado.preview_key == thumb_key
        assert atualizado.preview_medium_key == medium_key


async def test_worker_sem_job_devolve_false(
    engine: AsyncEngine, storage: S3Storage, storage_settings: Settings
) -> None:
    assert await run_once(engine, storage, storage_settings) is False


async def test_job_de_objeto_inexistente_reagenda(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="workerfail")
    job_id = uuid4()
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=job_id,
            tenant_slug=tenant.slug,
            object_key=f"{tenant.slug}/inexistente/x.png",
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=uuid4(),
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    relido = await SqlPreviewJobRepository(session).get(job_id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.PENDENTE
    assert relido.attempts == 1
    assert relido.next_attempt_at > datetime.now(UTC)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_worker.py -v`
Esperado: FAIL (módulo `sac.infrastructure.worker` inexistente).

- [ ] **Step 3: Implementar o worker**

`backend/src/sac/infrastructure/worker.py`:

```python
import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from sac.application.ports_attachments import StoragePort
from sac.application.use_cases.attachments import ExpirePendingUseCase
from sac.application.use_cases.previews import ProcessPreviewJobUseCase
from sac.domain.attachments import PreviewJobStatus
from sac.infrastructure.db import build_engine
from sac.infrastructure.images import generate_previews
from sac.infrastructure.models import PreviewJobModel
from sac.infrastructure.repositories_attachments import build_attachment_repos
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import build_storage


async def _next_tenant_slug(engine: AsyncEngine, now: datetime) -> str | None:
    """Descobre de qual tenant e o proximo job, para abrir UMA sessao capaz de
    escrever tanto em preview_jobs (schema publico) quanto nas tabelas do tenant.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return await session.scalar(
            select(PreviewJobModel.tenant_slug)
            .where(
                PreviewJobModel.status == str(PreviewJobStatus.PENDENTE),
                PreviewJobModel.next_attempt_at <= now,
            )
            .order_by(PreviewJobModel.next_attempt_at)
            .limit(1)
        )


async def run_once(engine: AsyncEngine, storage: StoragePort, settings: Settings) -> bool:
    now = datetime.now(UTC)
    slug = await _next_tenant_slug(engine, now)
    if slug is None:
        return False
    translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        repos = build_attachment_repos(session)
        use_case = ProcessPreviewJobUseCase(
            jobs=repos.jobs,
            storage=storage,
            generate=generate_previews,
            attachments_for=lambda _slug: repos.attachments,
            photos_for=lambda _slug: repos.photos,
        )
        try:
            processou = await use_case.execute(now)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return processou


async def _expire_pending(engine: AsyncEngine, slug: str, minutes: int) -> None:
    translated = engine.execution_options(schema_translate_map={"tenant": f"t_{slug}"})
    factory = async_sessionmaker(translated, expire_on_commit=False)
    async with factory() as session:
        repos = build_attachment_repos(session)
        await ExpirePendingUseCase(repos.attachments, minutes=minutes).execute()
        await session.commit()


async def _active_tenant_slugs(engine: AsyncEngine) -> list[str]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        rows = await session.scalars(
            select(TenantModel.slug).where(TenantModel.status != "inativa")
        )
        return list(rows)


async def expire_pending_all(engine: AsyncEngine, minutes: int) -> None:
    for slug in await _active_tenant_slugs(engine):
        await _expire_pending(engine, slug, minutes)


async def run_forever(
    engine: AsyncEngine,
    storage: StoragePort,
    settings: Settings,
    interval_seconds: float = 2.0,
    expire_every_seconds: float = 300.0,
) -> None:
    proxima_expiracao = 0.0
    while True:
        agora = asyncio.get_running_loop().time()
        if agora >= proxima_expiracao:
            await expire_pending_all(engine, settings.pending_expiration_minutes)
            proxima_expiracao = agora + expire_every_seconds
        processou = await run_once(engine, storage, settings)
        if not processou:
            await asyncio.sleep(interval_seconds)


async def _main_async(once: bool) -> None:
    settings = Settings()
    engine = build_engine(settings.database_url)
    storage = build_storage(settings)
    try:
        if once:
            await run_once(engine, storage, settings)
        else:
            await run_forever(engine, storage, settings)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sac-worker")
    parser.add_argument("--once", action="store_true", help="processa um job e sai")
    args = parser.parse_args()
    asyncio.run(_main_async(args.once))


if __name__ == "__main__":
    main()
```

`backend/src/sac/worker.py` (para `python -m sac.worker`):

```python
from sac.infrastructure.worker import main

if __name__ == "__main__":
    main()
```

Imports adicionais no worker: `TenantModel` (`sac.infrastructure.models`). A varredura de pendentes roda a cada 5 minutos sobre os tenants não inativos (é o que o spec pede) e reaproveita `_expire_pending`, que abre uma sessão traduzida por tenant.

Acrescente também este teste ao `test_worker.py`, cobrindo a varredura:

```python
async def test_expiracao_de_pendentes_varre_os_tenants(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    from sqlalchemy import text

    from sac.infrastructure.worker import expire_pending_all

    tenant = await seed_provisioned_tenant(session, engine, slug="workerexp")
    user = await seed_user(session, email="workerexp@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="pendente.png",
            content_type="image/png",
            size_bytes=10,
            object_key=f"{tenant.slug}/{ticket_id}/{uuid4()}.png",
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.PENDENTE,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
        )
        await repos.attachments.add(anexo)
        await ts.execute(
            text(
                f'UPDATE "{tenant.schema_name}".ticket_attachments '
                "SET created_at = now() - interval '2 hours'"
            )
        )
        await ts.commit()

    await expire_pending_all(engine, minutes=30)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        relido = await repos.attachments.get(anexo.id)
        assert relido is not None
        assert relido.status is AttachmentStatus.EXPIRADO
```

- [ ] **Step 4: Serviço no compose**

Em `docker-compose.yml`, acrescentar após o serviço `backend`:

```yaml
  worker:
    build: ./backend
    command: uv run python -m sac.worker
    depends_on:
      db:
        condition: service_healthy
      minio:
        condition: service_healthy
    environment:
      SAC_DATABASE_URL: postgresql+asyncpg://sac:sac@db:5432/sac
      SAC_S3_ENDPOINT_URL: http://minio:9000
      SAC_S3_PUBLIC_ENDPOINT_URL: http://localhost:9000
      SAC_S3_BUCKET: sac-dev
      SAC_S3_ACCESS_KEY: sacminio
      SAC_S3_SECRET_KEY: sacminio123
    volumes:
      - ./backend:/app
      - backend_venv:/app/.venv
```

Confirme que `dev.ps1` sobe `worker` (a Task 2 pode ter deixado de fora).

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_worker.py -v`
Esperado: PASS (3 testes).

- [ ] **Step 6: Verificações completas e commit**

```bash
git add backend/src/sac/infrastructure/worker.py backend/src/sac/worker.py docker-compose.yml dev.ps1 backend/tests/integration/test_worker.py
git commit -m "Adiciona worker de previews com fila em tabela e servico no compose"
```

---

### Task 9: API de anexos do ticket

**Files:**
- Modify: `backend/src/sac/interface/schemas.py`
- Modify: `backend/src/sac/interface/deps.py`
- Modify: `backend/src/sac/interface/app.py`
- Modify: `backend/src/sac/interface/routers/tickets.py`
- Test: `backend/tests/integration/test_attachments_api.py`

**Interfaces:**
- Consumes: use cases da Task 5; `AttachmentRepos`/`build_attachment_repos` (Task 4); `build_storage` (Task 2); `get_tenant_session`, `get_ticket_repos`, `require_permission`, `require_any_permission`, `_actor`, `_read` (padrões da Fase 2A); `Settings`.
- Produces:
  - Schemas: `AttachmentIntentIn(filename: str (max 255), content_type: str (max 100), size_bytes: int (gt=0), with_preview: bool = False)`, `AttachmentIntentOut(attachment_id: UUID, object_key: str, upload_url: str, expires_in: int, preview_upload_url: str | None)`, `AttachmentOut(id, filename, content_type, size_bytes, kind, preview_status, preview_url, author_user_id, author_name, created_at)`, `AttachmentUrlOut(url: str, expires_in: int)`; builder `attachment_out(view: AttachmentView, author_name: str | None) -> AttachmentOut`.
  - Deps: `get_storage(request: Request) -> S3Storage` (lê `request.app.state.storage`), `get_attachment_repos(session=Depends(get_tenant_session)) -> AttachmentRepos`, `get_tenant_slug(identity=Depends(get_current_identity)) -> str` (levanta `AuthError` se ausente).
  - `create_app` passa a guardar `app.state.storage = build_storage(settings)`.
  - Rotas: `POST /api/tickets/{id}/anexos/intencao` (201), `POST /api/tickets/{id}/anexos/{anexo_id}/confirmar` (200), `GET /api/tickets/{id}/anexos` (200), `GET /api/tickets/{id}/anexos/{anexo_id}/url` (200), `DELETE /api/tickets/{id}/anexos/{anexo_id}` (204).

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/integration/test_attachments_api.py`:

```python
import io

import httpx
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


def _png(width: int = 800, height: int = 400) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 140, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Alice Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, admin, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def _ticket(client: AsyncClient, headers: dict[str, str]) -> str:
    marcas = (await client.get("/api/cadastros/marcas", headers=headers)).json()
    res = await client.post(
        "/api/tickets",
        json={"brand_id": marcas[0]["id"], "priority": "media"},
        headers=headers,
    )
    assert res.status_code == 201
    return str(res.json()["id"])


async def test_ciclo_completo_de_anexo(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi1")
    ticket_id = await _ticket(client, headers)
    imagem = _png()

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={
            "filename": "foto do defeito.png",
            "content_type": "image/png",
            "size_bytes": len(imagem),
        },
        headers=headers,
    )
    assert res.status_code == 201
    intencao = res.json()
    assert intencao["object_key"].endswith(".png")
    assert "foto do defeito" not in intencao["object_key"]
    # isolamento por tenant: a chave nasce sob o slug do token, nunca de outro tenant
    assert intencao["object_key"].startswith("anexapi1/")
    assert intencao["preview_upload_url"] is None

    # o navegador sobe direto no storage
    async with httpx.AsyncClient() as direto:
        put = await direto.put(
            intencao["upload_url"], content=imagem, headers={"Content-Type": "image/png"}
        )
    assert put.status_code == 200

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
        headers=headers,
    )
    assert res.status_code == 200
    anexo = res.json()
    assert anexo["preview_status"] == "pendente"
    assert anexo["size_bytes"] == len(imagem)
    assert anexo["author_name"] == "Alice Admin"

    listados = (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json()
    assert len(listados) == 1
    assert listados[0]["preview_url"] is None

    url = (
        await client.get(
            f"/api/tickets/{ticket_id}/anexos/{anexo['id']}/url?variante=original",
            headers=headers,
        )
    ).json()
    async with httpx.AsyncClient() as direto:
        baixado = await direto.get(url["url"])
    assert baixado.status_code == 200
    assert baixado.content == imagem

    res = await client.delete(
        f"/api/tickets/{ticket_id}/anexos/{anexo['id']}", headers=headers
    )
    assert res.status_code == 204
    assert (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json() == []


async def test_confirmacao_sem_upload_da_422(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi2")
    ticket_id = await _ticket(client, headers)
    intencao = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
    ).json()
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "object_key"


async def test_tipo_e_tamanho_recusados(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi3")
    ticket_id = await _ticket(client, headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.gif", "content_type": "image/gif", "size_bytes": 100},
        headers=headers,
    )
    assert res.status_code == 422
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 52428801},
        headers=headers,
    )
    assert res.status_code == 422


async def test_cota_de_dez_anexos(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi4")
    ticket_id = await _ticket(client, headers)
    for _ in range(10):
        res = await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
        assert res.status_code == 201
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 100},
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["details"]["limite"] == 10


async def test_video_recebe_duas_urls_e_thumb_do_navegador(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, _, headers = await _setup(session, engine, "anexapi5")
    ticket_id = await _ticket(client, headers)
    intencao = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/intencao",
            json={
                "filename": "clipe.mp4",
                "content_type": "video/mp4",
                "size_bytes": 12,
                "with_preview": True,
            },
            headers=headers,
        )
    ).json()
    assert intencao["preview_upload_url"] is not None

    async with httpx.AsyncClient() as direto:
        await direto.put(
            intencao["upload_url"],
            content=b"conteudo-mp4",
            headers={"Content-Type": "video/mp4"},
        )
        await direto.put(
            intencao["preview_upload_url"],
            content=_png(100, 100),
            headers={"Content-Type": "image/webp"},
        )

    anexo = (
        await client.post(
            f"/api/tickets/{ticket_id}/anexos/{intencao['attachment_id']}/confirmar",
            headers=headers,
        )
    ).json()
    assert anexo["kind"] == "video"
    assert anexo["preview_status"] == "pronto"
    listados = (await client.get(f"/api/tickets/{ticket_id}/anexos", headers=headers)).json()
    assert listados[0]["preview_url"] is not None


async def test_visualizador_le_mas_nao_anexa_e_ticket_encerrado_bloqueia(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, _, headers = await _setup(session, engine, "anexapi6")
    viewer = await seed_user(session, email="viewer@anexapi6.com", name="Carla")
    await seed_link(session, user=viewer, tenant=tenant, role=Role.VISUALIZADOR)
    viewer_headers = token_for(viewer, tenant_slug=tenant.slug, role=Role.VISUALIZADOR)
    ticket_id = await _ticket(client, headers)

    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 10},
        headers=viewer_headers,
    )
    assert res.status_code == 403
    assert (
        await client.get(f"/api/tickets/{ticket_id}/anexos", headers=viewer_headers)
    ).status_code == 200

    await client.post(f"/api/tickets/{ticket_id}/cancelar", json={}, headers=headers)
    res = await client.post(
        f"/api/tickets/{ticket_id}/anexos/intencao",
        json={"filename": "x.png", "content_type": "image/png", "size_bytes": 10},
        headers=headers,
    )
    assert res.status_code == 409
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_attachments_api.py -v`
Esperado: FAIL (rotas 404).

- [ ] **Step 3: Schemas**

Acrescentar em `backend/src/sac/interface/schemas.py`:

```python
class AttachmentIntentIn(BaseModel):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    with_preview: bool = False


class AttachmentIntentOut(BaseModel):
    attachment_id: UUID
    object_key: str
    upload_url: str
    expires_in: int
    preview_upload_url: str | None


class AttachmentOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    kind: AttachmentKind
    preview_status: PreviewStatus
    preview_url: str | None
    author_user_id: UUID
    author_name: str | None
    created_at: datetime | None


class AttachmentUrlOut(BaseModel):
    url: str
    expires_in: int


def attachment_out(view: AttachmentView, author_name: str | None) -> AttachmentOut:
    a = view.attachment
    return AttachmentOut(
        id=a.id,
        filename=a.filename,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        kind=a.kind,
        preview_status=a.preview_status,
        preview_url=view.preview_url,
        author_user_id=a.author_user_id,
        author_name=author_name,
        created_at=a.created_at,
    )
```

Imports novos: `AttachmentKind`, `PreviewStatus` (`sac.domain.attachments`), `AttachmentView` (`sac.application.use_cases.attachments`), `TicketAttachment` se necessário.

- [ ] **Step 4: Deps e app**

Em `backend/src/sac/interface/deps.py`:

```python
def get_storage(request: Request) -> S3Storage:
    storage: S3Storage = request.app.state.storage
    return storage


def get_attachment_repos(
    session: AsyncSession = Depends(get_tenant_session),
) -> AttachmentRepos:
    return build_attachment_repos(session)


def get_member_directory(
    session: AsyncSession = Depends(get_session),
) -> SqlTenantMemberDirectory:
    return SqlTenantMemberDirectory(session)


async def get_tenant_slug(identity: TokenPayload = Depends(get_current_identity)) -> str:
    if identity.tenant_slug is None:
        raise AuthError("token sem tenant")
    return identity.tenant_slug
```

Imports: `S3Storage`, `build_storage` (`infrastructure/storage.py`), `AttachmentRepos`, `build_attachment_repos`, `SqlTenantMemberDirectory` (`infrastructure/repositories_attachments.py`).

Em `backend/src/sac/interface/app.py`, dentro de `create_app`, após `app.state.session_factory = ...`:

```python
    app.state.storage = build_storage(settings)
```

- [ ] **Step 5: Rotas**

Acrescentar em `backend/src/sac/interface/routers/tickets.py` (imports dos use cases e schemas novos; `_attach = require_permission(Permission.COMENTAR_ANEXAR)`):

```python
@router.post(
    "/{ticket_id}/anexos/intencao", response_model=AttachmentIntentOut, status_code=201
)
async def request_attachment_upload(
    ticket_id: UUID,
    body: AttachmentIntentIn,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> AttachmentIntentOut:
    use_case = RequestUploadUseCase(
        repos.tickets,
        anexos.attachments,
        storage,
        tenant_slug=tenant_slug,
        ttl_seconds=settings.presigned_ttl_seconds,
        max_per_ticket=settings.attachment_max_per_ticket,
        max_bytes=settings.attachment_max_bytes,
    )
    intent = await use_case.execute(
        _actor(identity),
        ticket_id,
        UploadIntentInput(
            filename=body.filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            with_preview=body.with_preview,
        ),
    )
    return AttachmentIntentOut(
        attachment_id=intent.attachment_id,
        object_key=intent.object_key,
        upload_url=intent.upload_url,
        expires_in=intent.expires_in,
        preview_upload_url=intent.preview_upload_url,
    )


@router.post("/{ticket_id}/anexos/{anexo_id}/confirmar", response_model=AttachmentOut)
async def confirm_attachment_upload(
    ticket_id: UUID,
    anexo_id: UUID,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> AttachmentOut:
    use_case = ConfirmUploadUseCase(
        repos.tickets,
        anexos.attachments,
        anexos.jobs,
        storage,
        tenant_slug=tenant_slug,
        max_bytes=settings.attachment_max_bytes,
    )
    anexo = await use_case.execute(_actor(identity), ticket_id, anexo_id)
    nomes = await repos.users.names_by_ids({anexo.author_user_id})
    view = AttachmentView(
        attachment=anexo,
        preview_url=(
            storage.presigned_get(anexo.preview_key, settings.presigned_ttl_seconds)
            if anexo.preview_status is PreviewStatus.PRONTO and anexo.preview_key
            else None
        ),
    )
    return attachment_out(view, nomes.get(anexo.author_user_id))


@router.get("/{ticket_id}/anexos", response_model=list[AttachmentOut])
async def list_attachments(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> list[AttachmentOut]:
    vistas = await ListAttachmentsUseCase(
        repos.tickets, anexos.attachments, storage, settings.presigned_ttl_seconds
    ).execute(_actor(identity), ticket_id)
    nomes = await repos.users.names_by_ids({v.attachment.author_user_id for v in vistas})
    return [attachment_out(v, nomes.get(v.attachment.author_user_id)) for v in vistas]


@router.get("/{ticket_id}/anexos/{anexo_id}/url", response_model=AttachmentUrlOut)
async def get_attachment_url(
    ticket_id: UUID,
    anexo_id: UUID,
    variante: str = "medio",
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> AttachmentUrlOut:
    url = await GetAttachmentUrlUseCase(
        repos.tickets, anexos.attachments, storage, settings.presigned_ttl_seconds
    ).execute(_actor(identity), ticket_id, anexo_id, variante)
    return AttachmentUrlOut(url=url, expires_in=settings.presigned_ttl_seconds)


@router.delete("/{ticket_id}/anexos/{anexo_id}", status_code=204)
async def delete_attachment(
    ticket_id: UUID,
    anexo_id: UUID,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
) -> Response:
    await DeleteAttachmentUseCase(repos.tickets, anexos.attachments).execute(
        _actor(identity), ticket_id, anexo_id
    )
    return Response(status_code=204)
```

Atenção: as rotas de anexo precisam ser declaradas ANTES de qualquer rota `"/{ticket_id}/{algo}"` genérica, se houver. Hoje o router só tem caminhos literais, então basta acrescentar ao final.

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_attachments_api.py -v`
Esperado: PASS (6 testes). O `client` de teste usa `create_app(Settings(database_url=...))`, que lê as variáveis de S3 do ambiente — exporte `SAC_S3_BUCKET` igual ao bucket da fixture ou ajuste a fixture `app` para receber `storage_settings`; faça o ajuste na fixture `app` do conftest (`create_app(Settings(database_url=database, s3_bucket=storage_settings.s3_bucket, s3_public_endpoint_url="http://127.0.0.1:9000"))`) e declare a dependência da fixture.

- [ ] **Step 7: Verificações completas e commit**

```bash
git add backend/src/sac/interface/schemas.py backend/src/sac/interface/deps.py backend/src/sac/interface/app.py backend/src/sac/interface/routers/tickets.py backend/tests/integration/conftest.py backend/tests/integration/test_attachments_api.py
git commit -m "Adiciona rotas de anexo do ticket com presigned URL e confirmacao"
```

---

### Task 10: API de foto do produto e de membros do tenant

**Files:**
- Modify: `backend/src/sac/interface/schemas.py`
- Modify: `backend/src/sac/interface/routers/cadastros_products.py`
- Create: `backend/src/sac/interface/routers/members.py`
- Modify: `backend/src/sac/interface/app.py`
- Test: `backend/tests/integration/test_product_photo_api.py`
- Test: `backend/tests/integration/test_members_api.py`

**Interfaces:**
- Consumes: use cases da Task 7; deps da Task 9; `get_product_repository`, `require_permission` (existentes).
- Produces:
  - Schemas: `PhotoIntentIn(content_type: str (max 100), size_bytes: int (gt=0))`, `PhotoIntentOut(object_key: str, upload_url: str, expires_in: int)`, `PhotoConfirmIn(object_key: str (max 400))`, `MemberOut(id: UUID, name: str, role: Role, active: bool)`.
  - `ProductOut` ganha `photo_preview_key: str | None` e `photo_url: str | None`; `product_out(product, photo_url=None)` passa a aceitar a URL opcional (assinatura nova: `product_out(product: Product, photo_url: str | None = None) -> ProductOut`).
  - Rotas: `POST /api/cadastros/produtos/{id}/foto/intencao` (201), `POST /api/cadastros/produtos/{id}/foto/confirmar` (204), `DELETE /api/cadastros/produtos/{id}/foto` (204), `GET /api/membros` (200, `list[MemberOut]`).

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/integration/test_product_photo_api.py`:

```python
import io

import httpx
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.domain.permissions import Role
from tests.integration.helpers import (
    seed_link,
    seed_provisioned_tenant,
    seed_user,
    token_for,
)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), color=(220, 90, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _setup(session: AsyncSession, engine: AsyncEngine, slug: str):
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    admin = await seed_user(session, email=f"admin@{slug}.com", name="Admin")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    return tenant, token_for(admin, tenant_slug=tenant.slug, role=Role.ADMIN)


async def test_foto_do_produto_da_intencao_ao_get(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, headers = await _setup(session, engine, "fotoapi1")
    produto = (
        await client.post(
            "/api/cadastros/produtos",
            json={"name": "Alicate com foto", "sku": "AF-1"},
            headers=headers,
        )
    ).json()
    imagem = _png()

    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/intencao",
        json={"content_type": "image/png", "size_bytes": len(imagem)},
        headers=headers,
    )
    assert res.status_code == 201
    intencao = res.json()
    assert f"catalogo/produtos/{produto['id']}/" in intencao["object_key"]

    async with httpx.AsyncClient() as direto:
        put = await direto.put(
            intencao["upload_url"], content=imagem, headers={"Content-Type": "image/png"}
        )
    assert put.status_code == 200

    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/confirmar",
        json={"object_key": intencao["object_key"]},
        headers=headers,
    )
    assert res.status_code == 204

    listagem = (await client.get("/api/cadastros/produtos", headers=headers)).json()
    alvo = next(p for p in listagem["items"] if p["id"] == produto["id"])
    assert alvo["photo_key"] == intencao["object_key"]

    res = await client.delete(
        f"/api/cadastros/produtos/{produto['id']}/foto", headers=headers
    )
    assert res.status_code == 204
    listagem = (await client.get("/api/cadastros/produtos", headers=headers)).json()
    alvo = next(p for p in listagem["items"] if p["id"] == produto["id"])
    assert alvo["photo_key"] is None
    assert alvo["photo_url"] is None


async def test_chave_de_outro_produto_e_recusada(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    _, headers = await _setup(session, engine, "fotoapi2")
    a = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "A", "sku": "A-1"}, headers=headers
        )
    ).json()
    b = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "B", "sku": "B-1"}, headers=headers
        )
    ).json()
    intencao = (
        await client.post(
            f"/api/cadastros/produtos/{b['id']}/foto/intencao",
            json={"content_type": "image/png", "size_bytes": 100},
            headers=headers,
        )
    ).json()
    res = await client.post(
        f"/api/cadastros/produtos/{a['id']}/foto/confirmar",
        json={"object_key": intencao["object_key"]},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["details"]["field"] == "object_key"


async def test_atendente_nao_gerencia_foto(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant, headers = await _setup(session, engine, "fotoapi3")
    att = await seed_user(session, email="att@fotoapi3.com", name="Bruno")
    await seed_link(session, user=att, tenant=tenant, role=Role.ATENDENTE)
    att_headers = token_for(att, tenant_slug=tenant.slug, role=Role.ATENDENTE)
    produto = (
        await client.post(
            "/api/cadastros/produtos", json={"name": "C", "sku": "C-1"}, headers=headers
        )
    ).json()
    res = await client.post(
        f"/api/cadastros/produtos/{produto['id']}/foto/intencao",
        json={"content_type": "image/png", "size_bytes": 100},
        headers=att_headers,
    )
    assert res.status_code == 403
```

`backend/tests/integration/test_members_api.py`:

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


async def test_membros_do_tenant_para_qualquer_papel(
    client: AsyncClient, session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="membrosapi")
    outro = await seed_provisioned_tenant(session, engine, slug="membrosoutro")
    admin = await seed_user(session, email="admin@membrosapi.com", name="Ana Admin")
    att = await seed_user(session, email="att@membrosapi.com", name="Bruno Atendente")
    fora = await seed_user(session, email="fora@membrosoutro.com", name="Carlos Fora")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=att, tenant=tenant, role=Role.ATENDENTE)
    await seed_link(session, user=fora, tenant=outro, role=Role.ADMIN)

    for user, role in ((admin, Role.ADMIN), (att, Role.ATENDENTE)):
        headers = token_for(user, tenant_slug=tenant.slug, role=role)
        res = await client.get("/api/membros", headers=headers)
        assert res.status_code == 200
        nomes = [m["name"] for m in res.json()]
        assert nomes == ["Ana Admin", "Bruno Atendente"]
        assert "Carlos Fora" not in nomes
        assert all("email" not in m for m in res.json())


async def test_membros_exige_token_de_tenant(client: AsyncClient, session: AsyncSession) -> None:
    assert (await client.get("/api/membros")).status_code == 401
    super_admin = await seed_user(session, email="super@membros.com", is_super_admin=True)
    headers = token_for(super_admin)
    assert (await client.get("/api/membros", headers=headers)).status_code == 401
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_product_photo_api.py tests/integration/test_members_api.py -v`
Esperado: FAIL (rotas 404).

- [ ] **Step 3: Schemas**

Acrescentar em `backend/src/sac/interface/schemas.py` e ajustar `ProductOut`/`product_out`:

```python
class PhotoIntentIn(BaseModel):
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)


class PhotoIntentOut(BaseModel):
    object_key: str
    upload_url: str
    expires_in: int


class PhotoConfirmIn(BaseModel):
    object_key: str = Field(max_length=400)


class MemberOut(BaseModel):
    id: UUID
    name: str
    role: Role
    active: bool
```

Em `ProductOut`, acrescentar `photo_preview_key: str | None` e `photo_url: str | None`; e trocar o builder por:

```python
def product_out(product: Product, photo_url: str | None = None) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        segment=product.segment,
        description=product.description,
        photo_key=product.photo_key,
        photo_preview_key=product.photo_preview_key,
        photo_url=photo_url,
        active=product.active,
    )
```

`Product` (domínio) ganha `photo_preview_key: str | None = None`, e `_product_entity`/`add`/`update` em `repositories_cadastros.py` passam a copiar o campo — sem isso a listagem nunca vê o preview.

- [ ] **Step 4: Rotas de foto**

Acrescentar em `backend/src/sac/interface/routers/cadastros_products.py` (imports dos use cases da Task 7 e das deps da Task 9):

```python
@router.post(
    "/{product_id}/foto/intencao",
    response_model=PhotoIntentOut,
    status_code=201,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def request_photo_upload(
    product_id: UUID,
    body: PhotoIntentIn,
    repo: SqlProductRepository = Depends(get_product_repository),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> PhotoIntentOut:
    intent = await RequestProductPhotoUploadUseCase(
        repo,
        storage,
        tenant_slug=tenant_slug,
        ttl_seconds=settings.presigned_ttl_seconds,
        max_bytes=settings.attachment_max_bytes,
    ).execute(product_id, PhotoIntentInput(body.content_type, body.size_bytes))
    return PhotoIntentOut(
        object_key=intent.object_key,
        upload_url=intent.upload_url,
        expires_in=intent.expires_in,
    )


@router.post(
    "/{product_id}/foto/confirmar",
    status_code=204,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def confirm_photo(
    product_id: UUID,
    body: PhotoConfirmIn,
    repo: SqlProductRepository = Depends(get_product_repository),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> Response:
    await ConfirmProductPhotoUseCase(
        repo,
        anexos.photos,
        anexos.jobs,
        storage,
        tenant_slug=tenant_slug,
        max_bytes=settings.attachment_max_bytes,
    ).execute(product_id, body.object_key)
    return Response(status_code=204)


@router.delete(
    "/{product_id}/foto",
    status_code=204,
    dependencies=[Depends(require_permission(Permission.GERENCIAR_CADASTROS))],
)
async def delete_photo(
    product_id: UUID,
    repo: SqlProductRepository = Depends(get_product_repository),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
) -> Response:
    await DeleteProductPhotoUseCase(repo, anexos.photos).execute(product_id)
    return Response(status_code=204)
```

E em `list_products`, montar a `photo_url` da thumb quando existir:

```python
    items, total = await ListProductsUseCase(repo).execute(search, active, page, per_page)
    return ProductsPageOut(
        items=[
            product_out(
                p,
                storage.presigned_get(p.photo_preview_key, settings.presigned_ttl_seconds)
                if p.photo_preview_key
                else None,
            )
            for p in items
        ],
        total=total,
        page=page,
        per_page=per_page,
    )
```

(acrescente `storage` e `settings` como dependências de `list_products`).

- [ ] **Step 5: Router de membros**

Criar `backend/src/sac/interface/routers/members.py`:

```python
from fastapi import APIRouter, Depends

from sac.application.use_cases.members import ListTenantMembersUseCase
from sac.infrastructure.repositories_attachments import SqlTenantMemberDirectory
from sac.interface.deps import get_member_directory, get_tenant_slug
from sac.interface.schemas import MemberOut

router = APIRouter(prefix="/membros", tags=["membros"])


@router.get("", response_model=list[MemberOut])
async def list_members(
    tenant_slug: str = Depends(get_tenant_slug),
    directory: SqlTenantMemberDirectory = Depends(get_member_directory),
) -> list[MemberOut]:
    membros = await ListTenantMembersUseCase(directory).execute(tenant_slug)
    return [
        MemberOut(id=m.id, name=m.name, role=m.role, active=m.active) for m in membros
    ]
```

Em `backend/src/sac/interface/app.py`: importar `members` e `app.include_router(members.router, prefix="/api")`.

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_product_photo_api.py tests/integration/test_members_api.py tests/integration/test_cadastros_products_api.py -v`
Esperado: PASS (o teste de produtos existente continua verde com os campos novos).

- [ ] **Step 7: Verificações completas e commit**

```bash
git add backend/src/sac/interface/schemas.py backend/src/sac/interface/routers/cadastros_products.py backend/src/sac/interface/routers/members.py backend/src/sac/interface/app.py backend/src/sac/domain/cadastros.py backend/src/sac/infrastructure/repositories_cadastros.py backend/tests/integration/test_product_photo_api.py backend/tests/integration/test_members_api.py
git commit -m "Adiciona rotas de foto do produto e listagem de membros do tenant"
```

---

### Task 11: Front — mídia no navegador e clients de API

INVOCAR o skill `frontend-design` antes de escrever UI (esta task é quase toda lógica, mas as próximas dependem dela; leia `docs/identidade-visual.md` de qualquer forma).

**Files:**
- Create: `frontend/src/lib/media.ts`
- Create: `frontend/src/lib/attachments.ts`
- Create: `frontend/src/lib/members.ts`

**Interfaces:**
- Consumes: `api` (`lib/api.ts`).
- Produces (media.ts): `type MediaKind = "imagem" | "pdf" | "video"`, `ACCEPTED_MIME: string[]`, `MAX_UPLOAD_BYTES = 52_428_800`, `kindOf(file: File): MediaKind | null`, `compressImage(file: File): Promise<File>` (acima de 2 MB ou 2000px devolve WebP reduzido; abaixo devolve o próprio arquivo; em qualquer falha devolve o original), `captureVideoThumb(file: File): Promise<Blob | null>` (frame ~1s em WebP, `null` se o navegador não decodificar).
- Produces (attachments.ts): tipos `Attachment`, `AttachmentIntent`, `UploadProgress`; funções `requestIntent(ticketId, body)`, `putToStorage(url, body, contentType, onProgress) -> Promise<void>`, `confirmUpload(ticketId, attachmentId)`, `listAttachments(ticketId)`, `attachmentUrl(ticketId, attachmentId, variante)`, `deleteAttachment(ticketId, attachmentId)`, e a orquestração `uploadAttachment(ticketId, file, onProgress) -> Promise<Attachment>`; para produto: `requestProductPhotoIntent(productId, body)`, `confirmProductPhoto(productId, objectKey)`, `deleteProductPhoto(productId)`, `uploadProductPhoto(productId, file, onProgress)`.
- Produces (members.ts): `type Member = { id: string; name: string; role: string; active: boolean }` e `listMembers(): Promise<Member[]>`.

- [ ] **Step 1: Implementar `lib/media.ts`**

```ts
export type MediaKind = "imagem" | "pdf" | "video"

export const MAX_UPLOAD_BYTES = 52_428_800

const KINDS: Record<string, MediaKind> = {
  "image/jpeg": "imagem",
  "image/png": "imagem",
  "image/webp": "imagem",
  "application/pdf": "pdf",
  "video/mp4": "video",
  "video/quicktime": "video",
  "video/webm": "video",
}

export const ACCEPTED_MIME = Object.keys(KINDS)

const COMPRESS_ABOVE_BYTES = 2 * 1024 * 1024
const MAX_DIMENSION = 2000

export function kindOf(file: File): MediaKind | null {
  return KINDS[file.type] ?? null
}

async function loadImage(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error("falha ao decodificar imagem"))
      image.src = url
    })
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Reduz imagens grandes antes do upload. Em qualquer falha devolve o original:
 *  anexar a foto importa mais do que economizar bytes. */
export async function compressImage(file: File): Promise<File> {
  if (kindOf(file) !== "imagem") return file
  try {
    const image = await loadImage(file)
    const maior = Math.max(image.width, image.height)
    if (file.size <= COMPRESS_ABOVE_BYTES && maior <= MAX_DIMENSION) return file
    const escala = maior > MAX_DIMENSION ? MAX_DIMENSION / maior : 1
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(image.width * escala)
    canvas.height = Math.round(image.height * escala)
    const ctx = canvas.getContext("2d")
    if (!ctx) return file
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/webp", 0.82),
    )
    if (!blob || blob.size >= file.size) return file
    return new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.webp`, {
      type: "image/webp",
    })
  } catch {
    return file
  }
}

/** Captura um frame do video no proprio navegador (o servidor nao processa video). */
export async function captureVideoThumb(file: File): Promise<Blob | null> {
  if (kindOf(file) !== "video") return null
  const url = URL.createObjectURL(file)
  const video = document.createElement("video")
  video.muted = true
  video.playsInline = true
  video.preload = "metadata"
  try {
    const pronto = new Promise<void>((resolve, reject) => {
      const falhar = () => reject(new Error("codec sem suporte"))
      video.onerror = falhar
      video.onloadeddata = () => {
        video.currentTime = Math.min(1, (video.duration || 1) / 2)
      }
      video.onseeked = () => resolve()
      setTimeout(falhar, 8000)
    })
    video.src = url
    await pronto
    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext("2d")
    if (!ctx || !canvas.width || !canvas.height) return null
    ctx.drawImage(video, 0, 0)
    return await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), "image/webp", 0.8),
    )
  } catch {
    return null
  } finally {
    URL.revokeObjectURL(url)
    video.removeAttribute("src")
  }
}
```

- [ ] **Step 2: Implementar `lib/attachments.ts`**

```ts
import { api } from "@/lib/api"
import { captureVideoThumb, compressImage, kindOf, type MediaKind } from "@/lib/media"

export type Attachment = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  kind: MediaKind
  preview_status: "sem_preview" | "pendente" | "pronto" | "falhou"
  preview_url: string | null
  author_user_id: string
  author_name: string | null
  created_at: string | null
}

export type AttachmentIntent = {
  attachment_id: string
  object_key: string
  upload_url: string
  expires_in: number
  preview_upload_url: string | null
}

export type UploadProgress = (percent: number) => void

type IntentBody = {
  filename: string
  content_type: string
  size_bytes: number
  with_preview?: boolean
}

export const requestIntent = (ticketId: string, body: IntentBody) =>
  api<AttachmentIntent>(`/tickets/${ticketId}/anexos/intencao`, {
    method: "POST",
    body,
  })

export const confirmUpload = (ticketId: string, attachmentId: string) =>
  api<Attachment>(`/tickets/${ticketId}/anexos/${attachmentId}/confirmar`, {
    method: "POST",
  })

export const listAttachments = (ticketId: string) =>
  api<Attachment[]>(`/tickets/${ticketId}/anexos`)

export const attachmentUrl = (
  ticketId: string,
  attachmentId: string,
  variante: "medio" | "original" = "medio",
) =>
  api<{ url: string; expires_in: number }>(
    `/tickets/${ticketId}/anexos/${attachmentId}/url?variante=${variante}`,
  )

export const deleteAttachment = (ticketId: string, attachmentId: string) =>
  api<void>(`/tickets/${ticketId}/anexos/${attachmentId}`, { method: "DELETE" })

/** PUT direto no storage. Usa XMLHttpRequest porque fetch nao reporta progresso
 *  de upload. A URL ja vem assinada; nao acrescentar headers de autenticacao. */
export function putToStorage(
  url: string,
  body: Blob,
  contentType: string,
  onProgress?: UploadProgress,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    xhr.setRequestHeader("Content-Type", contentType)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`falha no upload (${xhr.status})`))
    xhr.onerror = () => reject(new Error("falha de rede no upload"))
    xhr.send(body)
  })
}

export async function uploadAttachment(
  ticketId: string,
  file: File,
  onProgress?: UploadProgress,
): Promise<Attachment> {
  const preparado = await compressImage(file)
  const thumb = await captureVideoThumb(preparado)
  const intent = await requestIntent(ticketId, {
    filename: preparado.name,
    content_type: preparado.type,
    size_bytes: preparado.size,
    with_preview: thumb !== null,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress)
  if (thumb && intent.preview_upload_url) {
    await putToStorage(intent.preview_upload_url, thumb, "image/webp")
  }
  return confirmUpload(ticketId, intent.attachment_id)
}

export type PhotoIntent = { object_key: string; upload_url: string; expires_in: number }

export const requestProductPhotoIntent = (
  productId: string,
  body: { content_type: string; size_bytes: number },
) =>
  api<PhotoIntent>(`/cadastros/produtos/${productId}/foto/intencao`, {
    method: "POST",
    body,
  })

export const confirmProductPhoto = (productId: string, objectKey: string) =>
  api<void>(`/cadastros/produtos/${productId}/foto/confirmar`, {
    method: "POST",
    body: { object_key: objectKey },
  })

export const deleteProductPhoto = (productId: string) =>
  api<void>(`/cadastros/produtos/${productId}/foto`, { method: "DELETE" })

export async function uploadProductPhoto(
  productId: string,
  file: File,
  onProgress?: UploadProgress,
): Promise<void> {
  if (kindOf(file) !== "imagem") throw new Error("a foto do produto precisa ser imagem")
  const preparado = await compressImage(file)
  const intent = await requestProductPhotoIntent(productId, {
    content_type: preparado.type,
    size_bytes: preparado.size,
  })
  await putToStorage(intent.upload_url, preparado, preparado.type, onProgress)
  await confirmProductPhoto(productId, intent.object_key)
}
```

- [ ] **Step 3: Implementar `lib/members.ts`**

```ts
import { api } from "@/lib/api"

export type Member = {
  id: string
  name: string
  role: string
  active: boolean
}

export const listMembers = () => api<Member[]>("/membros")
```

- [ ] **Step 4: Verificar e commitar**

Run (em `frontend/`): `pnpm lint && pnpm build`
Esperado: sucesso (módulos ainda não consumidos por telas).

```bash
git add frontend/src/lib/media.ts frontend/src/lib/attachments.ts frontend/src/lib/members.ts
git commit -m "Adiciona compressao de imagem, thumb de video e clients de anexo no front"
```

---

### Task 12: Front — card de anexos no detalhe do ticket

INVOCAR o skill `frontend-design`; seguir `docs/identidade-visual.md` (grid denso, sem sombra decorativa, Paprika só na ação primária — aqui o botão de anexar é ação secundária do card, não Paprika; badges de estado discretos; empty state de texto direto).

**Files:**
- Create: `frontend/src/components/tickets/AttachmentsCard.tsx`
- Modify: `frontend/src/pages/tickets/TicketDetailPage.tsx`

**Interfaces:**
- Consumes: `lib/attachments.ts` e `lib/media.ts` (Task 11); `canComment`, `isClosed` (`lib/tickets.ts`); `useAuth`; `Dialog`, `Button`, `Card`, `Badge` de `components/ui`; `toast` (sonner); `errorMessage` (padrão usado no `ActionPanel`).
- Produces: `AttachmentsCard({ ticketId, status, onChanged }: { ticketId: string; status: TicketStatus; onChanged: () => void })`.

Comportamento obrigatório:

1. **Dropzone**: área com borda tracejada aceitando drag-and-drop e clique (input `type="file"` oculto, `multiple`, `accept={ACCEPTED_MIME.join(",")}`). Estado visual de "arraste aqui" ao `dragover`. Escondida quando `isClosed(status)` ou `!canComment(role)`.
2. **Validação no client antes de subir**: arquivo com `kindOf(file) === null` ou `file.size > MAX_UPLOAD_BYTES` não sobe — `toast.error` nomeando o arquivo ("clipe.avi: tipo nao aceito", "video.mp4: acima de 50 MB"). Isso é o "se não couber, recusa no ato" do spec.
3. **Fila de upload**: estado local `enviando: { id: string; nome: string; percent: number; erro?: string }[]`, um item por arquivo, atualizado pelo callback de progresso. Uploads em série (um por vez) para não competir por banda. Ao terminar cada arquivo com sucesso, `refetch()` da lista e remoção do item da fila; em erro, o item fica com `erro` e um botão "tentar de novo".
4. **Grid**: `useQuery(["anexos", ticketId], () => listAttachments(ticketId))`. Cada card mostra: miniatura (`preview_url`) quando `preview_status === "pronto"`; ícone de PDF (`FileText`) ou de vídeo (`Video`) quando `sem_preview`; spinner discreto com texto "gerando preview" quando `pendente`; e ícone de imagem quebrada com texto "preview falhou" quando `falhou`. Sempre com o nome do arquivo (truncado, `title` completo), tamanho formatado e autor.
5. **Abrir**: clique no card chama `attachmentUrl(ticketId, id, "medio")` e abre `window.open(url, "_blank", "noopener")`. Item de menu "Baixar original" usa `variante=original`.
6. **Excluir**: item de menu abre `Dialog` de confirmação ("Remover anexo" + nome do arquivo + aviso de que o arquivo continua no armazenamento para auditoria); confirma com `deleteAttachment`, `refetch()` e `onChanged()`.
7. **Sem ações para visualizador e em ticket encerrado**: o grid continua visível, só as ações desaparecem.
8. Empty state: "Nenhum anexo neste ticket."

- [ ] **Step 1: Escrever o componente**

Estrutura mínima (o corpo do JSX segue o padrão visual dos outros cards do detalhe):

```tsx
type FilaItem = { id: string; nome: string; percent: number; erro?: string }

export function AttachmentsCard({ ticketId, status, onChanged }: Props) {
  const { session } = useAuth()
  const role = session?.role ?? null
  const podeAnexar = canComment(role) && !isClosed(status)
  const [fila, setFila] = useState<FilaItem[]>([])
  const [arrastando, setArrastando] = useState(false)
  const [removendo, setRemovendo] = useState<Attachment | null>(null)
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["anexos", ticketId],
    queryFn: () => listAttachments(ticketId),
  })

  async function enviar(arquivos: File[]) {
    for (const arquivo of arquivos) {
      if (kindOf(arquivo) === null) {
        toast.error(`${arquivo.name}: tipo nao aceito`)
        continue
      }
      if (arquivo.size > MAX_UPLOAD_BYTES) {
        toast.error(`${arquivo.name}: acima de 50 MB`)
        continue
      }
      const id = crypto.randomUUID()
      setFila((atual) => [...atual, { id, nome: arquivo.name, percent: 0 }])
      try {
        await uploadAttachment(ticketId, arquivo, (percent) =>
          setFila((atual) =>
            atual.map((item) => (item.id === id ? { ...item, percent } : item)),
          ),
        )
        setFila((atual) => atual.filter((item) => item.id !== id))
        await refetch()
        onChanged()
      } catch (error) {
        setFila((atual) =>
          atual.map((item) =>
            item.id === id ? { ...item, erro: errorMessage(error) } : item,
          ),
        )
      }
    }
  }
  // ... JSX: Card > CardHeader (titulo "Anexos" + contador) > CardContent com
  // dropzone (quando podeAnexar), fila de progresso, grid de cards e dialog de remocao
}
```

- [ ] **Step 2: Trocar o placeholder no detalhe**

Em `frontend/src/pages/tickets/TicketDetailPage.tsx`, substituir o card de Anexos placeholder por:

```tsx
<AttachmentsCard
  ticketId={data.ticket.id}
  status={data.ticket.status}
  onChanged={invalidate}
/>
```

- [ ] **Step 3: Verificar e commitar**

Run: `pnpm lint && pnpm build`. Com o ambiente de pé (`./dev.ps1`), anexar uma imagem, um PDF e um vídeo pequeno; conferir progresso, miniatura aparecendo depois do worker rodar (recarregue), abrir e excluir.

```bash
git add frontend/src/components/tickets/AttachmentsCard.tsx frontend/src/pages/tickets/TicketDetailPage.tsx
git commit -m "Adiciona card de anexos com drag-and-drop e previews no detalhe do ticket"
```

---

### Task 13: Front — foto do produto e seletor de supervisor

INVOCAR o skill `frontend-design`; seguir `docs/identidade-visual.md`.

**Files:**
- Modify: `frontend/src/pages/cadastros/ProdutosPage.tsx`
- Modify: `frontend/src/lib/cadastros.ts` (tipo `Product` ganha `photo_preview_key` e `photo_url`)
- Modify: `frontend/src/pages/tickets/TicketCreatePage.tsx`
- Modify: `frontend/src/components/tickets/ActionPanel.tsx`

**Interfaces:**
- Consumes: `uploadProductPhoto`, `deleteProductPhoto` (Task 11); `listMembers` (Task 11); `Select` de `components/ui`.
- Produces: coluna de foto na tabela de produtos, upload no formulário de produto, e campo Supervisor na criação e no diálogo de editar ticket.

Comportamento obrigatório:

1. **`lib/cadastros.ts`**: `Product` ganha `photo_preview_key: string | null` e `photo_url: string | null`.
2. **Tabela de produtos**: primeira coluna passa a ser a miniatura (`photo_url` em `<img>` de 32px com `rounded` e borda; sem foto, um quadrado com `ImageOff` de 16px). Nada de layout novo além disso.
3. **Formulário de produto (dialog existente)**: campo "Foto" com input de arquivo aceitando só imagem, mostrando progresso durante o upload e a miniatura atual quando houver, mais botão "Remover foto". Como o upload precisa do `id`, ele só aparece na edição de um produto já salvo — na criação, o campo fica desabilitado com o texto "Salve o produto para enviar a foto." (evita inventar upload em duas fases).
4. **Seletor de supervisor**: `useQuery(["membros"], listMembers)`; `Select` com opção "Sem supervisor" (valor vazio) e os membros com papel `admin` ou `supervisor` (filtre no client: `role === "admin" || role === "supervisor"`), rotulados `nome (papel)`. Entra em `TicketCreatePage` na seção Caso, enviando `supervisor_user_id`, e no diálogo "Editar dados" do `ActionPanel`, substituindo o reenvio cego do valor atual pelo valor escolhido (mantendo o atual como seleção inicial).

- [ ] **Step 1: Implementar as três mudanças**

Siga os contratos acima. No `ActionPanel`, a montagem do `updateTicket` passa a usar `editSupervisorId` (inicializado com `ticket.supervisor_user_id ?? ""`) em vez de `ticket.supervisor_user_id`.

- [ ] **Step 2: Verificar e commitar**

Run: `pnpm lint && pnpm build`. No dev: enviar foto de um produto, ver a miniatura na tabela, remover; criar ticket escolhendo supervisor e conferir o nome no detalhe; trocar o supervisor pelo diálogo de edição.

```bash
git add frontend/src/lib/cadastros.ts frontend/src/pages/cadastros/ProdutosPage.tsx frontend/src/pages/tickets/TicketCreatePage.tsx frontend/src/components/tickets/ActionPanel.tsx
git commit -m "Adiciona foto do produto e seletor de supervisor no front"
```

---

### Task 14: E2E de anexos, README e verificação final

**Files:**
- Create: `frontend/e2e/05-anexos.spec.ts`
- Create: `frontend/e2e/fixtures/defeito.png` (PNG pequeno, gerado no Step 1)
- Modify: `README.md`

**Interfaces:**
- Consumes: helpers de `frontend/e2e/helpers.ts` (`login`, `apiFullTicket`), suíte existente.

- [ ] **Step 1: Gerar a fixture**

Em `frontend/e2e/fixtures/`, criar `defeito.png` com um PNG pequeno de verdade:

```bash
cd frontend && mkdir -p e2e/fixtures && python -c "
from PIL import Image
Image.new('RGB', (600, 400), (200, 80, 40)).save('e2e/fixtures/defeito.png')
" || node -e "
const fs=require('fs');
const b64='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
fs.mkdirSync('e2e/fixtures',{recursive:true});
fs.writeFileSync('e2e/fixtures/defeito.png', Buffer.from(b64,'base64'));
"
```

(o `python` usa o Pillow do backend se disponível; o fallback em Node grava um PNG 1x1 válido.)

- [ ] **Step 2: Escrever o spec**

`frontend/e2e/05-anexos.spec.ts`:

```ts
import { expect, test } from "@playwright/test"

import { apiFullTicket, login } from "./helpers"

test("anexa imagem pelo dropzone e remove", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "admin")
  await page.goto(`/tickets/${ticket.id}`)

  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles("e2e/fixtures/defeito.png")

  await expect(page.getByText("defeito.png")).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText("Nenhum anexo neste ticket.")).toHaveCount(0)

  await page.getByRole("button", { name: /Acoes do anexo defeito\.png/ }).click()
  await page.getByRole("menuitem", { name: "Remover" }).click()
  await page.getByRole("dialog").getByRole("button", { name: "Remover" }).click()
  await expect(page.getByText("Nenhum anexo neste ticket.")).toBeVisible()
})

test("visualizador ve anexos sem dropzone", async ({ page, request }) => {
  const ticket = await apiFullTicket(request, "admin")
  await login(page, request, "viewer")
  await page.goto(`/tickets/${ticket.id}`)
  await expect(page.getByText("Anexos")).toBeVisible()
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
})
```

Nota: o `aria-label` do menu de cada anexo deve ser `Acoes do anexo {filename}` — garanta isso na Task 12 (é o que dá seletor estável aqui).

- [ ] **Step 3: Rodar o E2E**

Run (em `frontend/`, com db, minio, backend e worker de pé): `pnpm e2e`
Esperado: os 9 testes anteriores + os 2 novos, todos verdes.

- [ ] **Step 4: Suíte completa**

Backend (em `backend/`): `uv run ruff format .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
Frontend: `pnpm lint`, `pnpm build`.
Esperado: tudo verde. Corrigir qualquer regressão antes de seguir.

- [ ] **Step 5: README**

Acrescentar ao `README.md`:
- Na seção de pré-requisitos/quickstart: MinIO agora sobe no compose (console em `http://localhost:9001`, usuário `sacminio`, senha `sacminio123`, bucket `sac-dev`) e existe um serviço `worker`.
- Na seção de verificações: os testes de integração exigem `docker compose up -d db minio minio-init`.
- Nova seção da Fase 2B em "Fases entregues", no formato das anteriores: anexos de ticket com upload direto por presigned URL (imagem, PDF e vídeo até 50 MB, 10 por ticket), compressão de imagem e captura da thumb de vídeo no navegador, previews WebP (thumb 400px e média 1200px) por worker com fila em tabela e retry com backoff, soft delete preservando o objeto, foto de catálogo do produto e endpoint de membros do tenant com seletor de supervisor no ticket. Anote que a galeria de mídias fica na Fase 3.

- [ ] **Step 6: Commit final**

```bash
git add frontend/e2e/05-anexos.spec.ts frontend/e2e/fixtures/defeito.png README.md
git commit -m "Adiciona e2e de anexos e documenta a Fase 2B no README"
```

- [ ] **Step 7: Encerramento**

Invocar o skill `superpowers:finishing-a-development-branch`.
