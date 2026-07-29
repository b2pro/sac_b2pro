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
        raise ValidationError("tipo de arquivo nao aceito", details={"field": "content_type"})
    return entry


def kind_for(content_type: str) -> AttachmentKind:
    return _entry(content_type)[0]


def extension_for(content_type: str) -> str:
    return _entry(content_type)[1]


def validate_size(size_bytes: int) -> None:
    if size_bytes < 1 or size_bytes > MAX_ATTACHMENT_BYTES:
        raise ValidationError("tamanho de arquivo invalido", details={"field": "size_bytes"})


def build_object_key(tenant_slug: str, ticket_id: UUID, content_type: str, uid: UUID) -> str:
    return f"{tenant_slug}/{ticket_id}/{uid}.{extension_for(content_type)}"


def build_product_photo_key(
    tenant_slug: str, product_id: UUID, content_type: str, uid: UUID
) -> str:
    return f"{tenant_slug}/catalogo/produtos/{product_id}/{uid}.{extension_for(content_type)}"


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
