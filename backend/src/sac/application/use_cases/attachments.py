import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
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
    StorageUnavailableError,
    ValidationError,
)
from sac.domain.permissions import Permission, has_permission
from sac.domain.tickets import is_closed

logger = logging.getLogger(__name__)


def _delete_object_keys(storage: StoragePort, anexo: TicketAttachment) -> None:
    """Apaga os objetos do anexo no storage: best-effort, chamado sempre
    DEPOIS de persistir a mudanca de estado. Uma falha aqui nunca pode
    propagar - o estado do dominio ja e a fonte da verdade e a varredura de
    reconciliacao (Task 11) e a rede de seguranca para o que sobrar orfao.
    Cada chave e tentada de forma independente: a falha em uma nao pode
    impedir a tentativa nas outras.
    """
    for key in (anexo.object_key, anexo.preview_key, anexo.preview_medium_key):
        if key is None:
            continue
        try:
            storage.delete(key)
        except StorageUnavailableError:
            logger.warning("falha ao apagar objeto do storage key=%s", key)


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


def _view_of(
    attachment: TicketAttachment, storage: StoragePort, ttl_seconds: int
) -> AttachmentView:
    """Regra unica de quando uma preview pode ser exposta: so quando ela esta
    PRONTA e existe uma chave gravada. Usado tanto na listagem quanto na
    confirmacao para que a decisao nao seja duplicada na camada de interface.
    """
    url = (
        storage.presigned_get(attachment.preview_key, ttl_seconds)
        if attachment.preview_status is PreviewStatus.PRONTO and attachment.preview_key
        else None
    )
    return AttachmentView(attachment=attachment, preview_url=url)


class RequestUploadUseCase:
    def __init__(
        self,
        tickets: TicketRepository,
        attachments: AttachmentRepository,
        storage: StoragePort,
        tenant_slug: str,
        ttl_seconds: int = 300,
        max_per_ticket: int = MAX_ATTACHMENTS_PER_TICKET,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._ttl = ttl_seconds
        self._max_per_ticket = max_per_ticket

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
            preview_url = self._storage.presigned_put(thumb_key, "image/webp", self._ttl)
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
            upload_url=self._storage.presigned_put(object_key, data.content_type, self._ttl),
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
        ttl_seconds: int = 300,
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._jobs = jobs
        self._storage = storage
        self._tenant_slug = tenant_slug
        self._max_bytes = max_bytes
        self._ttl = ttl_seconds

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID
    ) -> AttachmentView:
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
            thumb_head = self._storage.head(anexo.preview_key)
            if (
                thumb_head is not None
                and 1 <= thumb_head.size_bytes <= self._max_bytes
                and thumb_head.content_type == "image/webp"
            ):
                anexo.preview_status = PreviewStatus.PRONTO
            else:
                # Thumb ausente, grande demais ou de tipo inesperado: trata como
                # se o navegador nao tivesse enviado thumb nenhum. Uma thumb ruim
                # nunca bloqueia a confirmacao do video em si.
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
        return _view_of(anexo, self._storage, self._ttl)


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
        return [_view_of(anexo, self._storage, self._ttl) for anexo in anexos]


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
    def __init__(
        self, tickets: TicketRepository, attachments: AttachmentRepository, storage: StoragePort
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage

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
        _delete_object_keys(self._storage, anexo)


class IntentDiscardResult(StrEnum):
    """O que o servidor fez com o pedido de descarte. `DISPONIVEL` significa que
    o upload na verdade deu certo e nada foi apagado — o cliente que perdeu a
    resposta do confirmar descobre por aqui que o anexo existe.
    """

    DESCARTADO = "descartado"
    DISPONIVEL = "disponivel"


class DiscardIntentUseCase:
    """Desfaz uma intencao de upload abandonada, devolvendo a vaga que ela ocupa
    na cota do ticket.

    Existe separado de DeleteAttachmentUseCase porque o cliente nao sabe, num
    upload que falhou, se o `confirmar` chegou a commitar: uma resposta perdida
    depois do commit fazia o cliente pedir a exclusao de um anexo real. Aqui
    quem decide e o servidor, olhando o status da propria linha.
    """

    def __init__(
        self, tickets: TicketRepository, attachments: AttachmentRepository, storage: StoragePort
    ) -> None:
        self._tickets = tickets
        self._attachments = attachments
        self._storage = storage

    async def execute(
        self, actor: TicketActor, ticket_id: UUID, attachment_id: UUID
    ) -> IntentDiscardResult:
        ticket = await get_ticket_or_404(self._tickets, actor, ticket_id)
        # Sem guarda de ticket encerrado, ao contrario das outras escritas de
        # anexo: a vaga precisa voltar mesmo se o ticket fechou durante o upload,
        # e uma linha pendente nao aparece na listagem — nao e alteracao visivel.
        anexo = await _attachment_of_ticket(self._attachments, ticket.id, attachment_id)
        # Mais restrito que a exclusao, que admin e supervisor podem fazer em
        # anexo alheio: descartar intencao e desfazer o proprio upload.
        if anexo.author_user_id != actor.user_id:
            raise PermissionDeniedError("sem permissao para descartar intencao de outro autor")
        if anexo.status is AttachmentStatus.DISPONIVEL:
            return IntentDiscardResult.DISPONIVEL
        if anexo.status is AttachmentStatus.PENDENTE:
            anexo.deleted_at = datetime.now(UTC)
            await self._attachments.update(anexo)
            _delete_object_keys(self._storage, anexo)
        # EXPIRADO ja saiu da cota pela varredura: nada a escrever.
        return IntentDiscardResult.DESCARTADO


class ExpirePendingUseCase:
    def __init__(
        self, attachments: AttachmentRepository, storage: StoragePort, minutes: int = 30
    ) -> None:
        self._attachments = attachments
        self._storage = storage
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
            _delete_object_keys(self._storage, anexo)
            total += 1
        return total
