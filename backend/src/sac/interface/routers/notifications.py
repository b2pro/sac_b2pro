from fastapi import APIRouter, Depends, Response

from sac.application.ports import TokenPayload
from sac.application.use_cases.notifications import (
    GetNotificationCounterUseCase,
    ListNotificationsUseCase,
    MarkNotificationsReadUseCase,
)
from sac.infrastructure.repositories_notifications import SqlNotificationRepository
from sac.interface.deps import get_current_identity, get_notification_repository
from sac.interface.schemas import (
    MarkNotificationsReadIn,
    NotificationCounterOut,
    NotificationsPageOut,
    notification_out,
)

router = APIRouter(prefix="/notificacoes", tags=["notificacoes"])


@router.get("", response_model=NotificationsPageOut)
async def list_notifications(
    apenas_nao_lidas: bool = False,
    page: int = 1,
    per_page: int = 20,
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlNotificationRepository = Depends(get_notification_repository),
) -> NotificationsPageOut:
    rows, total = await ListNotificationsUseCase(repo).execute(
        identity.user_id, apenas_nao_lidas, page, per_page
    )
    return NotificationsPageOut(items=[notification_out(n) for n in rows], total=total)


@router.get("/contador", response_model=NotificationCounterOut)
async def get_notification_counter(
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlNotificationRepository = Depends(get_notification_repository),
) -> NotificationCounterOut:
    count = await GetNotificationCounterUseCase(repo).execute(identity.user_id)
    return NotificationCounterOut(nao_lidas=count)


@router.post("/marcar-lidas", status_code=204)
async def mark_notifications_read(
    body: MarkNotificationsReadIn,
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlNotificationRepository = Depends(get_notification_repository),
) -> Response:
    await MarkNotificationsReadUseCase(repo).execute(identity.user_id, body.ids)
    return Response(status_code=204)
