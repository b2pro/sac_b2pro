from datetime import UTC, datetime
from uuid import UUID

from sac.application.ports_notifications import NotificationRepository
from sac.domain.notifications import Notification


class ListNotificationsUseCase:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(
        self, user_id: UUID, only_unread: bool, page: int, per_page: int
    ) -> tuple[list[Notification], int]:
        return await self._notifications.list_for_user(user_id, only_unread, page, per_page)


class GetNotificationCounterUseCase:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(self, user_id: UUID) -> int:
        return await self._notifications.unread_count(user_id)


class MarkNotificationsReadUseCase:
    """Marca notificacoes do proprio usuario como lidas.

    ids=None (corpo `{"ids": null}` ou omitido) marca todas as pendentes;
    uma lista de ids marca so essas, e o repositorio ja restringe a consulta
    a `user_id`, entao um id que pertence a outro usuario simplesmente nao
    casa com nenhuma linha -- nunca lanca erro nem vaza estado de terceiros.
    """

    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(self, user_id: UUID, ids: list[UUID] | None) -> None:
        now = datetime.now(UTC)
        if ids is None:
            await self._notifications.mark_all_read(user_id, now)
        else:
            await self._notifications.mark_read(user_id, ids, now)
