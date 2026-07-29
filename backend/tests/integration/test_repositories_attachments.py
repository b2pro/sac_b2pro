import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
)
from sac.domain.permissions import Role
from sac.infrastructure.models_tenant import BrandModel, ProductModel, TicketModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    SqlTenantMemberDirectory,
    build_attachment_repos,
)
from tests.integration.helpers import seed_link, seed_provisioned_tenant, seed_user


def _factory(engine: AsyncEngine, schema: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )


async def _ticket_id(ts: AsyncSession, attendant: UUID) -> UUID:
    brand_id = (await ts.scalars(select(BrandModel.id))).first()
    assert brand_id is not None
    ticket = TicketModel(
        id=uuid4(),
        brand_id=brand_id,
        status="aberto",
        priority="media",
        attendant_user_id=attendant,
        due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    ts.add(ticket)
    await ts.flush()
    return ticket.id


def _anexo(ticket_id: UUID, author: UUID, **over: object) -> TicketAttachment:
    base: dict[str, object] = {
        "id": uuid4(),
        "ticket_id": ticket_id,
        "filename": "foto.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 999,
        "object_key": f"acme/{ticket_id}/{uuid4()}.jpg",
        "kind": AttachmentKind.IMAGEM,
        "status": AttachmentStatus.PENDENTE,
        "preview_status": PreviewStatus.PENDENTE,
        "author_user_id": author,
    }
    base.update(over)
    return TicketAttachment(**base)  # type: ignore[arg-type]


async def test_lista_traz_apenas_disponiveis_e_nao_deletados(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanex")
    user = await seed_user(session, email="repoanex@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        disponivel = _anexo(ticket_id, user.id, status=AttachmentStatus.DISPONIVEL)
        pendente = _anexo(ticket_id, user.id)
        deletado = _anexo(
            ticket_id,
            user.id,
            status=AttachmentStatus.DISPONIVEL,
            deleted_at=datetime.now(UTC),
        )
        for a in (disponivel, pendente, deletado):
            await repos.attachments.add(a)
        await ts.flush()

        listados = await repos.attachments.list_by_ticket(ticket_id)
        assert [a.id for a in listados] == [disponivel.id]
        # cota conta pendentes tambem, mas nao deletados
        assert await repos.attachments.count_active(ticket_id) == 2
        await ts.commit()


async def test_update_e_get_preservam_campos(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanexupd")
    user = await seed_user(session, email="repoanexupd@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = _anexo(ticket_id, user.id)
        await repos.attachments.add(anexo)
        await ts.flush()

        anexo.status = AttachmentStatus.DISPONIVEL
        anexo.confirmed_at = datetime.now(UTC)
        anexo.preview_key = "acme/x/previews/y.webp"
        anexo.preview_medium_key = "acme/x/previews/y_medium.webp"
        anexo.preview_status = PreviewStatus.PRONTO
        await repos.attachments.update(anexo)
        await ts.flush()

        lido = await repos.attachments.get(anexo.id)
        assert lido is not None
        assert lido.status is AttachmentStatus.DISPONIVEL
        assert lido.preview_status is PreviewStatus.PRONTO
        assert lido.preview_medium_key == "acme/x/previews/y_medium.webp"
        assert lido.confirmed_at is not None
        await ts.commit()


async def test_pendentes_antigos_sao_encontrados(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repoanexexp")
    user = await seed_user(session, email="repoanexexp@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        antigo = _anexo(ticket_id, user.id)
        await repos.attachments.add(antigo)
        await ts.flush()
        # envelhece o registro direto no banco
        await ts.execute(select(ProductModel.id).limit(0))  # no-op para manter a sessao ativa
        from sqlalchemy import text

        await ts.execute(
            text(
                f'UPDATE "{tenant.schema_name}".ticket_attachments '
                "SET created_at = now() - interval '2 hours'"
            )
        )
        encontrados = await repos.attachments.list_pending_before(
            datetime.now(UTC) - timedelta(minutes=30)
        )
        assert [a.id for a in encontrados] == [antigo.id]
        await ts.commit()


async def test_fila_claim_marca_processando_e_pula_travado(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    job = PreviewJob(
        id=uuid4(),
        tenant_slug="acme",
        object_key="acme/t/x.jpg",
        kind=AttachmentKind.IMAGEM,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=agora - timedelta(seconds=1),
        attachment_id=uuid4(),
    )
    await jobs.add(job)
    await session.flush()

    pego = await jobs.claim_next(agora)
    assert pego is not None and pego.id == job.id
    assert pego.status is PreviewJobStatus.PROCESSANDO
    # ja em processamento: nao volta
    assert await jobs.claim_next(agora) is None


async def test_fila_claim_pula_linha_travada_por_outra_sessao(engine: AsyncEngine) -> None:
    # Prova o SKIP LOCKED de verdade: duas sessoes/conexoes distintas disputando a fila.
    # Uma unica sessao chamando claim_next duas vezes (como no teste acima) prova apenas a
    # transicao de status - passaria mesmo com um SELECT simples sem nenhuma clausula de
    # lock. Aqui a segunda sessao so pode ver a primeira linha como "pendente" (a UPDATE da
    # sessao A ainda nao foi commitada) mas encontra a linha travada por FOR UPDATE e a
    # pula, reivindicando a outra.
    factory = async_sessionmaker(engine, expire_on_commit=False)
    agora = datetime.now(UTC)
    travado_id = uuid4()
    livre_id = uuid4()
    async with factory() as seed_session:
        seed_jobs = SqlPreviewJobRepository(seed_session)
        for job_id, sufixo in ((travado_id, "travado"), (livre_id, "livre")):
            await seed_jobs.add(
                PreviewJob(
                    id=job_id,
                    tenant_slug="acme",
                    object_key=f"acme/t/{sufixo}.jpg",
                    kind=AttachmentKind.IMAGEM,
                    status=PreviewJobStatus.PENDENTE,
                    attempts=0,
                    next_attempt_at=agora - timedelta(seconds=1),
                    attachment_id=uuid4(),
                )
            )
        await seed_session.commit()

    session_a = factory()
    session_b = factory()
    try:
        jobs_a = SqlPreviewJobRepository(session_a)
        jobs_b = SqlPreviewJobRepository(session_b)

        primeiro = await jobs_a.claim_next(agora)
        assert primeiro is not None
        assert primeiro.id in (travado_id, livre_id)
        # session_a NAO comita: mantem a linha reivindicada travada (FOR UPDATE) em aberto.

        # Se claim_next nao usasse SKIP LOCKED, esta chamada bloquearia esperando a
        # sessao A liberar o lock; o timeout transforma um travamento em falha visivel
        # em vez de travar a suite inteira.
        segundo = await asyncio.wait_for(jobs_b.claim_next(agora), timeout=5)

        assert segundo is not None, (
            "sessao B deveria pular a linha travada e reivindicar a outra, nao bloquear"
        )
        assert segundo.id != primeiro.id
        assert {primeiro.id, segundo.id} == {travado_id, livre_id}
    except BaseException:
        # nao deixa a limpeza mascarar o erro real (ex.: TimeoutError de um lock que
        # bloqueou de verdade)
        await session_a.rollback()
        await session_b.rollback()
        raise
    else:
        # persiste as duas linhas como "processando" para nao poluir a fila global
        # (preview_jobs e uma tabela publica, compartilhada entre todos os testes)
        await session_a.commit()
        await session_b.commit()
    finally:
        await session_a.close()
        await session_b.close()


async def test_fila_respeita_next_attempt_at(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    await jobs.add(
        PreviewJob(
            id=uuid4(),
            tenant_slug="acme",
            object_key="acme/t/futuro.jpg",
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=1,
            next_attempt_at=agora + timedelta(minutes=5),
            attachment_id=uuid4(),
        )
    )
    await session.flush()
    assert await jobs.claim_next(agora) is None


async def test_mark_failed_reagenda_e_esgota(session: AsyncSession) -> None:
    jobs = SqlPreviewJobRepository(session)
    agora = datetime.now(UTC)
    job = PreviewJob(
        id=uuid4(),
        tenant_slug="acme",
        object_key="acme/t/falha.jpg",
        kind=AttachmentKind.IMAGEM,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=agora - timedelta(seconds=1),
        attachment_id=uuid4(),
    )
    await jobs.add(job)
    await session.flush()
    await jobs.claim_next(agora)

    await jobs.mark_failed(job.id, "boom", agora + timedelta(minutes=1), exhausted=False)
    await session.flush()
    relido = await jobs.get(job.id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.PENDENTE
    assert relido.attempts == 1
    assert relido.last_error == "boom"

    await jobs.mark_failed(job.id, "boom final", agora, exhausted=True)
    await session.flush()
    final = await jobs.get(job.id)
    assert final is not None and final.status is PreviewJobStatus.FALHOU


async def test_foto_do_produto_grava_e_le(session: AsyncSession, engine: AsyncEngine) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repofoto")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        produto = ProductModel(id=uuid4(), name="Com foto", sku="CF-1")
        ts.add(produto)
        await ts.flush()

        await repos.photos.set_photo(produto.id, "k/original.png", "k/previews/original.webp")
        await ts.flush()
        assert await repos.photos.get_photo(produto.id) == (
            "k/original.png",
            "k/previews/original.webp",
        )

        await repos.photos.set_photo(produto.id, None, None)
        await ts.flush()
        assert await repos.photos.get_photo(produto.id) == (None, None)
        assert await repos.photos.get_photo(uuid4()) is None
        await ts.commit()


async def test_membros_do_tenant_com_nome_e_papel(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="repomembros")
    outro = await seed_provisioned_tenant(session, engine, slug="repooutro")
    admin = await seed_user(session, email="admin@repomembros.com", name="Ana Admin")
    atendente = await seed_user(session, email="att@repomembros.com", name="Bruno Atendente")
    de_fora = await seed_user(session, email="fora@repooutro.com", name="Carlos Fora")
    await seed_link(session, user=admin, tenant=tenant, role=Role.ADMIN)
    await seed_link(session, user=atendente, tenant=tenant, role=Role.ATENDENTE)
    await seed_link(session, user=de_fora, tenant=outro, role=Role.ADMIN)

    membros = await SqlTenantMemberDirectory(session).list_members(tenant.slug)
    assert [(m.name, m.role) for m in membros] == [
        ("Ana Admin", Role.ADMIN),
        ("Bruno Atendente", Role.ATENDENTE),
    ]
    assert all(m.active for m in membros)
