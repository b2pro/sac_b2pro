from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sac.domain.attachments import PreviewJob, TicketAttachment
from sac.domain.permissions import Role


@dataclass(frozen=True)
class ObjectHead:
    content_type: str
    size_bytes: int


class StoragePort(Protocol):
    # presigned_put NAO recebe limite de tamanho: URL assinada de put_object nao
    # suporta content-length-range (isso e feature de POST policy), entao um
    # parametro desses seria ignorado em silencio e a porta prometeria uma
    # garantia que nao existe. O limite e aplicado na intencao (validate_size) e
    # no HEAD da confirmacao; o risco residual e a regra de ciclo de vida que o
    # mitiga estao documentados em docs/armazenamento-anexos.md.
    def presigned_put(self, key: str, content_type: str, ttl_seconds: int) -> str: ...
    def presigned_get(self, key: str, ttl_seconds: int) -> str: ...
    def head(self, key: str) -> ObjectHead | None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...


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


class PreviewGenerator(Protocol):
    def __call__(self, data: bytes) -> tuple[bytes, bytes]: ...


class ProductPhotoRepository(Protocol):
    async def set_photo(
        self, product_id: UUID, photo_key: str | None, preview_key: str | None
    ) -> None: ...
    async def get_photo(self, product_id: UUID) -> tuple[str | None, str | None] | None: ...


class TenantMemberDirectory(Protocol):
    async def list_members(self, tenant_slug: str) -> list[TenantMember]: ...
