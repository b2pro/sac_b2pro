from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_attachments import ObjectHead, TenantMember
from sac.domain.attachments import (
    PreviewJob,
    PreviewJobStatus,
    TicketAttachment,
)
from sac.domain.errors import StorageUnavailableError


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.assinaturas: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.fail_delete_for: set[str] = set()
        # last_modified do bucket, como no S3: toda gravacao marca "agora", e o
        # teste que precisa de um objeto velho reescreve a entrada. O default
        # nunca e uma data antiga, senao um objeto criado sem cuidado no teste
        # entraria como candidato a delecao na reconciliacao.
        self.last_modified: dict[str, datetime] = {}

    def simulate_upload(self, key: str, data: bytes, content_type: str) -> None:
        """Faz o papel do navegador: grava no bucket sem passar pelo backend."""
        self.objects[key] = (data, content_type)
        self.last_modified[key] = datetime.now(UTC)

    def presigned_put(self, key: str, content_type: str, ttl_seconds: int) -> str:
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
        self.last_modified[key] = datetime.now(UTC)

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key][0]

    def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        return [
            (key, self.last_modified[key]) for key in sorted(self.objects) if key.startswith(prefix)
        ]

    def delete(self, key: str) -> None:
        if key in self.fail_delete_for:
            raise StorageUnavailableError("storage indisponivel (fake)")
        self.deleted.append(key)
        self.objects.pop(key, None)


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
