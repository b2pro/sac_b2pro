from datetime import UTC, datetime
from uuid import uuid4

from sac.application.ports_reporting import MediaFilters, MediaItemRow, ReportFilters
from sac.application.use_cases.reporting import ExportReportUseCase, ListMediaUseCase
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewStatus,
    TicketAttachment,
)


def _attachment(preview: PreviewStatus, preview_key: str | None) -> TicketAttachment:
    return TicketAttachment(
        id=uuid4(),
        ticket_id=uuid4(),
        filename="a.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        object_key="k.jpg",
        kind=AttachmentKind.IMAGEM,
        status=AttachmentStatus.DISPONIVEL,
        preview_status=preview,
        preview_key=preview_key,
        author_user_id=uuid4(),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


class FakeReportingRepo:
    def __init__(self, media=(), export_pages=()):  # noqa: ANN001
        self._media = list(media)
        self._pages = list(export_pages)

    async def list_media(self, filters, page, per_page):  # noqa: ANN001
        return self._media, len(self._media)

    async def export_rows(self, filters, page, per_page):  # noqa: ANN001
        return self._pages[page - 1] if page <= len(self._pages) else []


class FakeStorage:
    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        return f"https://signed/{key}"


async def test_list_media_assina_preview_pronto_e_deixa_none_sem_preview() -> None:
    rows = [
        MediaItemRow(_attachment(PreviewStatus.PRONTO, "thumb.webp"), ticket_number=1),
        MediaItemRow(_attachment(PreviewStatus.PENDENTE, None), ticket_number=2),
    ]
    views, total = await ListMediaUseCase(FakeReportingRepo(media=rows), FakeStorage()).execute(
        MediaFilters(), page=1, per_page=10
    )
    assert total == 2
    assert views[0].preview_url == "https://signed/thumb.webp"
    assert views[1].preview_url is None


async def test_export_stream_pagina_ate_esgotar() -> None:
    pages = [["r1", "r2"], ["r3"]]  # o use case nao inspeciona as linhas
    use_case = ExportReportUseCase(FakeReportingRepo(export_pages=pages), chunk_size=2)
    got = [chunk async for chunk in use_case.stream(ReportFilters())]
    assert got == [["r1", "r2"], ["r3"]]
