from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from sac.application.ports_reporting import (
    DashboardData,
    DashboardKpi,
    MediaFilters,
    MediaItemRow,
    RankingEntry,
    ReportData,
    ReportExportRow,
    ReportFilters,
    ReportKpis,
)
from sac.application.ports_tickets import TicketFilters, TicketListRow
from sac.domain.attachments import AttachmentStatus
from sac.domain.tickets import CLOSED_STATUSES, TicketStatus
from sac.infrastructure.models import UserModel
from sac.infrastructure.models_tenant import (
    BrandModel,
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    PurchaseChannelModel,
    SolutionTypeModel,
    TicketAttachmentModel,
    TicketItemModel,
    TicketModel,
    TicketReadModel,
)
from sac.infrastructure.repositories_attachments import attachment_entity
from sac.infrastructure.repositories_tickets import SqlTicketRepository, _ticket_entity

_CLOSED = [str(s) for s in CLOSED_STATUSES]


def _apply_ticket_filters(
    stmt: Select[Any],
    *,
    brand_id: UUID | None,
    status: TicketStatus | None,
    solution_type_id: UUID | None,
    product_id: UUID | None,
    defect_type_id: UUID | None,
) -> Select[Any]:
    """Filtros de ticket compartilhados por _report_stmt e _media_stmt (marca,
    status, tipo de solucao e os dois EXISTS sobre ticket_items)."""
    if brand_id is not None:
        stmt = stmt.where(TicketModel.brand_id == brand_id)
    if status is not None:
        stmt = stmt.where(TicketModel.status == str(status))
    if solution_type_id is not None:
        stmt = stmt.where(TicketModel.solution_type_id == solution_type_id)
    if product_id is not None:
        stmt = stmt.where(
            exists(
                select(TicketItemModel.id).where(
                    TicketItemModel.ticket_id == TicketModel.id,
                    TicketItemModel.product_id == product_id,
                )
            )
        )
    if defect_type_id is not None:
        stmt = stmt.where(
            exists(
                select(TicketItemModel.id).where(
                    TicketItemModel.ticket_id == TicketModel.id,
                    TicketItemModel.defect_type_id == defect_type_id,
                )
            )
        )
    return stmt


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_start = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, next_start


class SqlReportingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _conditions(self, brand_id: UUID | None) -> list[ColumnExpressionArgument[bool]]:
        conditions: list[ColumnExpressionArgument[bool]] = [TicketModel.deleted_at.is_(None)]
        if brand_id is not None:
            conditions.append(TicketModel.brand_id == brand_id)
        return conditions

    def _tickets(self, brand_id: UUID | None) -> Select[tuple[TicketModel]]:
        return select(TicketModel).where(*self._conditions(brand_id))

    def _ids(self, stmt: Select[Any]) -> Select[Any]:
        return stmt.with_only_columns(TicketModel.id)

    async def _count(self, stmt: Select[Any]) -> int:
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return int(total or 0)

    def _report_stmt(self, filters: ReportFilters) -> Select[tuple[TicketModel]]:
        stmt = select(TicketModel).where(TicketModel.deleted_at.is_(None))
        if filters.date_from is not None:
            stmt = stmt.where(TicketModel.opened_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(TicketModel.opened_at < filters.date_to)
        stmt = _apply_ticket_filters(
            stmt,
            brand_id=filters.brand_id,
            status=filters.status,
            solution_type_id=filters.solution_type_id,
            product_id=filters.product_id,
            defect_type_id=filters.defect_type_id,
        )
        if filters.attendant_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == filters.attendant_user_id)
        if filters.purchase_channel_id is not None:
            stmt = stmt.where(TicketModel.purchase_channel_id == filters.purchase_channel_id)
        return stmt

    def _media_stmt(self, filters: MediaFilters) -> Select[tuple[TicketAttachmentModel, int]]:
        stmt = (
            select(TicketAttachmentModel, TicketModel.number)
            .join(TicketModel, TicketAttachmentModel.ticket_id == TicketModel.id)
            .where(
                TicketAttachmentModel.deleted_at.is_(None),
                TicketAttachmentModel.status == str(AttachmentStatus.DISPONIVEL),
                TicketModel.deleted_at.is_(None),
            )
        )
        if filters.kind is not None:
            stmt = stmt.where(TicketAttachmentModel.kind == str(filters.kind))
        if filters.date_from is not None:
            stmt = stmt.where(TicketAttachmentModel.created_at >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(TicketAttachmentModel.created_at < filters.date_to)
        stmt = _apply_ticket_filters(
            stmt,
            brand_id=filters.brand_id,
            status=filters.status,
            solution_type_id=filters.solution_type_id,
            product_id=filters.product_id,
            defect_type_id=filters.defect_type_id,
        )
        if filters.attendant_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == filters.attendant_user_id)
        return stmt

    async def list_media(
        self, filters: MediaFilters, page: int, per_page: int
    ) -> tuple[list[MediaItemRow], int]:
        stmt = self._media_stmt(filters)
        total = await self._count(stmt)
        rows_stmt = (
            stmt.order_by(TicketAttachmentModel.created_at.desc(), TicketAttachmentModel.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(rows_stmt)
        rows = [
            MediaItemRow(
                attachment=attachment_entity(m), ticket_number=number, created_at=m.created_at
            )
            for m, number in result.all()
        ]
        return rows, total

    async def dashboard(
        self,
        brand_id: UUID | None,
        unread_for: UUID,
        now: datetime,
        owner_user_id: UUID | None = None,
    ) -> DashboardData:
        base = self._tickets(brand_id)
        month_start, month_end = _month_bounds(now)
        kpis = [
            DashboardKpi("total", await self._count(base), {}),
            DashboardKpi(
                "abertos",
                await self._count(base.where(TicketModel.status == str(TicketStatus.ABERTO))),
                {"status": "aberto"},
            ),
            DashboardKpi(
                "aguardando_analise",
                await self._count(
                    base.where(TicketModel.status == str(TicketStatus.AGUARDANDO_ANALISE))
                ),
                {"status": "aguardando_analise"},
            ),
            DashboardKpi(
                "atrasados",
                await self._count(
                    base.where(TicketModel.due_at < now, TicketModel.status.not_in(_CLOSED))
                ),
                {"overdue": "1"},
            ),
            # Os 3 KPIs "no_mes" abaixo contam pelo timestamp do marco (approved_at/
            # declined_at/closed_at), mas o filtro do card clicavel busca pelo status
            # ATUAL do ticket. Um ticket aprovado e depois finalizado no mesmo mes
            # entra na contagem de aprovados_no_mes mas nao aparece na lista filtrada
            # por status=aprovado (o status atual dele e finalizado). Aproximacao
            # intencional, mantida do comportamento do sistema legado.
            DashboardKpi(
                "aprovados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.approved_at >= month_start,
                        TicketModel.approved_at < month_end,
                    )
                ),
                {"status": "aprovado"},
            ),
            DashboardKpi(
                "declinados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.declined_at >= month_start,
                        TicketModel.declined_at < month_end,
                    )
                ),
                {"status": "declinado"},
            ),
            DashboardKpi(
                "finalizados_no_mes",
                await self._count(
                    base.where(
                        TicketModel.status == str(TicketStatus.FINALIZADO),
                        TicketModel.closed_at >= month_start,
                        TicketModel.closed_at < month_end,
                    )
                ),
                {"status": "finalizado"},
            ),
        ]

        status_rows = await self._session.execute(
            select(TicketModel.status, func.count())
            .where(*self._conditions(brand_id))
            .group_by(TicketModel.status)
        )
        status_counts = {s: 0 for s in TicketStatus}
        for status, count in status_rows.all():
            status_counts[TicketStatus(status)] = int(count)

        base_ids = self._ids(base)
        products = await self._ranking_items(base_ids, ProductModel, TicketItemModel.product_id)
        defects = await self._ranking_items(
            base_ids, DefectTypeModel, TicketItemModel.defect_type_id
        )
        solutions = await self._ranking_solutions(base_ids)

        avg_seconds = await self._session.scalar(
            select(
                func.avg(func.extract("epoch", TicketModel.closed_at - TicketModel.opened_at))
            ).where(
                *self._conditions(brand_id),
                TicketModel.status == str(TicketStatus.FINALIZADO),
                TicketModel.closed_at.is_not(None),
            )
        )

        # KPIs, distribuicao por status e rankings acima permanecem tenant-wide
        # (visao gerencial consolidada); so a lista "recent", exibida linha a
        # linha, e restrita ao proprio actor quando ele nao pode ver tudo.
        recent, _ = await SqlTicketRepository(self._session).list(
            TicketFilters(brand_id=brand_id, attendant_user_id=owner_user_id),
            page=1,
            per_page=10,
            sort="last_activity_at",
            order="desc",
            unread_for=unread_for,
        )

        return DashboardData(
            kpis=kpis,
            status_counts=status_counts,
            products=products,
            defects=defects,
            solutions=solutions,
            avg_resolution_hours=float(avg_seconds) / 3600 if avg_seconds is not None else None,
            recent=recent,
        )

    async def _ranking_items(
        self,
        base_ids: Select[Any],
        model: type[Any],
        fk: InstrumentedAttribute[UUID],
    ) -> list[RankingEntry]:
        stmt = (
            select(model.id, model.name, func.sum(TicketItemModel.quantity))
            .join(TicketItemModel, fk == model.id)
            .where(TicketItemModel.ticket_id.in_(base_ids))
            .group_by(model.id, model.name)
            .order_by(func.sum(TicketItemModel.quantity).desc(), model.name.asc())
            .limit(5)
        )
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]

    async def _ranking_solutions(self, base_ids: Select[Any]) -> list[RankingEntry]:
        stmt = (
            select(SolutionTypeModel.id, SolutionTypeModel.name, func.count())
            .join(TicketModel, TicketModel.solution_type_id == SolutionTypeModel.id)
            .where(TicketModel.id.in_(base_ids))
            .group_by(SolutionTypeModel.id, SolutionTypeModel.name)
            .order_by(func.count().desc(), SolutionTypeModel.name.asc())
            .limit(5)
        )
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]

    async def report(
        self,
        filters: ReportFilters,
        page: int,
        per_page: int,
        unread_for: UUID,
        owner_user_id: UUID | None = None,
    ) -> ReportData:
        stmt = self._report_stmt(filters)
        # KPIs, ranking e tempo medio ficam sobre o recorte tenant-wide (nao
        # entram no escopo do actor) — visao gerencial consolidada, como no
        # legado. Apenas a tabela de tickets abaixo (rows_stmt) e paginada e
        # portanto restrita ao proprio actor quando ele nao pode ver tudo.
        total = await self._count(stmt)
        finalized = await self._count(
            stmt.where(TicketModel.status == str(TicketStatus.FINALIZADO))
        )
        declined = await self._count(stmt.where(TicketModel.status == str(TicketStatus.DECLINADO)))

        base_ids = self._ids(stmt)
        avg_seconds = await self._session.scalar(
            select(
                func.avg(func.extract("epoch", TicketModel.closed_at - TicketModel.opened_at))
            ).where(
                TicketModel.id.in_(base_ids),
                TicketModel.status == str(TicketStatus.FINALIZADO),
                TicketModel.closed_at.is_not(None),
            )
        )
        products = await self._ranking_items(base_ids, ProductModel, TicketItemModel.product_id)
        defects = await self._ranking_items(
            base_ids, DefectTypeModel, TicketItemModel.defect_type_id
        )
        solutions = await self._ranking_solutions(base_ids)

        table_stmt = stmt
        if owner_user_id is not None:
            table_stmt = table_stmt.where(TicketModel.attendant_user_id == owner_user_id)
        table_total = total if owner_user_id is None else await self._count(table_stmt)

        rows_stmt = (
            table_stmt.add_columns(CustomerModel.name, TicketReadModel.last_read_at)
            .outerjoin(CustomerModel, TicketModel.customer_id == CustomerModel.id)
            .outerjoin(
                TicketReadModel,
                (TicketReadModel.ticket_id == TicketModel.id)
                & (TicketReadModel.user_id == unread_for),
            )
            .order_by(TicketModel.opened_at.desc(), TicketModel.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(rows_stmt)
        models: list[tuple[TicketModel, str | None, datetime | None]] = [
            (row[0], row[1], row[2]) for row in result.all()
        ]
        ticket_ids = [m.id for m, _, _ in models]
        counts: dict[UUID, int] = {}
        first_products: dict[UUID, str] = {}
        if ticket_ids:
            count_rows = await self._session.execute(
                select(TicketItemModel.ticket_id, func.count())
                .where(TicketItemModel.ticket_id.in_(ticket_ids))
                .group_by(TicketItemModel.ticket_id)
            )
            counts = {row[0]: int(row[1]) for row in count_rows.all()}
            item_rows = await self._session.execute(
                select(TicketItemModel)
                .where(TicketItemModel.ticket_id.in_(ticket_ids))
                .order_by(TicketItemModel.created_at)
            )
            items = list(item_rows.scalars().all())
            product_ids = {i.product_id for i in items}
            product_names: dict[UUID, str] = {}
            if product_ids:
                product_rows = await self._session.execute(
                    select(ProductModel.id, ProductModel.name).where(
                        ProductModel.id.in_(product_ids)
                    )
                )
                product_names = {r[0]: r[1] for r in product_rows.all()}
            for item in items:
                first_products.setdefault(item.ticket_id, product_names[item.product_id])
        tickets: list[TicketListRow] = [
            TicketListRow(
                ticket=_ticket_entity(m),
                customer_name=customer_name,
                first_product_name=first_products.get(m.id),
                items_count=counts.get(m.id, 0),
                unread=last_read is None or last_read < m.last_activity_at,
            )
            for m, customer_name, last_read in models
        ]

        return ReportData(
            kpis=ReportKpis(
                total=total,
                finalized=finalized,
                declined=declined,
                avg_resolution_hours=float(avg_seconds) / 3600 if avg_seconds is not None else None,
            ),
            products=products,
            defects=defects,
            solutions=solutions,
            tickets=tickets,
            total=table_total,
        )

    async def export_rows(
        self,
        filters: ReportFilters,
        page: int,
        per_page: int,
        owner_user_id: UUID | None = None,
    ) -> list[ReportExportRow]:
        stmt = self._report_stmt(filters)
        if owner_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == owner_user_id)
        rows_stmt = (
            stmt.add_columns(
                BrandModel.name,
                CustomerModel.name,
                CustomerModel.document,
                CustomerModel.phone,
                CustomerModel.email,
                SolutionTypeModel.name,
                PurchaseChannelModel.name,
            )
            .outerjoin(BrandModel, TicketModel.brand_id == BrandModel.id)
            .outerjoin(CustomerModel, TicketModel.customer_id == CustomerModel.id)
            .outerjoin(SolutionTypeModel, TicketModel.solution_type_id == SolutionTypeModel.id)
            .outerjoin(
                PurchaseChannelModel,
                TicketModel.purchase_channel_id == PurchaseChannelModel.id,
            )
            .order_by(TicketModel.opened_at.desc(), TicketModel.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(rows_stmt)
        rows = result.all()
        if not rows:
            return []

        ticket_ids = [row[0].id for row in rows]
        attendant_ids = {row[0].attendant_user_id for row in rows}
        name_rows = await self._session.execute(
            select(UserModel.id, UserModel.name).where(UserModel.id.in_(attendant_ids))
        )
        attendant_names = {r[0]: r[1] for r in name_rows.all()}

        item_rows = await self._session.execute(
            select(TicketItemModel)
            .where(TicketItemModel.ticket_id.in_(ticket_ids))
            .order_by(TicketItemModel.created_at)
        )
        items = list(item_rows.scalars().all())
        product_ids = {i.product_id for i in items}
        defect_ids = {i.defect_type_id for i in items}
        product_names: dict[UUID, str] = {}
        defect_names: dict[UUID, str] = {}
        if product_ids:
            product_rows = await self._session.execute(
                select(ProductModel.id, ProductModel.name).where(ProductModel.id.in_(product_ids))
            )
            product_names = {r[0]: r[1] for r in product_rows.all()}
        if defect_ids:
            defect_rows = await self._session.execute(
                select(DefectTypeModel.id, DefectTypeModel.name).where(
                    DefectTypeModel.id.in_(defect_ids)
                )
            )
            defect_names = {r[0]: r[1] for r in defect_rows.all()}
        products_by_ticket: dict[UUID, list[str]] = defaultdict(list)
        defects_by_ticket: dict[UUID, list[str]] = defaultdict(list)
        for item in items:
            products_by_ticket[item.ticket_id].append(
                f"{product_names[item.product_id]} x{item.quantity}"
            )
            defects_by_ticket[item.ticket_id].append(
                f"{defect_names[item.defect_type_id]} x{item.quantity}"
            )

        export_rows: list[ReportExportRow] = []
        for (
            m,
            brand_name,
            customer_name,
            customer_document,
            customer_phone,
            customer_email,
            solution_name,
            channel_name,
        ) in rows:
            export_rows.append(
                ReportExportRow(
                    number=m.number,
                    brand=brand_name,
                    status=m.status,
                    priority=m.priority,
                    customer_name=customer_name,
                    customer_document=customer_document,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    products="; ".join(products_by_ticket.get(m.id, [])),
                    defects="; ".join(defects_by_ticket.get(m.id, [])),
                    solution=solution_name,
                    channel=channel_name,
                    attendant=attendant_names.get(m.attendant_user_id),
                    order_code=m.order_code,
                    opened_at=m.opened_at,
                    closed_at=m.closed_at,
                )
            )
        return export_rows
