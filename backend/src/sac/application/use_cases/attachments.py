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
    MAX_ATTACHMENT_BYTES,
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
        max_bytes: int = MAX_ATTACHMENT_BYTES,
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
        max_bytes: int = MAX_ATTACHMENT_BYTES,
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
        self,
        actor: TicketActor,
        ticket_id: UUID,
        attachment_id: UUID,
        variant: str = "medio",
    ) -> str:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        anexo = await _attachment_of_ticket(self._attachments, ticket.id, attachment_id)
        chave = anexo.object_key
        if variant == "medio" and anexo.preview_medium_key:
            chave = anexo.preview_medium_key
        return self._storage.presigned_get(chave, self._ttl)


class DeleteAttachmentUseCase:
    def __init__(self, tickets: TicketRepository, attachments: AttachmentRepository) -> None:
        self._tickets = tickets
        self._attachments = attachments

    async def execute(self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID) -> None:
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
        total = 0
        for anexo in pendentes:
            # list_pending_before nao filtra deleted_at (Task 4); anexos ja
            # excluidos por soft delete ja estao invisiveis em list_by_ticket
            # e count_active, entao nao contam aqui nem mudam de status.
            if anexo.deleted_at is not None:
                continue
            anexo.status = AttachmentStatus.EXPIRADO
            await self._attachments.update(anexo)
            total += 1
        return total
