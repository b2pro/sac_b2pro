import dataclasses
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sac.application.ports import TokenPayload
from sac.application.ports_reporting import MediaFilters, RankingEntry, ReportFilters
from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.reporting import (
    ExportReportUseCase,
    GetDashboardUseCase,
    GetReportUseCase,
    ListMediaUseCase,
)
from sac.domain.attachments import AttachmentKind
from sac.domain.permissions import Permission
from sac.domain.tickets import TicketStatus
from sac.infrastructure.csv_export import CSV_HEADER, csv_line, export_row_values
from sac.infrastructure.repositories_reporting import SqlReportingRepository
from sac.infrastructure.repositories_tickets import TicketRepos
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.interface.deps import (
    get_reporting_repository,
    get_settings,
    get_storage,
    get_ticket_repos,
    require_permission,
)
from sac.interface.schemas import ticket_list_item_out
from sac.interface.schemas_reporting import (
    DashboardKpiOut,
    DashboardOut,
    MediaItemOut,
    MediaPageOut,
    RankingOut,
    ReportKpisOut,
    ReportOut,
)

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
relatorios_router = APIRouter(prefix="/relatorios", tags=["relatorios"])
midias_router = APIRouter(prefix="/midias", tags=["midias"])

_view = require_permission(Permission.VER_VISIBILIDADE)


def _actor(identity: TokenPayload) -> TicketActor:
    assert identity.role is not None  # garantido pela dependency de permissao
    return TicketActor(user_id=identity.user_id, role=identity.role)


def _ranking_out(entries: list[RankingEntry]) -> list[RankingOut]:
    return [RankingOut(id=e.id, name=e.name, count=e.count) for e in entries]


def _report_filters(
    de: datetime | None = None,
    ate: datetime | None = None,
    brand_id: UUID | None = None,
    product_id: UUID | None = None,
    defect_type_id: UUID | None = None,
    solution_type_id: UUID | None = None,
    status: TicketStatus | None = None,
    atendente_id: UUID | None = None,
    channel_id: UUID | None = None,
) -> ReportFilters:
    return ReportFilters(
        date_from=de,
        date_to=ate,
        brand_id=brand_id,
        product_id=product_id,
        defect_type_id=defect_type_id,
        solution_type_id=solution_type_id,
        status=status,
        attendant_user_id=atendente_id,
        purchase_channel_id=channel_id,
    )


@dashboard_router.get("", response_model=DashboardOut)
async def get_dashboard(
    brand_id: UUID | None = None,
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
    ticket_repos: TicketRepos = Depends(get_ticket_repos),
) -> DashboardOut:
    data, names = await GetDashboardUseCase(repo, ticket_repos.users).execute(
        _actor(identity), brand_id, datetime.now(UTC)
    )
    recent = [
        ticket_list_item_out(
            dataclasses.replace(row, attendant_name=names.get(row.ticket.attendant_user_id))
        )
        for row in data.recent
    ]
    return DashboardOut(
        kpis=[DashboardKpiOut(key=k.key, count=k.count, filters=k.filters) for k in data.kpis],
        status_counts=data.status_counts,
        products=_ranking_out(data.products),
        defects=_ranking_out(data.defects),
        solutions=_ranking_out(data.solutions),
        avg_resolution_hours=data.avg_resolution_hours,
        recent=recent,
    )


@relatorios_router.get("/export")
async def export_relatorio(
    filters: ReportFilters = Depends(_report_filters),
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
) -> StreamingResponse:
    use_case = ExportReportUseCase(repo)
    # os chunks sao materializados aqui (dentro do handler, com a sessao do
    # tenant ainda aberta) porque a sessao da dependency-with-yield e fechada
    # no retorno do handler; um generator lazy ainda nao drenado estouraria
    # ao tentar usar a sessao dentro do StreamingResponse, ja fora do escopo
    # da dependency.
    chunks = [chunk async for chunk in use_case.stream(_actor(identity), filters)]

    async def stream() -> AsyncIterator[str]:
        yield "﻿" + csv_line(list(CSV_HEADER))
        for chunk in chunks:
            for row in chunk:
                yield csv_line(export_row_values(row))

    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="relatorio-tickets.csv"'},
    )


@relatorios_router.get("", response_model=ReportOut)
async def get_report(
    filters: ReportFilters = Depends(_report_filters),
    page: int = 1,
    per_page: int = 20,
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
    ticket_repos: TicketRepos = Depends(get_ticket_repos),
) -> ReportOut:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    data, names = await GetReportUseCase(repo, ticket_repos.users).execute(
        _actor(identity), filters, page, per_page
    )
    items = [
        ticket_list_item_out(
            dataclasses.replace(row, attendant_name=names.get(row.ticket.attendant_user_id))
        )
        for row in data.tickets
    ]
    return ReportOut(
        kpis=ReportKpisOut(
            total=data.kpis.total,
            finalized=data.kpis.finalized,
            declined=data.kpis.declined,
            avg_resolution_hours=data.kpis.avg_resolution_hours,
        ),
        products=_ranking_out(data.products),
        defects=_ranking_out(data.defects),
        solutions=_ranking_out(data.solutions),
        items=items,
        total=data.total,
        page=page,
        per_page=per_page,
    )


@midias_router.get("", response_model=MediaPageOut)
async def list_media(
    kind: AttachmentKind | None = None,
    brand_id: UUID | None = None,
    product_id: UUID | None = None,
    defect_type_id: UUID | None = None,
    solution_type_id: UUID | None = None,
    status: TicketStatus | None = None,
    de: datetime | None = None,
    ate: datetime | None = None,
    page: int = 1,
    per_page: int = 20,
    identity: TokenPayload = Depends(_view),
    repo: SqlReportingRepository = Depends(get_reporting_repository),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> MediaPageOut:
    filters = MediaFilters(
        kind=kind,
        brand_id=brand_id,
        product_id=product_id,
        defect_type_id=defect_type_id,
        solution_type_id=solution_type_id,
        status=status,
        date_from=de,
        date_to=ate,
    )
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    use_case = ListMediaUseCase(repo, storage, settings.presigned_ttl_seconds)
    views, total = await use_case.execute(_actor(identity), filters, page, per_page)
    items = [
        MediaItemOut(
            id=v.attachment.id,
            ticket_id=v.attachment.ticket_id,
            ticket_number=v.ticket_number,
            filename=v.attachment.filename,
            kind=v.attachment.kind,
            content_type=v.attachment.content_type,
            size_bytes=v.attachment.size_bytes,
            created_at=v.created_at,
            preview_url=v.preview_url,
        )
        for v in views
    ]
    return MediaPageOut(items=items, total=total, page=page, per_page=per_page)
