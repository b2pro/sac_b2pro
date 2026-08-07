from datetime import UTC, datetime
from uuid import uuid4

from sac.application.ports_reporting import MediaFilters, MediaItemRow, ReportFilters
from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.reporting import ExportReportUseCase, ListMediaUseCase
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewStatus,
    TicketAttachment,
)
from sac.domain.permissions import Role

_ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)


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

    async def export_rows(self, filters, page, per_page, owner_user_id=None):  # noqa: ANN001
        return self._pages[page - 1] if page <= len(self._pages) else []


class FakeStorage:
    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        return f"https://signed/{key}"


class PartlyRaisingStorage:
    """Simula uma chave invalida (ou o storage fora do ar) so para um item,
    para provar que os demais da pagina continuam assinados normalmente."""

    def __init__(self, bad_key: str) -> None:
        self._bad_key = bad_key

    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        if key == self._bad_key:
            raise RuntimeError("storage indisponível")
        return f"https://signed/{key}"


def _media_row(preview: PreviewStatus, preview_key: str | None, ticket_number: int) -> MediaItemRow:
    return MediaItemRow(
        attachment=_attachment(preview, preview_key),
        ticket_number=ticket_number,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


async def test_list_media_assina_preview_pronto_e_deixa_none_sem_preview() -> None:
    rows = [
        _media_row(PreviewStatus.PRONTO, "thumb.webp", ticket_number=1),
        _media_row(PreviewStatus.PENDENTE, None, ticket_number=2),
    ]
    views, total = await ListMediaUseCase(FakeReportingRepo(media=rows), FakeStorage()).execute(
        _ADMIN, MediaFilters(), page=1, per_page=10
    )
    assert total == 2
    assert views[0].preview_url == "https://signed/thumb.webp"
    assert views[1].preview_url is None


async def test_list_media_falha_ao_assinar_um_item_nao_derruba_a_pagina() -> None:
    rows = [
        _media_row(PreviewStatus.PRONTO, "thumb-ok.webp", ticket_number=1),
        _media_row(PreviewStatus.PRONTO, "thumb-quebrado.webp", ticket_number=2),
    ]
    use_case = ListMediaUseCase(
        FakeReportingRepo(media=rows), PartlyRaisingStorage(bad_key="thumb-quebrado.webp")
    )
    views, total = await use_case.execute(_ADMIN, MediaFilters(), page=1, per_page=10)
    assert total == 2
    assert views[0].preview_url == "https://signed/thumb-ok.webp"
    assert views[1].preview_url is None


async def test_export_stream_pagina_ate_esgotar() -> None:
    pages = [["r1", "r2"], ["r3"]]  # o use case nao inspeciona as linhas
    use_case = ExportReportUseCase(FakeReportingRepo(export_pages=pages), chunk_size=2)
    got = [chunk async for chunk in use_case.stream(_ADMIN, ReportFilters())]
    assert got == [["r1", "r2"], ["r3"]]
