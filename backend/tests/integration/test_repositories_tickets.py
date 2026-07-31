from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_tickets import TicketFilters
from sac.domain.cadastros import Customer
from sac.domain.errors import ValidationError
from sac.domain.tickets import (
    Ticket,
    TicketComment,
    TicketItem,
    TicketPriority,
    TicketStatus,
)
from sac.infrastructure.models_tenant import (
    BrandModel,
    DefectTypeModel,
    ProductModel,
    TicketModel,
)
from sac.infrastructure.repositories_tickets import build_ticket_repos
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    translated = engine.execution_options(schema_translate_map={"tenant": schema})
    return async_sessionmaker(translated, expire_on_commit=False)


def _novo_ticket(brand_id: UUID, attendant: UUID, **overrides: object) -> Ticket:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "id": uuid4(),
        "number": 0,
        "brand_id": brand_id,
        "status": TicketStatus.ABERTO,
        "priority": TicketPriority.MEDIA,
        "attendant_user_id": attendant,
        "opened_at": now,
        "due_at": now + timedelta(hours=72),
        "last_activity_at": now,
    }
    base.update(overrides)
    return Ticket(**base)  # type: ignore[arg-type]


async def test_roundtrip_add_get_update_e_numero(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repot")
    user = await seed_user(session, email="repot@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        ticket = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        assert ticket.number >= 1
        loaded = await repos.tickets.get(ticket.id)
        assert loaded is not None and loaded.number == ticket.number
        loaded.status = TicketStatus.AGUARDANDO_ANALISE
        loaded.description = "atualizado"
        await repos.tickets.update(loaded)
        again = await repos.tickets.get(ticket.id)
        assert again is not None
        assert again.status is TicketStatus.AGUARDANDO_ANALISE
        assert again.description == "atualizado"
        await ts.commit()


async def test_fk_invalida_vira_validation_error_422(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repofk")
    user = await seed_user(session, email="repofk@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        with pytest.raises(ValidationError) as exc:
            await repos.tickets.add(_novo_ticket(uuid4(), user.id))
        assert exc.value.details.get("field") == "brand_id"


async def test_list_filtros_unread_e_overdue(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repolist")
    user = await seed_user(session, email="repolist@t.com")
    leitor = await seed_user(session, email="leitor@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        defect_id = (await ts.scalars(select(DefectTypeModel.id))).first()
        assert defect_id is not None
        ts.add(ProductModel(id=uuid4(), name="Alicate X", sku="ALX-1"))
        await ts.flush()
        product_id = (
            await ts.scalars(select(ProductModel.id).where(ProductModel.sku == "ALX-1"))
        ).first()
        assert product_id is not None
        atrasado = await repos.tickets.add(
            _novo_ticket(
                brand_id,
                user.id,
                due_at=datetime.now(UTC) - timedelta(hours=1),
                order_code="PED-1",
            )
        )
        no_prazo = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        await repos.items.add(
            TicketItem(
                id=uuid4(),
                ticket_id=atrasado.id,
                product_id=product_id,
                defect_type_id=defect_id,
                quantity=2,
            )
        )
        await ts.flush()

        rows, total = await repos.tickets.list(
            TicketFilters(), 1, 20, "last_activity_at", "desc", unread_for=leitor.id
        )
        assert total == 2
        assert all(row.unread for row in rows)

        rows, total = await repos.tickets.list(
            TicketFilters(overdue=True), 1, 20, "last_activity_at", "desc", unread_for=leitor.id
        )
        assert total == 1 and rows[0].ticket.id == atrasado.id
        assert rows[0].items_count == 1
        assert rows[0].first_product_name == "Alicate X"

        rows, total = await repos.tickets.list(
            TicketFilters(product_id=product_id),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=leitor.id,
        )
        assert total == 1

        rows, total = await repos.tickets.list(
            TicketFilters(order_code="PED-1"),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=leitor.id,
        )
        assert total == 1

        await repos.reads.mark_read(no_prazo.id, leitor.id, datetime.now(UTC))
        await ts.flush()
        rows, _ = await repos.tickets.list(
            TicketFilters(), 1, 20, "number", "asc", unread_for=leitor.id
        )
        by_id = {row.ticket.id: row for row in rows}
        assert by_id[atrasado.id].unread is True
        assert by_id[no_prazo.id].unread is False
        await ts.commit()


async def test_itens_mantem_ordem_de_insercao_mesmo_apos_edicao(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoord")
    user = await seed_user(session, email="repoord@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        defect_id = (await ts.scalars(select(DefectTypeModel.id))).first()
        assert defect_id is not None
        p1, p2 = uuid4(), uuid4()
        ts.add_all(
            [
                ProductModel(id=p1, name="Primeiro", sku="ORD-1"),
                ProductModel(id=p2, name="Segundo", sku="ORD-2"),
            ]
        )
        await ts.flush()
        ticket = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        primeiro = TicketItem(
            id=uuid4(),
            ticket_id=ticket.id,
            product_id=p1,
            defect_type_id=defect_id,
            quantity=1,
        )
        segundo = TicketItem(
            id=uuid4(),
            ticket_id=ticket.id,
            product_id=p2,
            defect_type_id=defect_id,
            quantity=1,
        )
        await repos.items.add(primeiro)
        await repos.items.add(segundo)
        # created_at dos dois itens empata (server_default e transaction_timestamp)
        # e editar o primeiro grava uma nova versao da linha no fim da pagina, o
        # que inverte a ordem fisica. Sem uma coluna de ordem, ordenar por
        # created_at devolve os itens invertidos.
        primeiro.quantity = 3
        await repos.items.update(primeiro)

        itens = await repos.items.list_by_ticket(ticket.id)
        assert [i.product_name for i in itens] == ["Primeiro", "Segundo"]

        rows, _ = await repos.tickets.list(
            TicketFilters(), 1, 20, "number", "asc", unread_for=user.id
        )
        assert rows[0].first_product_name == "Primeiro"
        await ts.commit()


async def test_busca_por_cliente_nome_ou_documento(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repocli")
    user = await seed_user(session, email="repocli@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        customer = Customer(id=uuid4(), name="Joana Prado", document="39053344705")
        await repos.customers.add(customer)
        com_cliente = await repos.tickets.add(
            _novo_ticket(brand_id, user.id, customer_id=customer.id)
        )
        await repos.tickets.add(_novo_ticket(brand_id, user.id))
        for termo in ("joana", "390.533.447-05", "39053344705"):
            rows, total = await repos.tickets.list(
                TicketFilters(customer=termo),
                1,
                20,
                "last_activity_at",
                "desc",
                unread_for=user.id,
            )
            assert total == 1, termo
            assert rows[0].ticket.id == com_cliente.id
            assert rows[0].customer_name == "Joana Prado"
        await ts.commit()


async def test_satelites_comentario_timeline_reverso_read_sla(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="reposat")
    user = await seed_user(session, email="reposat@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        ticket = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        comment = TicketComment(id=uuid4(), ticket_id=ticket.id, author_user_id=user.id, body="oi")
        await repos.comments.add(comment)
        reply = TicketComment(
            id=uuid4(),
            ticket_id=ticket.id,
            author_user_id=user.id,
            body="resposta",
            reply_to_id=comment.id,
        )
        await repos.comments.add(reply)
        listed = await repos.comments.list_by_ticket(ticket.id)
        assert [c.body for c in listed] == ["oi", "resposta"]

        from sac.domain.tickets import ReverseCode, TicketTimelineEvent, TimelineEventType

        await repos.timeline.add(
            TicketTimelineEvent(
                id=uuid4(),
                ticket_id=ticket.id,
                type=TimelineEventType.CRIACAO,
                title="Ticket criado",
                author_user_id=user.id,
            )
        )
        events = await repos.timeline.list_by_ticket(ticket.id)
        assert events[0].type is TimelineEventType.CRIACAO

        reverse = ReverseCode(id=uuid4(), ticket_id=ticket.id, code="BR1", author_user_id=user.id)
        await repos.reverses.add(reverse)
        assert await repos.reverses.count(ticket.id) == 1
        await repos.reverses.remove(reverse.id)
        assert await repos.reverses.count(ticket.id) == 0

        now = datetime.now(UTC)
        await repos.reads.mark_read(ticket.id, user.id, now)
        await repos.reads.mark_read(ticket.id, user.id, now + timedelta(minutes=1))
        stored = await repos.reads.last_read_at(ticket.id, user.id)
        assert stored is not None
        await repos.reads.mark_unread(ticket.id, user.id)
        assert await repos.reads.last_read_at(ticket.id, user.id) is None

        from sac.domain.tickets import TicketPriority as TP

        policy = await repos.sla.get(TP.URGENTE)
        assert policy is not None and policy.hours == 24

        names = await repos.users.names_by_ids({user.id})
        assert names[user.id] == user.name
        await ts.commit()


async def test_filtra_por_atendente(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoaten")
    atendente_um = await seed_user(session, email="atendente1@repoaten.com")
    atendente_dois = await seed_user(session, email="atendente2@repoaten.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        do_um = await repos.tickets.add(_novo_ticket(brand_id, atendente_um.id))
        await repos.tickets.add(_novo_ticket(brand_id, atendente_dois.id))

        rows, total = await repos.tickets.list(
            TicketFilters(attendant_user_id=atendente_um.id),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=atendente_um.id,
        )
        assert total == 1
        assert rows[0].ticket.id == do_um.id
        await ts.commit()


async def test_busca_por_prefixo_do_numero(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repobusn")
    user = await seed_user(session, email="repobusn@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        quarenta_oito = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        quatrocentos_oitenta_nove = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        sete = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        cento_quarenta_oito = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        # os numeros reais vem de uma sequence do tenant; forcamos os valores
        # que o teste precisa direto na tabela, sem passar pelo repositorio.
        await ts.execute(
            update(TicketModel).where(TicketModel.id == quarenta_oito.id).values(number=48)
        )
        await ts.execute(
            update(TicketModel)
            .where(TicketModel.id == quatrocentos_oitenta_nove.id)
            .values(number=489)
        )
        await ts.execute(update(TicketModel).where(TicketModel.id == sete.id).values(number=7))
        # 148 contem "48" como substring, mas nao deve casar: a busca por
        # numero e por prefixo, nao por trecho.
        await ts.execute(
            update(TicketModel).where(TicketModel.id == cento_quarenta_oito.id).values(number=148)
        )
        await ts.flush()

        rows, total = await repos.tickets.list(
            TicketFilters(search="48"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 2
        ids = {row.ticket.id for row in rows}
        assert ids == {quarenta_oito.id, quatrocentos_oitenta_nove.id}
        assert cento_quarenta_oito.id not in ids
        await ts.commit()


async def test_busca_por_nome_do_cliente(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repobusc")
    user = await seed_user(session, email="repobusc@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        customer = Customer(id=uuid4(), name="Mariana Alves", document="39053344705")
        await repos.customers.add(customer)
        com_cliente = await repos.tickets.add(
            _novo_ticket(brand_id, user.id, customer_id=customer.id)
        )
        await repos.tickets.add(_novo_ticket(brand_id, user.id))

        rows, total = await repos.tickets.list(
            TicketFilters(search="mari"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 1
        assert rows[0].ticket.id == com_cliente.id
        await ts.commit()


async def test_busca_por_nome_do_produto(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repobusp")
    user = await seed_user(session, email="repobusp@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        defect_id = (await ts.scalars(select(DefectTypeModel.id))).first()
        assert defect_id is not None
        ts.add(ProductModel(id=uuid4(), name="Alicate de cuticula", sku="ALC-CUT"))
        await ts.flush()
        product_id = (
            await ts.scalars(select(ProductModel.id).where(ProductModel.sku == "ALC-CUT"))
        ).first()
        assert product_id is not None
        com_produto = await repos.tickets.add(_novo_ticket(brand_id, user.id))
        await repos.items.add(
            TicketItem(
                id=uuid4(),
                ticket_id=com_produto.id,
                product_id=product_id,
                defect_type_id=defect_id,
                quantity=1,
            )
        )
        await repos.tickets.add(_novo_ticket(brand_id, user.id))
        await ts.flush()

        rows, total = await repos.tickets.list(
            TicketFilters(search="alicate"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 1
        assert rows[0].ticket.id == com_produto.id

        rows, total = await repos.tickets.list(
            TicketFilters(search="esmalte"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 0
        await ts.commit()


async def test_busca_por_codigo_do_pedido(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repobuso")
    user = await seed_user(session, email="repobuso@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        com_pedido = await repos.tickets.add(
            _novo_ticket(brand_id, user.id, order_code="PED-00042")
        )
        await repos.tickets.add(_novo_ticket(brand_id, user.id))

        rows, total = await repos.tickets.list(
            TicketFilters(search="00042"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 1
        assert rows[0].ticket.id == com_pedido.id

        rows, total = await repos.tickets.list(
            TicketFilters(search="00043"), 1, 20, "last_activity_at", "desc", unread_for=user.id
        )
        assert total == 0
        await ts.commit()


async def test_busca_nao_casa_o_que_nao_deve(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repobusz")
    user = await seed_user(session, email="repobusz@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_ticket_repos(ts)
        brand_id = (await ts.scalars(select(BrandModel.id))).first()
        assert brand_id is not None
        await repos.tickets.add(_novo_ticket(brand_id, user.id))

        rows, total = await repos.tickets.list(
            TicketFilters(search="termo-inexistente-xyz"),
            1,
            20,
            "last_activity_at",
            "desc",
            unread_for=user.id,
        )
        assert total == 0
        assert rows == []
        await ts.commit()
