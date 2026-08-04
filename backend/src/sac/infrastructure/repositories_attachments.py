from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_attachments import TenantMember
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from sac.domain.errors import NotFoundError
from sac.domain.permissions import Role
from sac.infrastructure.models import PreviewJobModel, TenantModel, UserModel, UserTenantModel
from sac.infrastructure.models_tenant import ProductModel, TicketAttachmentModel
from sac.infrastructure.repositories_tickets import flush_tickets


def attachment_entity(m: TicketAttachmentModel) -> TicketAttachment:
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
        return attachment_entity(m) if m is not None else None

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
        return [attachment_entity(m) for m in rows]

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
        return [attachment_entity(m) for m in rows]


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


# Colunas de chave de objeto das duas fontes de chaves conhecidas. Existem como
# constante, e nao inline na consulta, porque
# tests/unit/infrastructure/test_reconcile_guards.py compara estas listas com as
# colunas `*_key` reais dos modelos: uma coluna de chave nova quebra o teste alto
# e claro, em vez de virar delecao silenciosa do objeto que ela aponta na
# proxima varredura.
ATTACHMENT_KEY_COLUMNS = (
    TicketAttachmentModel.object_key,
    TicketAttachmentModel.preview_key,
    TicketAttachmentModel.preview_medium_key,
)
PRODUCT_KEY_COLUMNS = (ProductModel.photo_key, ProductModel.photo_preview_key)


class SqlKnownKeysRepository:
    """Uniao das chaves de objeto que este tenant ainda reconhece. Alimenta a
    reconciliacao de orfaos, que apaga do bucket o que NAO estiver aqui - uma
    fonte esquecida nesta consulta e anexo vivo destruido.

    Sao duas fontes, e nas duas `deleted_at IS NULL` faz parte da definicao de
    legitimo:

    - `ticket_attachments`: object_key + as duas previews, das linhas ativas e
      NAO expiradas. Os dois estados excluidos sao justamente os que a delecao
      direta (best-effort) pode perder: a exclusao e o descarte marcam
      deleted_at, e a expiracao marca apenas status=EXPIRADO e nunca deleted_at.
      Como nao existe caminho de restauracao de anexo - e confirmar uma intencao
      expirada e recusado com conflito - o objeto dessas linhas tem que sumir;
      proteger qualquer uma delas aqui deixaria a rede de seguranca sem nada
      para pegar. O filtro de status e por diferenca (`!= EXPIRADO`) e nao por
      lista: um status novo no futuro entra protegido, que e o lado seguro.
    - `products`: photo_key, photo_preview_key e AS DUAS previews derivadas da
      foto. A derivacao nao e enfeite: o worker escreve thumb e medium no
      bucket, mas a tabela guarda so a thumb (`photo_preview_key`), entao sem
      derivar o medium ele seria apagado como orfao a cada varredura. Aqui o
      filtro e apenas deleted_at: produto INATIVO continua listado na API com a
      foto assinada, logo a foto dele e legitima.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def known_keys(self) -> set[str]:
        chaves: set[str] = set()
        anexos = await self._session.execute(
            select(*ATTACHMENT_KEY_COLUMNS).where(
                TicketAttachmentModel.deleted_at.is_(None),
                TicketAttachmentModel.status != str(AttachmentStatus.EXPIRADO),
            )
        )
        for linha in anexos.all():
            chaves.update(chave for chave in linha if chave)
        fotos = await self._session.execute(
            select(*PRODUCT_KEY_COLUMNS).where(
                ProductModel.deleted_at.is_(None),
                or_(
                    ProductModel.photo_key.is_not(None),
                    ProductModel.photo_preview_key.is_not(None),
                ),
            )
        )
        for photo_key, photo_preview_key in fotos.all():
            if photo_preview_key:
                chaves.add(photo_preview_key)
            if photo_key:
                chaves.add(photo_key)
                chaves.update(preview_keys_for(photo_key))
        return chaves


class SqlTenantMemberDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_members(self, tenant_slug: str) -> list[TenantMember]:
        """Traz tambem os membros inativos, marcados com active=False - quem
        decide o que fazer com eles e o cliente. Filtrar aqui faria o supervisor
        ja atribuido a um ticket desaparecer da resposta quando fosse desativado,
        e o seletor mostraria "Sem supervisor" para um ticket que tem supervisor.
        Inativo e vinculo desativado OU usuario desativado globalmente: as duas
        coisas tiram o membro de circulacao. Excluido por soft delete continua
        fora da lista - esse nao existe mais.
        """
        rows = await self._session.execute(
            select(
                UserModel.id,
                UserModel.name,
                UserTenantModel.role,
                UserTenantModel.active,
                UserModel.active,
            )
            .join(UserTenantModel, UserTenantModel.user_id == UserModel.id)
            .join(TenantModel, TenantModel.id == UserTenantModel.tenant_id)
            .where(
                TenantModel.slug == tenant_slug,
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.name)
        )
        return [
            TenantMember(id=row[0], name=row[1], role=Role(row[2]), active=bool(row[3] and row[4]))
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
