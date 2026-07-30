from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from sac.application.ports_attachments import StoragePort
from sac.application.ports_reporting import (
    DashboardData,
    MediaFilters,
    ReportData,
    ReportExportRow,
    ReportFilters,
    ReportingRepository,
)
from sac.application.ports_tickets import TicketActor, UserDirectoryPort
from sac.application.use_cases.tickets_shared import restrict_to_own
from sac.domain.attachments import PreviewStatus, TicketAttachment


@dataclass(frozen=True)
class MediaView:
    attachment: TicketAttachment
    ticket_number: int
    created_at: datetime
    preview_url: str | None


class GetDashboardUseCase:
    def __init__(self, repo: ReportingRepository, users: UserDirectoryPort) -> None:
        self._repo = repo
        self._users = users

    async def execute(
        self, actor: TicketActor, brand_id: UUID | None, now: datetime
    ) -> tuple[DashboardData, dict[UUID, str]]:
        owner = restrict_to_own(actor)
        data = await self._repo.dashboard(brand_id, actor.user_id, now, owner_user_id=owner)
        names = await self._users.names_by_ids(
            {row.ticket.attendant_user_id for row in data.recent}
        )
        return data, names


class GetReportUseCase:
    def __init__(self, repo: ReportingRepository, users: UserDirectoryPort) -> None:
        self._repo = repo
        self._users = users

    async def execute(
        self, actor: TicketActor, filters: ReportFilters, page: int, per_page: int
    ) -> tuple[ReportData, dict[UUID, str]]:
        owner = restrict_to_own(actor)
        data = await self._repo.report(filters, page, per_page, actor.user_id, owner_user_id=owner)
        names = await self._users.names_by_ids(
            {row.ticket.attendant_user_id for row in data.tickets}
        )
        return data, names


class ExportReportUseCase:
    def __init__(self, repo: ReportingRepository, chunk_size: int = 500) -> None:
        self._repo = repo
        self._chunk_size = chunk_size

    async def stream(
        self, actor: TicketActor, filters: ReportFilters
    ) -> AsyncIterator[list[ReportExportRow]]:
        owner = restrict_to_own(actor)
        page = 1
        while True:
            rows = await self._repo.export_rows(
                filters, page, self._chunk_size, owner_user_id=owner
            )
            if not rows:
                return
            yield rows
            page += 1


class ListMediaUseCase:
    def __init__(
        self, repo: ReportingRepository, storage: StoragePort, ttl_seconds: int = 300
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._ttl_seconds = ttl_seconds

    async def execute(
        self, actor: TicketActor, filters: MediaFilters, page: int, per_page: int
    ) -> tuple[list[MediaView], int]:
        owner = restrict_to_own(actor)
        if owner is not None:
            filters = replace(filters, attendant_user_id=owner)
        rows, total = await self._repo.list_media(filters, page, per_page)
        views = [
            MediaView(
                attachment=row.attachment,
                ticket_number=row.ticket_number,
                created_at=row.created_at,
                preview_url=self._preview_url(row.attachment),
            )
            for row in rows
        ]
        return views, total

    def _preview_url(self, attachment: TicketAttachment) -> str | None:
        if attachment.preview_status != PreviewStatus.PRONTO or not attachment.preview_key:
            return None
        try:
            return self._storage.presigned_get(attachment.preview_key, self._ttl_seconds)
        except Exception:
            # falha ao assinar um item (chave invalida, storage indisponivel)
            # nao pode derrubar a pagina inteira da galeria — o item so sai
            # sem preview, como qualquer anexo sem thumbnail gerado.
            return None
