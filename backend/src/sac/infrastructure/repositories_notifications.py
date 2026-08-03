from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
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
