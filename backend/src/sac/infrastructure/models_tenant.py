from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    photo_preview_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


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


_ALIVE = text("deleted_at IS NULL")


class TicketModel(TenantBase):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("number", name="uq_tickets_number"),
        # deleted_at (exclusao logica) e o filtro base de toda query de ticket,
        # mas 99% das linhas o satisfazem: como coluna lider de b-tree custaria
        # 8 bytes por entrada sem seletividade nenhuma. Entra como PREDICADO
        # PARCIAL, que alem de encolher o indice dispensa a recheck de
        # deleted_at no heap. Racional medido em 0007_indices_parciais.
        Index("ix_tickets_status", "status", postgresql_where=_ALIVE),
        # brand_id nao restringe linhas (so ha duas marcas), mas cobre a
        # contagem do dashboard por marca em Index Only Scan.
        Index("ix_tickets_brand_id", "brand_id", postgresql_where=_ALIVE),
        # opened_at ordena a tabela do relatorio e o export CSV (ORDER BY
        # opened_at DESC, id) alem de filtrar o periodo.
        Index("ix_tickets_opened_at", "opened_at", postgresql_where=_ALIVE),
        # last_activity_at e due_at sao colunas de ordenacao da lista de tickets
        # (_SORT_COLUMNS); customer_id e attendant_user_id sao filtros dela.
        Index("ix_tickets_last_activity_at", "last_activity_at", postgresql_where=_ALIVE),
        Index("ix_tickets_due_at", "due_at", postgresql_where=_ALIVE),
        Index("ix_tickets_customer_id", "customer_id", postgresql_where=_ALIVE),
        Index("ix_tickets_attendant_user_id", "attendant_user_id", postgresql_where=_ALIVE),
        # Nao ha indice de closed_at (o tempo medio de resolucao entra por
        # status, e closed_at IS NOT NULL nao filtra nada dentro de
        # finalizado). Tampouco de approved_at/declined_at: elas so aparecem em
        # count(*) FILTER (...) no dashboard, e FILTER de agregado e avaliado
        # linha a linha depois da varredura — nunca como predicado de indice.
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # server_default aqui e apenas um marcador para o mapper incluir "number" no
    # RETURNING do INSERT (eager_defaults="auto" so considera server_default/clause
    # element). Sem isso, o atributo fica nao carregado apos o flush e o proximo
    # acesso dispara um reload sincrono, incompativel com AsyncSession
    # (MissingGreenlet). O valor em si sempre vem da Sequence embutida no INSERT
    # (TICKET_NUMBER_SEQ); o DDL real (migration 0003_tickets) NAO cria um DEFAULT
    # de coluna no banco.
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


TICKET_ITEM_SEQ = Sequence("ticket_item_seq", schema="tenant")


class TicketItemModel(TenantBase):
    __tablename__ = "ticket_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_ticket_items_quantity"),
        # Nao e parcial: ticket_items nao tem deleted_at (o item some junto com
        # o ticket). Serve tanto o load_item_summaries quanto a FK.
        Index("ix_ticket_items_ticket_id", "ticket_id"),
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
    # Ordem de insercao dos itens dentro do ticket. created_at nao serve: o
    # server_default e transaction_timestamp(), entao todos os itens gravados na
    # mesma transacao empatam e o "primeiro produto" fica indeterminado. O valor
    # vem da Sequence embutida no INSERT (TICKET_ITEM_SEQ) e o server_default
    # aqui e apenas o marcador que faz o mapper trazer a coluna no RETURNING -
    # mesma mecanica descrita em TicketModel.number.
    seq: Mapped[int] = mapped_column(
        BigInteger, TICKET_ITEM_SEQ, server_default=TICKET_ITEM_SEQ.next_value(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TicketCommentModel(TenantBase):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        Index("ix_ticket_comments_ticket_id", "ticket_id"),
        {"schema": "tenant"},
    )

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
    __table_args__ = (
        Index("ix_ticket_timeline_events_ticket_id", "ticket_id"),
        {"schema": "tenant"},
    )

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
    __table_args__ = (
        Index("ix_reverse_codes_ticket_id", "ticket_id"),
        {"schema": "tenant"},
    )

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


class NotificationModel(TenantBase):
    __tablename__ = "notifications"
    __table_args__ = (
        # Cobre o dropdown: contagem/lista de nao lidas de um usuario. Parcial
        # porque read_at IS NULL e a minoria depois de algum uso — a maioria
        # das notificacoes acaba lida — entao o indice fica pequeno e ainda
        # dispensa recheck de read_at no heap (mesmo racional de _ALIVE em
        # TicketModel).
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        # Cobre a lista paginada (lidas + nao lidas) ordenada por created_at
        # desc: sem read_at IS NULL no filtro, entao nao pode reusar o parcial
        # acima.
        Index("ix_notifications_user_created", "user_id", "created_at"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_notifications_ticket_id"), nullable=False
    )
    # desnormalizado do ticket (ver domain/notifications.py): dispensa join no
    # dropdown e nunca diverge, pois number e imutavel apos a criacao do ticket.
    ticket_number: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    snippet: Mapped[str | None] = mapped_column(String(200))
    actor_user_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketAttachmentModel(TenantBase):
    __tablename__ = "ticket_attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_ticket_attachments_size"),
        Index("ix_ticket_attachments_ticket_id", "ticket_id"),
        # NAO e parcial em deleted_at, ao contrario dos indices de tickets: o
        # varredor de anexos pendentes (list_pending_before) filtra apenas
        # status e created_at, sem deleted_at, e nao alcancaria um indice
        # parcial. Nesta forma o indice serve as duas consultas — a galeria usa
        # o prefixo status mais a ordenacao por created_at, o varredor usa o
        # prefixo status — e dispensa um segundo indice so de status.
        Index("ix_ticket_attachments_status_created_at", "status", "created_at"),
        {"schema": "tenant"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.tickets.id", name="fk_ticket_attachments_ticket_id"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(400), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    preview_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    preview_medium_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    preview_status: Mapped[str] = mapped_column(String(12), nullable=False)
    author_user_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
