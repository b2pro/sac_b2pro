from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.notifications import Notification, NotificationType
from sac.domain.tickets import Ticket, TicketPriority, TicketStatus
from sac.infrastructure.models_tenant import BrandModel
from sac.infrastructure.repositories_notifications import SqlNotificationRepository
from sac.infrastructure.repositories_tickets import build_ticket_repos
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


def _notification(
    user_id: UUID, ticket_id: UUID, ticket_number: int, **overrides: object
) -> Notification:
    base: dict[str, object] = {
        "id": uuid4(),
        "user_id": user_id,
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "type": NotificationType.ATRIBUICAO,
        "title": "Ticket atribuído",
    }
    base.update(overrides)
    return Notification(**base)  # type: ignore[arg-type]


async def test_unread_count_list_e_mark_read_isolados_por_usuario(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repnotif")
    user_a = await seed_user(session, email="repnotifa@t.com")
    user_b = await seed_user(session, email="repnotifb@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket_repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        now = datetime.now(UTC)
        ticket = await ticket_repos.tickets.add(
            Ticket(
                id=uuid4(),
                number=0,
                brand_id=brand_id,
                status=TicketStatus.ABERTO,
                priority=TicketPriority.MEDIA,
                attendant_user_id=user_a.id,
                opened_at=now,
                due_at=now + timedelta(hours=72),
                last_activity_at=now,
            )
        )
        await ts.commit()

        repo = SqlNotificationRepository(ts)
        n1 = _notification(
            user_a.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=3)
        )
        n2 = _notification(
            user_a.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=2)
        )
        n3 = _notification(
            user_a.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=1)
        )
        n_b = _notification(user_b.id, ticket.id, ticket.number, created_at=now)
        await repo.add_many([n1, n2, n3, n_b])
        await ts.commit()

        # n1 ja chega lida, as demais entram nao lidas.
        await repo.mark_read(user_a.id, [n1.id], now)
        await ts.commit()

        assert await repo.unread_count(user_a.id) == 2
        assert await repo.unread_count(user_b.id) == 1

        rows, total = await repo.list_for_user(user_a.id, only_unread=False, page=1, per_page=10)
        assert total == 3
        assert [row.id for row in rows] == [n3.id, n2.id, n1.id]

        unread_rows, unread_total = await repo.list_for_user(
            user_a.id, only_unread=True, page=1, per_page=10
        )
        assert unread_total == 2
        assert {row.id for row in unread_rows} == {n2.id, n3.id}

        later = now + timedelta(minutes=5)
        await repo.mark_all_read(user_a.id, later)
        await ts.commit()

        assert await repo.unread_count(user_a.id) == 0
        # de B nao foi mexido.
        assert await repo.unread_count(user_b.id) == 1


async def test_list_for_user_pagina_de_fronteira(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    # per_page=2 sobre 3 linhas forca offset/limit a sair da primeira pagina:
    # um limit/offset trocado ou um off-by-one em (page - 1) * per_page
    # passaria verde se so page=1 fosse exercitado (motivo do achado do
    # revisor no fix round 1).
    tenant = await seed_provisioned_tenant(session, engine, slug="repnotifpag")
    user = await seed_user(session, email="repnotifpag@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        ticket_repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        now = datetime.now(UTC)
        ticket = await ticket_repos.tickets.add(
            Ticket(
                id=uuid4(),
                number=0,
                brand_id=brand_id,
                status=TicketStatus.ABERTO,
                priority=TicketPriority.MEDIA,
                attendant_user_id=user.id,
                opened_at=now,
                due_at=now + timedelta(hours=72),
                last_activity_at=now,
            )
        )
        await ts.commit()

        repo = SqlNotificationRepository(ts)
        # created_at crescente: n1 e a mais antiga, n3 a mais recente.
        n1 = _notification(user.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=3))
        n2 = _notification(user.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=2))
        n3 = _notification(user.id, ticket.id, ticket.number, created_at=now - timedelta(minutes=1))
        await repo.add_many([n1, n2, n3])
        await ts.commit()

        page1, total1 = await repo.list_for_user(user.id, only_unread=False, page=1, per_page=2)
        assert total1 == 3
        assert [row.id for row in page1] == [n3.id, n2.id]

        page2, total2 = await repo.list_for_user(user.id, only_unread=False, page=2, per_page=2)
        assert total2 == 3
        assert [row.id for row in page2] == [n1.id]
