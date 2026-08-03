import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from sac.domain.notifications import Notification, NotificationType
from sac.infrastructure.models_tenant import NotificationModel


def _notification_entity(m: NotificationModel) -> Notification:
    return Notification(
        id=m.id,
        user_id=m.user_id,
        ticket_id=m.ticket_id,
        ticket_number=m.ticket_number,
        type=NotificationType(m.type),
        title=m.title,
        snippet=m.snippet,
        actor_user_id=m.actor_user_id,
        created_at=m.created_at,
        read_at=m.read_at,
    )


class SqlNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, notifications: list[Notification]) -> None:
        self._session.add_all(
            NotificationModel(
                id=n.id,
                user_id=n.user_id,
                ticket_id=n.ticket_id,
                ticket_number=n.ticket_number,
                type=str(n.type),
                title=n.title,
                snippet=n.snippet,
                actor_user_id=n.actor_user_id,
                created_at=n.created_at,
                read_at=n.read_at,
            )
            for n in notifications
        )
        await self._session.flush()

    async def list_for_user(
        self, user_id: UUID, only_unread: bool, page: int, per_page: int
    ) -> tuple[list[Notification], int]:
        stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if only_unread:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows_stmt = (
            stmt.order_by(NotificationModel.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.scalars(rows_stmt)
        return [_notification_entity(m) for m in result], int(total or 0)

    async def unread_count(self, user_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count()).where(
                NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None)
            )
        )
        return int(total or 0)

    async def mark_read(self, user_id: UUID, ids: list[UUID], at: datetime) -> None:
        if not ids:
            return
        await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.id.in_(ids),
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=at)
        )

    async def mark_all_read(self, user_id: UUID, at: datetime) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None))
            .values(read_at=at)
        )


_NOTIFY_CHANNEL = "sac_notifications"


class PgNotifyPublisher:
    """Publisher real de tempo real: emite pg_notify no canal global.

    Recebe a MESMA sessao/transacao do use case que gravou as notificacoes
    (SqlNotificationRepository.add_many), de proposito: o Postgres so entrega
    o NOTIFY a outros backends quando essa transacao comita, e quem comita e
    a dependency get_tenant_session ao final do request. Isso faz o aviso em
    tempo real sair exatamente quando a escrita se torna visivel para outras
    conexoes -- nunca antes (evitando um listener ler estado que ainda pode
    ser desfeito por um rollback) nem depois (sem round-trip extra).

    Canal unico e global, nao um por tenant: o listener (Task 5) e quem
    filtra tenant/destinatario, entao nao ha necessidade de multiplicar
    LISTENs no lado do consumidor. O payload carrega so o slug do tenant e os
    ids dos destinatarios -- nunca titulo/snippet da notificacao -- porque o
    NOTIFY do Postgres tem limite de 8000 bytes e o conteudo em si o listener
    busca depois via SqlNotificationRepository, nao pelo payload do canal.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(self, tenant_slug: str, user_ids: list[UUID]) -> None:
        payload = json.dumps({"tenant": tenant_slug, "users": [str(u) for u in user_ids]})
        await self._session.execute(
            text("SELECT pg_notify(:canal, :payload)"),
            {"canal": _NOTIFY_CHANNEL, "payload": payload},
        )
