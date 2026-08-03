from uuid import UUID

from sac.domain.notifications import Notification


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self.notifications: list[Notification] = []
        self.add_many_call_count = 0

    async def add_many(self, notifications: list[Notification]) -> None:
        self.add_many_call_count += 1
        self.notifications.extend(notifications)

    async def list_for_user(
        self, user_id: UUID, only_unread: bool, page: int, per_page: int
    ) -> tuple[list[Notification], int]:
        return [], 0

    async def unread_count(self, user_id: UUID) -> int:
        return 0

    async def mark_read(self, user_id: UUID, ids: list[UUID], at) -> None:
        pass

    async def mark_all_read(self, user_id: UUID, at) -> None:
        pass


class InMemoryNotificationPublisher:
    def __init__(self) -> None:
        self.publish_calls: list[tuple[str, list[UUID]]] = []

    async def publish(self, tenant_slug: str, user_ids: list[UUID]) -> None:
        self.publish_calls.append((tenant_slug, user_ids))
