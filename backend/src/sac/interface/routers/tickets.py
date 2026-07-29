from uuid import UUID

from fastapi import APIRouter, Depends, Response

from sac.application.ports import TokenPayload
from sac.application.ports_tickets import TicketActor, TicketFilters
from sac.application.use_cases.attachments import (
    ConfirmUploadUseCase,
    DeleteAttachmentUseCase,
    GetAttachmentUrlUseCase,
    ListAttachmentsUseCase,
    RequestUploadUseCase,
    UploadIntentInput,
)
from sac.application.use_cases.customers import CustomerInput
from sac.application.use_cases.tickets_crud import (
    AddCommentUseCase,
    AddTicketItemUseCase,
    CreateTicketInput,
    CreateTicketUseCase,
    RemoveTicketItemUseCase,
    TicketItemInput,
    UpdateTicketInput,
    UpdateTicketItemUseCase,
    UpdateTicketUseCase,
)
from sac.application.use_cases.tickets_queries import (
    GetTicketDetailUseCase,
    ListTicketsUseCase,
    MarkTicketUnreadUseCase,
)
from sac.application.use_cases.tickets_workflow import (
    ApproveTicketUseCase,
    CancelTicketUseCase,
    DeclineTicketUseCase,
    DeleteReverseUseCase,
    FinalizeTicketUseCase,
    HoldForCustomerUseCase,
    ReceiveProductUseCase,
    RegisterReverseUseCase,
    ReopenTicketUseCase,
    ResumeTicketUseCase,
    SetWarrantyUseCase,
    SubmitTicketUseCase,
)
from sac.domain.permissions import Permission
from sac.domain.tickets import TicketPriority, TicketStatus
from sac.infrastructure.repositories_attachments import AttachmentRepos
from sac.infrastructure.repositories_tickets import TicketRepos
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.interface.deps import (
    get_attachment_repos,
    get_settings,
    get_storage,
    get_tenant_slug,
    get_ticket_repos,
    require_any_permission,
    require_permission,
)
from sac.interface.schemas import (
    ApproveIn,
    AttachmentIntentIn,
    AttachmentIntentOut,
    AttachmentOut,
    AttachmentUrlOut,
    CancelIn,
    CommentIn,
    DeclineIn,
    FinalizeIn,
    ReverseCodeOut,
    ReverseIn,
    TicketCommentOut,
    TicketDetailOut,
    TicketIn,
    TicketItemIn,
    TicketItemOut,
    TicketOut,
    TicketsPageOut,
    TicketUpdateIn,
    WarrantyIn,
    attachment_out,
    ticket_detail_out,
    ticket_item_out,
    ticket_list_item_out,
    ticket_out,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

_create = require_permission(Permission.CRIAR_TICKET)
_read = require_any_permission(Permission.VER_TODOS_TICKETS, Permission.VER_PROPRIOS_TICKETS)
_edit = require_any_permission(Permission.EDITAR_QUALQUER_TICKET, Permission.EDITAR_PROPRIO_TICKET)
_submit = require_permission(Permission.ENVIAR_PARA_ANALISE)
_decide = require_permission(Permission.DECIDIR_TICKET)
_operate = require_any_permission(
    Permission.OPERAR_LOGISTICA_TODOS, Permission.OPERAR_LOGISTICA_PROPRIOS
)
_comment = require_permission(Permission.COMENTAR_ANEXAR)
_attach = require_permission(Permission.COMENTAR_ANEXAR)


def _actor(identity: TokenPayload) -> TicketActor:
    assert identity.role is not None  # garantido pelas dependencies de permissao
    return TicketActor(user_id=identity.user_id, role=identity.role)


def _item_input(body: TicketItemIn) -> TicketItemInput:
    return TicketItemInput(
        product_id=body.product_id,
        defect_type_id=body.defect_type_id,
        quantity=body.quantity,
    )


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketIn,
    identity: TokenPayload = Depends(_create),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    customer_input = (
        CustomerInput(
            name=body.customer.name,
            document=body.customer.document,
            phone=body.customer.phone,
            email=body.customer.email,
            cep=body.customer.cep,
            street=body.customer.street,
            number=body.customer.number,
            complement=body.customer.complement,
            neighborhood=body.customer.neighborhood,
            city=body.customer.city,
            state=body.customer.state,
        )
        if body.customer is not None
        else None
    )
    data = CreateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer=customer_input,
        customer_id=body.customer_id,
        attendant_user_id=body.attendant_user_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
        items=tuple(_item_input(i) for i in body.items),
    )
    use_case = CreateTicketUseCase(
        repos.tickets, repos.items, repos.customers, repos.sla, repos.timeline, repos.reads
    )
    return ticket_out(await use_case.execute(_actor(identity), data))


@router.get("", response_model=TicketsPageOut)
async def list_tickets(
    status: TicketStatus | None = None,
    brand_id: UUID | None = None,
    customer: str | None = None,
    customer_id: UUID | None = None,
    product_id: UUID | None = None,
    order_code: str | None = None,
    priority: TicketPriority | None = None,
    overdue: bool = False,
    page: int = 1,
    per_page: int = 20,
    sort: str = "last_activity_at",
    order: str = "desc",
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketsPageOut:
    filters = TicketFilters(
        status=status,
        brand_id=brand_id,
        customer=customer,
        customer_id=customer_id,
        product_id=product_id,
        order_code=order_code,
        priority=priority,
        overdue=overdue,
    )
    rows, total = await ListTicketsUseCase(repos.tickets, repos.users).execute(
        _actor(identity), filters, page, per_page, sort, order
    )
    return TicketsPageOut(
        items=[ticket_list_item_out(r) for r in rows],
        total=total,
        page=max(page, 1),
        per_page=min(max(per_page, 1), 100),
    )


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket_detail(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketDetailOut:
    use_case = GetTicketDetailUseCase(
        repos.tickets,
        repos.items,
        repos.comments,
        repos.timeline,
        repos.reverses,
        repos.reads,
        repos.customers,
        repos.users,
    )
    return ticket_detail_out(await use_case.execute(_actor(identity), ticket_id))


@router.put("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    body: TicketUpdateIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    data = UpdateTicketInput(
        brand_id=body.brand_id,
        priority=body.priority,
        customer_id=body.customer_id,
        supervisor_user_id=body.supervisor_user_id,
        purchase_channel_id=body.purchase_channel_id,
        order_code=body.order_code,
        purchase_date=body.purchase_date,
        delivery_date=body.delivery_date,
        description=body.description,
    )
    use_case = UpdateTicketUseCase(repos.tickets, repos.customers, repos.sla, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, data))


@router.post("/{ticket_id}/itens", response_model=TicketItemOut, status_code=201)
async def add_ticket_item(
    ticket_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await AddTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, _item_input(body)
    )
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.put("/{ticket_id}/itens/{item_id}", response_model=TicketItemOut)
async def update_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    body: TicketItemIn,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketItemOut:
    item = await UpdateTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, item_id, _item_input(body)
    )
    views = await repos.items.list_by_ticket(ticket_id)
    view = next(v for v in views if v.item.id == item.id)
    return ticket_item_out(view)


@router.delete("/{ticket_id}/itens/{item_id}", status_code=204)
async def remove_ticket_item(
    ticket_id: UUID,
    item_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    await RemoveTicketItemUseCase(repos.tickets, repos.items, repos.timeline).execute(
        _actor(identity), ticket_id, item_id
    )
    return Response(status_code=204)


@router.post("/{ticket_id}/enviar-analise", response_model=TicketOut)
async def submit_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_submit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = SubmitTicketUseCase(repos.tickets, repos.items, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/aprovar", response_model=TicketOut)
async def approve_ticket(
    ticket_id: UUID,
    body: ApproveIn,
    identity: TokenPayload = Depends(_decide),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ApproveTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, notes=body.notes))


@router.post("/{ticket_id}/declinar", response_model=TicketOut)
async def decline_ticket(
    ticket_id: UUID,
    body: DeclineIn,
    identity: TokenPayload = Depends(_decide),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = DeclineTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, reason=body.reason))


@router.post("/{ticket_id}/cancelar", response_model=TicketOut)
async def cancel_ticket(
    ticket_id: UUID,
    body: CancelIn,
    identity: TokenPayload = Depends(_decide),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = CancelTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id, reason=body.reason))


@router.post("/{ticket_id}/reabrir", response_model=TicketOut)
async def reopen_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_decide),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ReopenTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/aguardar-cliente", response_model=TicketOut)
async def hold_for_customer(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = HoldForCustomerUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/retomar", response_model=TicketOut)
async def resume_ticket(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_edit),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ResumeTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/produto-recebido", response_model=TicketOut)
async def receive_product(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = ReceiveProductUseCase(repos.tickets, repos.timeline)
    return ticket_out(await use_case.execute(_actor(identity), ticket_id))


@router.post("/{ticket_id}/finalizar", response_model=TicketOut)
async def finalize_ticket(
    ticket_id: UUID,
    body: FinalizeIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = FinalizeTicketUseCase(repos.tickets, repos.timeline)
    return ticket_out(
        await use_case.execute(
            _actor(identity), ticket_id, solution_type_id=body.solution_type_id, notes=body.notes
        )
    )


@router.post("/{ticket_id}/reversos", response_model=ReverseCodeOut, status_code=201)
async def register_reverse(
    ticket_id: UUID,
    body: ReverseIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> ReverseCodeOut:
    use_case = RegisterReverseUseCase(repos.tickets, repos.reverses, repos.timeline)
    reverse = await use_case.execute(_actor(identity), ticket_id, code=body.code)
    names = await repos.users.names_by_ids(
        {reverse.author_user_id} if reverse.author_user_id else set()
    )
    return ReverseCodeOut(
        id=reverse.id,
        code=reverse.code,
        author_user_id=reverse.author_user_id,
        author_name=names.get(reverse.author_user_id) if reverse.author_user_id else None,
        created_at=reverse.created_at,
    )


@router.delete("/{ticket_id}/reversos/{reverso_id}", status_code=204)
async def delete_reverse(
    ticket_id: UUID,
    reverso_id: UUID,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    use_case = DeleteReverseUseCase(repos.tickets, repos.reverses, repos.timeline)
    await use_case.execute(_actor(identity), ticket_id, reverso_id)
    return Response(status_code=204)


@router.put("/{ticket_id}/garantia", response_model=TicketOut)
async def set_warranty(
    ticket_id: UUID,
    body: WarrantyIn,
    identity: TokenPayload = Depends(_operate),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketOut:
    use_case = SetWarrantyUseCase(repos.tickets, repos.timeline)
    return ticket_out(
        await use_case.execute(
            _actor(identity),
            ticket_id,
            order_code=body.order_code,
            tracking_code=body.tracking_code,
        )
    )


@router.post("/{ticket_id}/comentarios", response_model=TicketCommentOut, status_code=201)
async def add_comment(
    ticket_id: UUID,
    body: CommentIn,
    identity: TokenPayload = Depends(_comment),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> TicketCommentOut:
    use_case = AddCommentUseCase(repos.tickets, repos.comments, repos.reads)
    comment = await use_case.execute(
        _actor(identity), ticket_id, body=body.body, reply_to_id=body.reply_to_id
    )
    names = await repos.users.names_by_ids({comment.author_user_id})
    return TicketCommentOut(
        id=comment.id,
        author_user_id=comment.author_user_id,
        author_name=names.get(comment.author_user_id),
        body=comment.body,
        reply_to_id=comment.reply_to_id,
        created_at=comment.created_at,
    )


@router.post("/{ticket_id}/nao-lido", status_code=204)
async def mark_unread(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
) -> Response:
    use_case = MarkTicketUnreadUseCase(repos.tickets, repos.reads)
    await use_case.execute(_actor(identity), ticket_id)
    return Response(status_code=204)


@router.post("/{ticket_id}/anexos/intencao", response_model=AttachmentIntentOut, status_code=201)
async def request_attachment_upload(
    ticket_id: UUID,
    body: AttachmentIntentIn,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> AttachmentIntentOut:
    use_case = RequestUploadUseCase(
        repos.tickets,
        anexos.attachments,
        storage,
        tenant_slug=tenant_slug,
        ttl_seconds=settings.presigned_ttl_seconds,
        max_per_ticket=settings.attachment_max_per_ticket,
        max_bytes=settings.attachment_max_bytes,
    )
    intent = await use_case.execute(
        _actor(identity),
        ticket_id,
        UploadIntentInput(
            filename=body.filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            with_preview=body.with_preview,
        ),
    )
    return AttachmentIntentOut(
        attachment_id=intent.attachment_id,
        object_key=intent.object_key,
        upload_url=intent.upload_url,
        expires_in=intent.expires_in,
        preview_upload_url=intent.preview_upload_url,
    )


@router.post("/{ticket_id}/anexos/{anexo_id}/confirmar", response_model=AttachmentOut)
async def confirm_attachment_upload(
    ticket_id: UUID,
    anexo_id: UUID,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    tenant_slug: str = Depends(get_tenant_slug),
    settings: Settings = Depends(get_settings),
) -> AttachmentOut:
    use_case = ConfirmUploadUseCase(
        repos.tickets,
        anexos.attachments,
        anexos.jobs,
        storage,
        tenant_slug=tenant_slug,
        max_bytes=settings.attachment_max_bytes,
        ttl_seconds=settings.presigned_ttl_seconds,
    )
    view = await use_case.execute(_actor(identity), ticket_id, anexo_id)
    nomes = await repos.users.names_by_ids({view.attachment.author_user_id})
    return attachment_out(view, nomes.get(view.attachment.author_user_id))


@router.get("/{ticket_id}/anexos", response_model=list[AttachmentOut])
async def list_attachments(
    ticket_id: UUID,
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> list[AttachmentOut]:
    vistas = await ListAttachmentsUseCase(
        repos.tickets, anexos.attachments, storage, settings.presigned_ttl_seconds
    ).execute(_actor(identity), ticket_id)
    nomes = await repos.users.names_by_ids({v.attachment.author_user_id for v in vistas})
    return [attachment_out(v, nomes.get(v.attachment.author_user_id)) for v in vistas]


@router.get("/{ticket_id}/anexos/{anexo_id}/url", response_model=AttachmentUrlOut)
async def get_attachment_url(
    ticket_id: UUID,
    anexo_id: UUID,
    variante: str = "medio",
    identity: TokenPayload = Depends(_read),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> AttachmentUrlOut:
    url = await GetAttachmentUrlUseCase(
        repos.tickets, anexos.attachments, storage, settings.presigned_ttl_seconds
    ).execute(_actor(identity), ticket_id, anexo_id, variante)
    return AttachmentUrlOut(url=url, expires_in=settings.presigned_ttl_seconds)


@router.delete("/{ticket_id}/anexos/{anexo_id}", status_code=204)
async def delete_attachment(
    ticket_id: UUID,
    anexo_id: UUID,
    identity: TokenPayload = Depends(_attach),
    repos: TicketRepos = Depends(get_ticket_repos),
    anexos: AttachmentRepos = Depends(get_attachment_repos),
) -> Response:
    await DeleteAttachmentUseCase(repos.tickets, anexos.attachments).execute(
        _actor(identity), ticket_id, anexo_id
    )
    return Response(status_code=204)
