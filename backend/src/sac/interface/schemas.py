from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from sac.application.ports_cadastros import CepAddress
from sac.application.ports_tickets import (
    TicketCounters,
    TicketDetail,
    TicketItemView,
    TicketListRow,
)
from sac.application.use_cases.attachments import AttachmentView, IntentDiscardResult
from sac.application.use_cases.auth import AuthResult
from sac.domain.attachments import AttachmentKind, PreviewStatus
from sac.domain.cadastros import Customer, Product
from sac.domain.catalog import CatalogItem
from sac.domain.entities import Tenant, TenantStatus
from sac.domain.notifications import Notification, NotificationType
from sac.domain.permissions import Role
from sac.domain.tickets import (
    SlaState,
    Ticket,
    TicketPriority,
    TicketStatus,
    TimelineEventType,
    is_closed,
    sla_state,
)


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    is_super_admin: bool
    active: bool


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant_slug: str | None
    role: str | None


def login_out(result: AuthResult) -> LoginOut:
    return LoginOut(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=UserOut(
            id=result.user.id,
            name=result.user.name,
            email=result.user.email,
            is_super_admin=result.user.is_super_admin,
            active=result.user.active,
        ),
        tenant_slug=result.tenant_slug,
        role=result.role.value if result.role else None,
    )


class TenantCreateIn(BaseModel):
    slug: str
    name: str
    modules: dict[str, bool] = Field(default_factory=dict)


class TenantStatusIn(BaseModel):
    status: TenantStatus


class TenantModulesIn(BaseModel):
    modules: dict[str, bool]


class TenantOut(BaseModel):
    id: UUID
    slug: str
    name: str
    status: TenantStatus
    modules: dict[str, bool]


def tenant_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        status=tenant.status,
        modules=tenant.modules,
    )


class UserCreateIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    is_super_admin: bool = False


class UserActiveIn(BaseModel):
    active: bool


class PasswordResetIn(BaseModel):
    password: str


class LinkCreateIn(BaseModel):
    user_id: UUID
    role: Role


class LinkOut(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: Role
    active: bool


class CatalogItemIn(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None


class CatalogItemOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    active: bool


class ActiveIn(BaseModel):
    active: bool


def catalog_out(item: CatalogItem) -> CatalogItemOut:
    return CatalogItemOut(
        id=item.id, name=item.name, description=item.description, active=item.active
    )


class CustomerIn(BaseModel):
    name: str = Field(max_length=200)
    document: str = Field(max_length=18)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    cep: str | None = Field(default=None, max_length=9)
    street: str | None = Field(default=None, max_length=200)
    number: str | None = Field(default=None, max_length=20)
    complement: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=2)


class CustomerOut(BaseModel):
    id: UUID
    name: str
    document: str
    phone: str | None
    email: str | None
    cep: str | None
    street: str | None
    number: str | None
    complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    active: bool


class CustomersPageOut(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    per_page: int


class ProductIn(BaseModel):
    name: str = Field(max_length=200)
    sku: str = Field(max_length=80)
    segment: str | None = Field(default=None, max_length=80)
    description: str | None = None


class ProductOut(BaseModel):
    id: UUID
    name: str
    sku: str
    segment: str | None
    description: str | None
    photo_key: str | None
    photo_preview_key: str | None
    photo_url: str | None
    active: bool


class ProductsPageOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    per_page: int


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut.model_validate(customer, from_attributes=True)


def product_out(product: Product, photo_url: str | None = None) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        segment=product.segment,
        description=product.description,
        photo_key=product.photo_key,
        photo_preview_key=product.photo_preview_key,
        photo_url=photo_url,
        active=product.active,
    )


class CepOut(BaseModel):
    cep: str
    street: str
    neighborhood: str
    city: str
    state: str


def cep_out(address: CepAddress) -> CepOut:
    return CepOut(
        cep=address.cep,
        street=address.street,
        neighborhood=address.neighborhood,
        city=address.city,
        state=address.state,
    )


class TicketItemIn(BaseModel):
    product_id: UUID
    defect_type_id: UUID
    quantity: int = Field(default=1, ge=1)


class TicketIn(BaseModel):
    brand_id: UUID
    priority: TicketPriority
    customer: CustomerIn | None = None
    customer_id: UUID | None = None
    attendant_user_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = Field(default=None, max_length=60)
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None
    items: list[TicketItemIn] = Field(default_factory=list)


class ApproveIn(BaseModel):
    notes: str | None = None


class DeclineIn(BaseModel):
    reason: str = Field(min_length=1)


class CancelIn(BaseModel):
    reason: str | None = None


class FinalizeIn(BaseModel):
    solution_type_id: UUID
    notes: str | None = None


class ReverseIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)


class WarrantyIn(BaseModel):
    order_code: str = Field(min_length=1, max_length=60)
    tracking_code: str | None = Field(default=None, max_length=60)


class CommentIn(BaseModel):
    body: str = Field(min_length=1)
    reply_to_id: UUID | None = None


class TicketUpdateIn(BaseModel):
    brand_id: UUID
    priority: TicketPriority
    customer_id: UUID | None = None
    # omitido/None: nao mexe no atendente. Reatribuir exige
    # EDITAR_QUALQUER_TICKET (ver UpdateTicketUseCase).
    attendant_user_id: UUID | None = None
    supervisor_user_id: UUID | None = None
    purchase_channel_id: UUID | None = None
    order_code: str | None = Field(default=None, max_length=60)
    purchase_date: date | None = None
    delivery_date: date | None = None
    description: str | None = None


class TicketOut(BaseModel):
    id: UUID
    number: int
    status: TicketStatus
    priority: TicketPriority
    sla: SlaState
    brand_id: UUID
    customer_id: UUID | None
    attendant_user_id: UUID
    supervisor_user_id: UUID | None
    purchase_channel_id: UUID | None
    order_code: str | None
    purchase_date: date | None
    delivery_date: date | None
    description: str | None
    decision_notes: str | None
    final_notes: str | None
    solution_type_id: UUID | None
    warranty_order_code: str | None
    warranty_tracking_code: str | None
    opened_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    declined_at: datetime | None
    closed_at: datetime | None
    last_activity_at: datetime
    due_at: datetime


def ticket_out(ticket: Ticket) -> TicketOut:
    now = datetime.now(UTC)
    return TicketOut(
        id=ticket.id,
        number=ticket.number,
        status=ticket.status,
        priority=ticket.priority,
        sla=sla_state(now, ticket.due_at, is_closed(ticket)),
        brand_id=ticket.brand_id,
        customer_id=ticket.customer_id,
        attendant_user_id=ticket.attendant_user_id,
        supervisor_user_id=ticket.supervisor_user_id,
        purchase_channel_id=ticket.purchase_channel_id,
        order_code=ticket.order_code,
        purchase_date=ticket.purchase_date,
        delivery_date=ticket.delivery_date,
        description=ticket.description,
        decision_notes=ticket.decision_notes,
        final_notes=ticket.final_notes,
        solution_type_id=ticket.solution_type_id,
        warranty_order_code=ticket.warranty_order_code,
        warranty_tracking_code=ticket.warranty_tracking_code,
        opened_at=ticket.opened_at,
        submitted_at=ticket.submitted_at,
        approved_at=ticket.approved_at,
        declined_at=ticket.declined_at,
        closed_at=ticket.closed_at,
        last_activity_at=ticket.last_activity_at,
        due_at=ticket.due_at,
    )


class TicketListItemOut(BaseModel):
    id: UUID
    number: int
    status: TicketStatus
    priority: TicketPriority
    sla: SlaState
    due_at: datetime
    customer_name: str | None
    first_product_name: str | None
    items_count: int
    attendant_name: str | None
    opened_at: datetime
    last_activity_at: datetime
    unread: bool


class TicketsPageOut(BaseModel):
    items: list[TicketListItemOut]
    total: int
    page: int
    per_page: int


def ticket_list_item_out(row: TicketListRow) -> TicketListItemOut:
    t = row.ticket
    now = datetime.now(UTC)
    return TicketListItemOut(
        id=t.id,
        number=t.number,
        status=t.status,
        priority=t.priority,
        sla=sla_state(now, t.due_at, is_closed(t)),
        due_at=t.due_at,
        customer_name=row.customer_name,
        first_product_name=row.first_product_name,
        items_count=row.items_count,
        attendant_name=row.attendant_name,
        opened_at=t.opened_at,
        last_activity_at=t.last_activity_at,
        unread=row.unread,
    )


class TicketCountersOut(BaseModel):
    todos: int
    ativos: int
    abertos: int
    aguardando_analise: int
    atrasados: int
    nao_lidos: int
    meus: int


def ticket_counters_out(counters: TicketCounters) -> TicketCountersOut:
    return TicketCountersOut(
        todos=counters.todos,
        ativos=counters.ativos,
        abertos=counters.abertos,
        aguardando_analise=counters.aguardando_analise,
        atrasados=counters.atrasados,
        nao_lidos=counters.nao_lidos,
        meus=counters.meus,
    )


class TicketItemOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    defect_type_id: UUID
    defect_type_name: str
    quantity: int


def ticket_item_out(view: TicketItemView) -> TicketItemOut:
    return TicketItemOut(
        id=view.item.id,
        product_id=view.item.product_id,
        product_name=view.product_name,
        defect_type_id=view.item.defect_type_id,
        defect_type_name=view.defect_type_name,
        quantity=view.item.quantity,
    )


class TicketCommentOut(BaseModel):
    id: UUID
    author_user_id: UUID
    author_name: str | None
    body: str
    reply_to_id: UUID | None
    created_at: datetime | None


class TimelineEventOut(BaseModel):
    id: UUID
    type: TimelineEventType
    title: str
    old_value: str | None
    new_value: str | None
    author_user_id: UUID | None
    author_name: str | None
    created_at: datetime | None


class ReverseCodeOut(BaseModel):
    id: UUID
    code: str
    author_user_id: UUID | None
    author_name: str | None
    created_at: datetime | None


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    customer: CustomerOut | None
    attendant_name: str | None
    supervisor_name: str | None
    items: list[TicketItemOut]
    comments: list[TicketCommentOut]
    timeline: list[TimelineEventOut]
    reverses: list[ReverseCodeOut]


def ticket_detail_out(detail: TicketDetail) -> TicketDetailOut:
    names = detail.user_names
    t = detail.ticket
    return TicketDetailOut(
        ticket=ticket_out(t),
        customer=customer_out(detail.customer) if detail.customer else None,
        attendant_name=names.get(t.attendant_user_id),
        supervisor_name=(names.get(t.supervisor_user_id) if t.supervisor_user_id else None),
        items=[ticket_item_out(i) for i in detail.items],
        comments=[
            TicketCommentOut(
                id=c.id,
                author_user_id=c.author_user_id,
                author_name=names.get(c.author_user_id),
                body=c.body,
                reply_to_id=c.reply_to_id,
                created_at=c.created_at,
            )
            for c in detail.comments
        ],
        timeline=[
            TimelineEventOut(
                id=e.id,
                type=e.type,
                title=e.title,
                old_value=e.old_value,
                new_value=e.new_value,
                author_user_id=e.author_user_id,
                author_name=names.get(e.author_user_id) if e.author_user_id else None,
                created_at=e.created_at,
            )
            for e in detail.timeline
        ],
        reverses=[
            ReverseCodeOut(
                id=r.id,
                code=r.code,
                author_user_id=r.author_user_id,
                author_name=names.get(r.author_user_id) if r.author_user_id else None,
                created_at=r.created_at,
            )
            for r in detail.reverses
        ],
    )


class AttachmentIntentIn(BaseModel):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    with_preview: bool = False


class AttachmentIntentOut(BaseModel):
    attachment_id: UUID
    object_key: str
    upload_url: str
    expires_in: int
    preview_upload_url: str | None


class AttachmentOut(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    kind: AttachmentKind
    preview_status: PreviewStatus
    preview_url: str | None
    author_user_id: UUID
    author_name: str | None
    created_at: datetime | None


class AttachmentUrlOut(BaseModel):
    url: str
    expires_in: int


class AttachmentIntentDiscardOut(BaseModel):
    """`descartado` quando a vaga voltou para a cota; `disponivel` quando o
    upload na verdade tinha sido confirmado e nada foi apagado.
    """

    status: IntentDiscardResult


def attachment_out(view: AttachmentView, author_name: str | None) -> AttachmentOut:
    a = view.attachment
    return AttachmentOut(
        id=a.id,
        filename=a.filename,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        kind=a.kind,
        preview_status=a.preview_status,
        preview_url=view.preview_url,
        author_user_id=a.author_user_id,
        author_name=author_name,
        created_at=a.created_at,
    )


class PhotoIntentIn(BaseModel):
    content_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)


class PhotoIntentOut(BaseModel):
    object_key: str
    upload_url: str
    expires_in: int


class PhotoConfirmIn(BaseModel):
    object_key: str = Field(max_length=400)


class MemberOut(BaseModel):
    id: UUID
    name: str
    role: Role
    active: bool


class NotificationOut(BaseModel):
    id: UUID
    ticket_id: UUID
    ticket_number: int
    type: NotificationType
    title: str
    snippet: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationsPageOut(BaseModel):
    items: list[NotificationOut]
    total: int


class NotificationCounterOut(BaseModel):
    nao_lidas: int


class MarkNotificationsReadIn(BaseModel):
    ids: list[UUID] | None = None


def notification_out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        ticket_id=notification.ticket_id,
        ticket_number=notification.ticket_number,
        type=notification.type,
        title=notification.title,
        snippet=notification.snippet,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )
