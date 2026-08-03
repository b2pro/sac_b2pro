import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from sac.application.ports import TokenPayload
from sac.application.use_cases.notifications import (
    GetNotificationCounterUseCase,
    ListNotificationsUseCase,
    MarkNotificationsReadUseCase,
)
from sac.infrastructure.notify_listener import NotificationListener
from sac.infrastructure.repositories_notifications import SqlNotificationRepository
from sac.interface.deps import get_current_identity, get_notification_repository, get_tenant_slug
from sac.interface.schemas import (
    MarkNotificationsReadIn,
    NotificationCounterOut,
    NotificationsPageOut,
    notification_out,
)

router = APIRouter(prefix="/notificacoes", tags=["notificacoes"])

# Intervalo do heartbeat: comentario SSE periodico para atravessar proxy que
# derruba conexao ociosa e para o servidor perceber cliente morto. 25s fica
# abaixo do idle timeout tipico (30s/60s) de nginx e balanceadores.
HEARTBEAT_SECONDS = 25.0

_DATA_EVENT = 'data: {"tipo": "nova"}\n\n'
_HEARTBEAT = ": ping\n\n"


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


@router.get("/stream")
async def stream_notifications(
    request: Request,
    identity: TokenPayload = Depends(get_current_identity),
    slug: str = Depends(get_tenant_slug),
) -> StreamingResponse:
    """Empurra um sinal por SSE quando chega notificacao para este usuario.

    O evento nao carrega conteudo (`{"tipo": "nova"}`): o cliente refaz
    GET /api/notificacoes ao receber, porque a tabela e a fonte de verdade e o
    payload do NOTIFY do Postgres e limitado. Isolamento: a fila vem do par
    (tenant do token, usuario do token) -- nunca de parametro da URL --, logo um
    usuario so pode ouvir os proprios eventos.
    """
    listener: NotificationListener = request.app.state.notify_listener
    # subscribe FORA do gerador, de proposito: o corpo do StreamingResponse so
    # comeca a ser iterado depois dos headers, entao assinar aqui garante que o
    # LISTEN esta ativo antes de o cliente considerar o stream aberto -- sem
    # isso, um NOTIFY imediatamente posterior seria perdido.
    queue = await listener.subscribe(slug, identity.user_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                try:
                    await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield _HEARTBEAT
                    continue
                yield _DATA_EVENT
        finally:
            # finally e obrigatorio: cliente que fecha a aba faz o servidor
            # cancelar este gerador, e sem remover a fila o registry cresceria
            # para sempre com filas de streams mortos.
            listener.unsubscribe(slug, identity.user_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # desliga buffering do nginx: com buffer, o evento so chegaria ao
            # navegador quando o proxy resolvesse esvaziar.
            "X-Accel-Buffering": "no",
        },
    )
