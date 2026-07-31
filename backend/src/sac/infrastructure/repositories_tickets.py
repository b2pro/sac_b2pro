from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, String, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.ports_tickets import TicketFilters, TicketItemView, TicketListRow
from sac.domain.documents import normalize_digits
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.tickets import (
    CLOSED_STATUSES,
    ReverseCode,
    SlaPolicy,
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
    TicketTimelineEvent,
    TimelineEventType,
)
from sac.infrastructure.models import UserModel
from sac.infrastructure.models_tenant import (
    CustomerModel,
    DefectTypeModel,
    ProductModel,
    ReverseCodeModel,
    SlaPolicyModel,
    TicketCommentModel,
    TicketItemModel,
    TicketModel,
    TicketReadModel,
    TicketTimelineEventModel,
)
from sac.infrastructure.repositories_cadastros import SqlCustomerRepository

_FK_FIELDS: dict[str, str] = {
    "fk_tickets_brand_id": "brand_id",
    "fk_tickets_customer_id": "customer_id",
    "fk_tickets_purchase_channel_id": "purchase_channel_id",
    "fk_tickets_solution_type_id": "solution_type_id",
    "fk_ticket_items_ticket_id": "ticket_id",
    "fk_ticket_items_product_id": "product_id",
    "fk_ticket_items_defect_type_id": "defect_type_id",
    "fk_ticket_comments_ticket_id": "ticket_id",
    "fk_ticket_comments_reply_to_id": "reply_to_id",
    "fk_ticket_timeline_events_ticket_id": "ticket_id",
    "fk_ticket_reads_ticket_id": "ticket_id",
    "fk_reverse_codes_ticket_id": "ticket_id",
    # o repositorio de anexos tambem usa flush_tickets; sem estas duas entradas
    # uma violacao de constraint de anexo seria re-levantada crua e viraria 500
    "fk_ticket_attachments_ticket_id": "ticket_id",
}
_UNIQUE_CONSTRAINTS: dict[str, str] = {
    "uq_tickets_number": "numero de ticket ja utilizado",
    "uq_sla_policies_priority": "prioridade de SLA ja cadastrada",
}
_CHECK_CONSTRAINTS: dict[str, str] = {
    "ck_ticket_items_quantity": "quantidade minima e 1",
    "ck_ticket_attachments_size": "tamanho de anexo invalido",
}


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = exc.orig
    name = getattr(orig, "constraint_name", None)
    if name:
        return str(name)
    cause = getattr(orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return str(name) if name else None


async def flush_tickets(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        name = _constraint_name(exc)
        if name in _FK_FIELDS:
            raise ValidationError(
                "registro relacionado inexistente", details={"field": _FK_FIELDS[name]}
            ) from exc
        if name in _UNIQUE_CONSTRAINTS:
            raise ConflictError(_UNIQUE_CONSTRAINTS[name]) from exc
        if name in _CHECK_CONSTRAINTS:
            raise ValidationError(_CHECK_CONSTRAINTS[name]) from exc
        raise


def ticket_entity(m: TicketModel) -> Ticket:
    return Ticket(
        id=m.id,
        number=m.number,
        brand_id=m.brand_id,
        status=TicketStatus(m.status),
        priority=TicketPriority(m.priority),
        attendant_user_id=m.attendant_user_id,
        opened_at=m.opened_at,
        due_at=m.due_at,
        last_activity_at=m.last_activity_at,
        customer_id=m.customer_id,
        supervisor_user_id=m.supervisor_user_id,
        purchase_channel_id=m.purchase_channel_id,
        order_code=m.order_code,
        purchase_date=m.purchase_date,
        delivery_date=m.delivery_date,
        description=m.description,
        decision_notes=m.decision_notes,
        final_notes=m.final_notes,
        solution_type_id=m.solution_type_id,
        warranty_order_code=m.warranty_order_code,
        warranty_tracking_code=m.warranty_tracking_code,
        submitted_at=m.submitted_at,
        approved_at=m.approved_at,
        declined_at=m.declined_at,
        closed_at=m.closed_at,
        deleted_at=m.deleted_at,
    )


_TICKET_FIELDS = (
    "brand_id",
    "customer_id",
    "attendant_user_id",
    "supervisor_user_id",
    "purchase_channel_id",
    "order_code",
    "purchase_date",
    "delivery_date",
    "description",
    "decision_notes",
    "final_notes",
    "solution_type_id",
    "warranty_order_code",
    "warranty_tracking_code",
    "opened_at",
    "submitted_at",
    "approved_at",
    "declined_at",
    "closed_at",
    "last_activity_at",
    "due_at",
    "deleted_at",
)

_SORT_COLUMNS = {
    "number": TicketModel.number,
    "opened_at": TicketModel.opened_at,
    "due_at": TicketModel.due_at,
    "last_activity_at": TicketModel.last_activity_at,
}


async def load_item_summaries(
    session: AsyncSession, ticket_ids: list[UUID]
) -> tuple[dict[UUID, int], dict[UUID, str]]:
    """Contagem de itens e nome do primeiro produto de cada ticket informado.

    "Primeiro produto" e o do item de menor `seq`, isto e, o primeiro inserido
    no ticket. A listagem de tickets e a tabela do relatorio exibem essa mesma
    coluna e antes mantinham copias divergentes desta consulta.
    """
    if not ticket_ids:
        return {}, {}
    count_rows = await session.execute(
        select(TicketItemModel.ticket_id, func.count())
        .where(TicketItemModel.ticket_id.in_(ticket_ids))
        .group_by(TicketItemModel.ticket_id)
    )
    counts = {row[0]: int(row[1]) for row in count_rows.all()}
    first_rows = await session.execute(
        select(TicketItemModel.ticket_id, ProductModel.name)
        .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
        .where(TicketItemModel.ticket_id.in_(ticket_ids))
        .order_by(TicketItemModel.ticket_id, TicketItemModel.seq)
        .distinct(TicketItemModel.ticket_id)
    )
    return counts, {row[0]: row[1] for row in first_rows.all()}


class SqlTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, ticket: Ticket) -> Ticket:
        model = TicketModel(id=ticket.id, status=str(ticket.status), priority=str(ticket.priority))
        for field in _TICKET_FIELDS:
            setattr(model, field, getattr(ticket, field))
        self._session.add(model)
        await flush_tickets(self._session)
        await self._session.refresh(model, attribute_names=["number"])
        ticket.number = model.number
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        m = await self._session.get(TicketModel, ticket_id)
        return ticket_entity(m) if m and m.deleted_at is None else None

    async def update(self, ticket: Ticket) -> None:
        m = await self._session.get(TicketModel, ticket.id)
        if m is None:
            raise NotFoundError("ticket nao encontrado")
        m.status = str(ticket.status)
        m.priority = str(ticket.priority)
        for field in _TICKET_FIELDS:
            setattr(m, field, getattr(ticket, field))
        await flush_tickets(self._session)

    def _base_stmt(self, filters: TicketFilters) -> Select[tuple[TicketModel]]:
        stmt = select(TicketModel).where(TicketModel.deleted_at.is_(None))
        if filters.status is not None:
            stmt = stmt.where(TicketModel.status == str(filters.status))
        if filters.brand_id is not None:
            stmt = stmt.where(TicketModel.brand_id == filters.brand_id)
        if filters.customer_id is not None:
            stmt = stmt.where(TicketModel.customer_id == filters.customer_id)
        if filters.priority is not None:
            stmt = stmt.where(TicketModel.priority == str(filters.priority))
        if filters.attendant_user_id is not None:
            stmt = stmt.where(TicketModel.attendant_user_id == filters.attendant_user_id)
        if filters.order_code:
            stmt = stmt.where(TicketModel.order_code.ilike(f"%{filters.order_code}%"))
        if filters.overdue:
            stmt = stmt.where(
                TicketModel.due_at < func.now(),
                TicketModel.status.not_in([str(s) for s in CLOSED_STATUSES]),
            )
        if filters.customer:
            digits = normalize_digits(filters.customer)
            customer_match = (
                or_(
                    CustomerModel.name.ilike(f"%{filters.customer}%"),
                    CustomerModel.document.like(f"%{digits}%"),
                )
                if digits
                else CustomerModel.name.ilike(f"%{filters.customer}%")
            )
            stmt = stmt.where(
                TicketModel.customer_id.in_(select(CustomerModel.id).where(customer_match))
            )
        if filters.product_id is not None:
            stmt = stmt.where(
                exists(
                    select(TicketItemModel.id).where(
                        TicketItemModel.ticket_id == TicketModel.id,
                        TicketItemModel.product_id == filters.product_id,
                    )
                )
            )
        if filters.search:
            term = filters.search.strip().lstrip("#")
            if term:
                targets = [
                    TicketModel.customer_id.in_(
                        select(CustomerModel.id).where(CustomerModel.name.ilike(f"%{term}%"))
                    ),
                    exists(
                        select(TicketItemModel.id)
                        .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
                        .where(
                            TicketItemModel.ticket_id == TicketModel.id,
                            ProductModel.name.ilike(f"%{term}%"),
                        )
                    ),
                    TicketModel.order_code.ilike(f"%{term}%"),
                ]
                if term.isdigit():
                    targets.append(cast(TicketModel.number, String).like(f"{term}%"))
                stmt = stmt.where(or_(*targets))
        return stmt

    async def list(
        self,
        filters: TicketFilters,
        page: int,
        per_page: int,
        sort: str,
        order: str,
        unread_for: UUID,
    ) -> tuple[list[TicketListRow], int]:
        stmt = self._base_stmt(filters)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        column = _SORT_COLUMNS.get(sort, TicketModel.last_activity_at)
        rows_stmt = (
            self._base_stmt(filters)
            .add_columns(CustomerModel.name, TicketReadModel.last_read_at)
            .outerjoin(CustomerModel, TicketModel.customer_id == CustomerModel.id)
            .outerjoin(
                TicketReadModel,
                (TicketReadModel.ticket_id == TicketModel.id)
                & (TicketReadModel.user_id == unread_for),
            )
            .order_by(column.desc() if order == "desc" else column.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(rows_stmt)
        models: list[tuple[TicketModel, str | None, datetime | None]] = [
            (row[0], row[1], row[2]) for row in result.all()
        ]
        ticket_ids = [m.id for m, _, _ in models]
        counts, first_products = await load_item_summaries(self._session, ticket_ids)
        rows = [
            TicketListRow(
                ticket=ticket_entity(m),
                customer_name=customer_name,
                first_product_name=first_products.get(m.id),
                items_count=counts.get(m.id, 0),
                unread=last_read is None or last_read < m.last_activity_at,
            )
            for m, customer_name, last_read in models
        ]
        return rows, int(total or 0)


class SqlTicketItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketItemView]:
        result = await self._session.execute(
            select(TicketItemModel, ProductModel.name, DefectTypeModel.name)
            .join(ProductModel, TicketItemModel.product_id == ProductModel.id)
            .join(DefectTypeModel, TicketItemModel.defect_type_id == DefectTypeModel.id)
            .where(TicketItemModel.ticket_id == ticket_id)
            .order_by(TicketItemModel.seq)
        )
        return [
            TicketItemView(
                item=TicketItem(
                    id=m.id,
                    ticket_id=m.ticket_id,
                    product_id=m.product_id,
                    defect_type_id=m.defect_type_id,
                    quantity=m.quantity,
                ),
                product_name=product_name,
                defect_type_name=defect_name,
            )
            for m, product_name, defect_name in result.all()
        ]

    async def count(self, ticket_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(TicketItemModel.ticket_id == ticket_id)
        )
        return int(total or 0)

    async def get(self, item_id: UUID) -> TicketItem | None:
        m = await self._session.get(TicketItemModel, item_id)
        if m is None:
            return None
        return TicketItem(
            id=m.id,
            ticket_id=m.ticket_id,
            product_id=m.product_id,
            defect_type_id=m.defect_type_id,
            quantity=m.quantity,
        )

    async def add(self, item: TicketItem) -> None:
        self._session.add(
            TicketItemModel(
                id=item.id,
                ticket_id=item.ticket_id,
                product_id=item.product_id,
                defect_type_id=item.defect_type_id,
                quantity=item.quantity,
            )
        )
        await flush_tickets(self._session)

    async def update(self, item: TicketItem) -> None:
        m = await self._session.get(TicketItemModel, item.id)
        if m is None:
            raise NotFoundError("item nao encontrado")
        m.product_id = item.product_id
        m.defect_type_id = item.defect_type_id
        m.quantity = item.quantity
        await flush_tickets(self._session)

    async def remove(self, item_id: UUID) -> None:
        m = await self._session.get(TicketItemModel, item_id)
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)


class SqlTicketCommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketComment]:
        result = await self._session.scalars(
            select(TicketCommentModel)
            .where(TicketCommentModel.ticket_id == ticket_id)
            .order_by(TicketCommentModel.created_at)
        )
        return [
            TicketComment(
                id=m.id,
                ticket_id=m.ticket_id,
                author_user_id=m.author_user_id,
                body=m.body,
                reply_to_id=m.reply_to_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def get(self, comment_id: UUID) -> TicketComment | None:
        m = await self._session.get(TicketCommentModel, comment_id)
        if m is None:
            return None
        return TicketComment(
            id=m.id,
            ticket_id=m.ticket_id,
            author_user_id=m.author_user_id,
            body=m.body,
            reply_to_id=m.reply_to_id,
            created_at=m.created_at,
        )

    async def add(self, comment: TicketComment) -> None:
        self._session.add(
            TicketCommentModel(
                id=comment.id,
                ticket_id=comment.ticket_id,
                author_user_id=comment.author_user_id,
                body=comment.body,
                reply_to_id=comment.reply_to_id,
            )
        )
        await flush_tickets(self._session)


class SqlTimelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[TicketTimelineEvent]:
        result = await self._session.scalars(
            select(TicketTimelineEventModel)
            .where(TicketTimelineEventModel.ticket_id == ticket_id)
            .order_by(TicketTimelineEventModel.created_at)
        )
        return [
            TicketTimelineEvent(
                id=m.id,
                ticket_id=m.ticket_id,
                type=TimelineEventType(m.type),
                title=m.title,
                old_value=m.old_value,
                new_value=m.new_value,
                author_user_id=m.author_user_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def add(self, event: TicketTimelineEvent) -> None:
        self._session.add(
            TicketTimelineEventModel(
                id=event.id,
                ticket_id=event.ticket_id,
                type=str(event.type),
                title=event.title,
                old_value=event.old_value,
                new_value=event.new_value,
                author_user_id=event.author_user_id,
            )
        )
        await flush_tickets(self._session)


class SqlReverseCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_ticket(self, ticket_id: UUID) -> list[ReverseCode]:
        result = await self._session.scalars(
            select(ReverseCodeModel)
            .where(ReverseCodeModel.ticket_id == ticket_id)
            .order_by(ReverseCodeModel.created_at)
        )
        return [
            ReverseCode(
                id=m.id,
                ticket_id=m.ticket_id,
                code=m.code,
                author_user_id=m.author_user_id,
                created_at=m.created_at,
            )
            for m in result
        ]

    async def count(self, ticket_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(ReverseCodeModel.ticket_id == ticket_id)
        )
        return int(total or 0)

    async def get(self, reverse_id: UUID) -> ReverseCode | None:
        m = await self._session.get(ReverseCodeModel, reverse_id)
        if m is None:
            return None
        return ReverseCode(
            id=m.id,
            ticket_id=m.ticket_id,
            code=m.code,
            author_user_id=m.author_user_id,
            created_at=m.created_at,
        )

    async def add(self, reverse: ReverseCode) -> None:
        self._session.add(
            ReverseCodeModel(
                id=reverse.id,
                ticket_id=reverse.ticket_id,
                code=reverse.code,
                author_user_id=reverse.author_user_id,
            )
        )
        await flush_tickets(self._session)

    async def remove(self, reverse_id: UUID) -> None:
        m = await self._session.get(ReverseCodeModel, reverse_id)
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)


class SqlTicketReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_read(self, ticket_id: UUID, user_id: UUID, at: datetime) -> None:
        stmt = (
            pg_insert(TicketReadModel)
            .values(ticket_id=ticket_id, user_id=user_id, last_read_at=at)
            .on_conflict_do_update(
                index_elements=["ticket_id", "user_id"], set_={"last_read_at": at}
            )
        )
        await self._session.execute(stmt)

    async def mark_unread(self, ticket_id: UUID, user_id: UUID) -> None:
        m = await self._session.get(TicketReadModel, (ticket_id, user_id))
        if m is not None:
            await self._session.delete(m)
            await flush_tickets(self._session)

    async def last_read_at(self, ticket_id: UUID, user_id: UUID) -> datetime | None:
        m = await self._session.get(TicketReadModel, (ticket_id, user_id))
        return m.last_read_at if m else None


class SqlSlaPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, priority: TicketPriority) -> SlaPolicy | None:
        m = await self._session.scalar(
            select(SlaPolicyModel).where(SlaPolicyModel.priority == str(priority))
        )
        if m is None:
            return None
        return SlaPolicy(
            priority=TicketPriority(m.priority), hours=m.hours, warn_hours=m.warn_hours
        )


class SqlUserDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def names_by_ids(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        result = await self._session.execute(
            select(UserModel.id, UserModel.name).where(UserModel.id.in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}


@dataclass
class TicketRepos:
    tickets: SqlTicketRepository
    items: SqlTicketItemRepository
    comments: SqlTicketCommentRepository
    timeline: SqlTimelineRepository
    reverses: SqlReverseCodeRepository
    reads: SqlTicketReadRepository
    sla: SqlSlaPolicyRepository
    customers: SqlCustomerRepository
    users: SqlUserDirectory


def build_ticket_repos(session: AsyncSession) -> TicketRepos:
    return TicketRepos(
        tickets=SqlTicketRepository(session),
        items=SqlTicketItemRepository(session),
        comments=SqlTicketCommentRepository(session),
        timeline=SqlTimelineRepository(session),
        reverses=SqlReverseCodeRepository(session),
        reads=SqlTicketReadRepository(session),
        sla=SqlSlaPolicyRepository(session),
        customers=SqlCustomerRepository(session),
        users=SqlUserDirectory(session),
    )
