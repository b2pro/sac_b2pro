from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnExpressionArgument, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from sac.application.ports_reporting import DashboardData, DashboardKpi, RankingEntry
from sac.application.ports_tickets import TicketFilters
from sac.domain.tickets import CLOSED_STATUSES, TicketStatus
from sac.infrastructure.models_tenant import (
    DefectTypeModel,
    ProductModel,
    SolutionTypeModel,
    TicketItemModel,
    TicketModel,
)
from sac.infrastructure.repositories_tickets import SqlTicketRepository

_CLOSED = [str(s) for s in CLOSED_STATUSES]


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

    async def _count(self, stmt: Select[Any]) -> int:
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return int(total or 0)

    async def dashboard(
        self, brand_id: UUID | None, unread_for: UUID, now: datetime
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

        products = await self._ranking_items(brand_id, ProductModel, TicketItemModel.product_id)
        defects = await self._ranking_items(
            brand_id, DefectTypeModel, TicketItemModel.defect_type_id
        )
        solutions = await self._ranking_solutions(brand_id)

        avg_seconds = await self._session.scalar(
            select(
                func.avg(func.extract("epoch", TicketModel.closed_at - TicketModel.opened_at))
            ).where(
                *self._conditions(brand_id),
                TicketModel.status == str(TicketStatus.FINALIZADO),
                TicketModel.closed_at.is_not(None),
            )
        )

        recent, _ = await SqlTicketRepository(self._session).list(
            TicketFilters(brand_id=brand_id),
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
        brand_id: UUID | None,
        model: type[Any],
        fk: InstrumentedAttribute[UUID],
    ) -> list[RankingEntry]:
        stmt = (
            select(model.id, model.name, func.sum(TicketItemModel.quantity))
            .join(TicketItemModel, fk == model.id)
            .join(TicketModel, TicketItemModel.ticket_id == TicketModel.id)
            .where(*self._conditions(brand_id))
            .group_by(model.id, model.name)
            .order_by(func.sum(TicketItemModel.quantity).desc(), model.name.asc())
            .limit(5)
        )
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]

    async def _ranking_solutions(self, brand_id: UUID | None) -> list[RankingEntry]:
        stmt = (
            select(SolutionTypeModel.id, SolutionTypeModel.name, func.count())
            .join(TicketModel, TicketModel.solution_type_id == SolutionTypeModel.id)
            .where(*self._conditions(brand_id))
            .group_by(SolutionTypeModel.id, SolutionTypeModel.name)
            .order_by(func.count().desc(), SolutionTypeModel.name.asc())
            .limit(5)
        )
        rows = await self._session.execute(stmt)
        return [RankingEntry(id=r[0], name=r[1], count=int(r[2])) for r in rows.all()]
