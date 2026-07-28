from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TenantBase(DeclarativeBase):
    pass


class TenantTableMixin:
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogModelBase(TenantTableMixin, TenantBase):
    __abstract__ = True

    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class BrandModel(CatalogModelBase):
    __tablename__ = "brands"


class DefectTypeModel(CatalogModelBase):
    __tablename__ = "defect_types"


class SolutionTypeModel(CatalogModelBase):
    __tablename__ = "solution_types"


class PurchaseChannelModel(CatalogModelBase):
    __tablename__ = "purchase_channels"


class ProductModel(TenantTableMixin, TenantBase):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    segment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CustomerModel(TenantTableMixin, TenantBase):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200))
    document: Mapped[str] = mapped_column(String(14), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)


TICKET_NUMBER_SEQ = Sequence("ticket_number_seq", schema="tenant")


class TicketModel(TenantBase):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("number", name="uq_tickets_number"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    number: Mapped[int] = mapped_column(
        BigInteger, TICKET_NUMBER_SEQ, server_default=TICKET_NUMBER_SEQ.next_value(), nullable=False
    )
    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.brands.id", name="fk_tickets_brand_id"), nullable=False
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.customers.id", name="fk_tickets_customer_id"), nullable=True
    )
    attendant_user_id: Mapped[UUID] = mapped_column(nullable=False)
    supervisor_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    purchase_channel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.purchase_channels.id", name="fk_tickets_purchase_channel_id"),
        nullable=True,
    )
    order_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.solution_types.id", name="fk_tickets_solution_type_id"),
        nullable=True,
    )
    warranty_order_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    warranty_tracking_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketItemModel(TenantBase):
    __tablename__ = "ticket_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_ticket_items_quantity"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_items_ticket_id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.products.id", name="fk_ticket_items_product_id"), nullable=False
    )
    defect_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.defect_types.id", name="fk_ticket_items_defect_type_id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TicketCommentModel(TenantBase):
    __tablename__ = "ticket_comments"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_comments_ticket_id"), nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(nullable=False)
    reply_to_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant.ticket_comments.id", name="fk_ticket_comments_reply_to_id"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketTimelineEventModel(TenantBase):
    __tablename__ = "ticket_timeline_events"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_timeline_events_ticket_id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketReadModel(TenantBase):
    __tablename__ = "ticket_reads"
    __table_args__ = (
        PrimaryKeyConstraint("ticket_id", "user_id", name="pk_ticket_reads"),
        {"schema": "tenant"},
    )

    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_reads_ticket_id")
    )
    user_id: Mapped[UUID] = mapped_column()
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReverseCodeModel(TenantBase):
    __tablename__ = "reverse_codes"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_reverse_codes_ticket_id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    author_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SlaPolicyModel(TenantBase):
    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint("priority", name="uq_sla_policies_priority"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
