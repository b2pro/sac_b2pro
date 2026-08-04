import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.application.ports_attachments import ObjectHead
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from sac.domain.entities import Tenant
from sac.infrastructure.models_tenant import BrandModel, TicketModel
from sac.infrastructure.repositories_attachments import (
    SqlPreviewJobRepository,
    build_attachment_repos,
)
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import S3Storage
from sac.infrastructure.worker import run_once
from tests.integration.helpers import seed_provisioned_tenant, seed_user


def _png(width: int = 1000, height: int = 500) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


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


async def _seed_pending_image(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    *,
    slug: str,
    user_email: str,
    next_attempt_at: datetime,
) -> tuple[Tenant, TicketAttachment, UUID]:
    """Cria um tenant provisionado com um anexo disponivel + objeto no bucket
    + job de preview pendente. Devolve o tenant, o anexo e o id do job."""
    tenant = await seed_provisioned_tenant(session, engine, slug=slug)
    user = await seed_user(session, email=user_email)
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        chave = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="foto.png",
            content_type="image/png",
            size_bytes=len(_png()),
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
            confirmed_at=datetime.now(UTC),
        )
        await repos.attachments.add(anexo)
        await ts.commit()

    storage.put_bytes(chave, _png(), "image/png")
    job_id = uuid4()
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=job_id,
            tenant_slug=tenant.slug,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=next_attempt_at,
            attachment_id=anexo.id,
        )
    )
    await session.commit()
    return tenant, anexo, job_id


async def test_worker_gera_os_dois_previews_e_marca_pronto(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    tenant = await seed_provisioned_tenant(session, engine, slug="workerok")
    user = await seed_user(session, email="worker@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        chave = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="foto.png",
            content_type="image/png",
            size_bytes=len(_png()),
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
            confirmed_at=datetime.now(UTC),
        )
        await repos.attachments.add(anexo)
        await ts.commit()

    storage.put_bytes(chave, _png(), "image/png")
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=uuid4(),
            tenant_slug=tenant.slug,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=anexo.id,
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    thumb_key, medium_key = preview_keys_for(chave)
    head_thumb = storage.head(thumb_key)
    head_medium = storage.head(medium_key)
    assert isinstance(head_thumb, ObjectHead) and head_thumb.content_type == "image/webp"
    assert isinstance(head_medium, ObjectHead)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        atualizado = await repos.attachments.get(anexo.id)
        assert atualizado is not None
        assert atualizado.preview_status is PreviewStatus.PRONTO
        assert atualizado.preview_key == thumb_key
        assert atualizado.preview_medium_key == medium_key


async def test_worker_sem_job_devolve_false(
    engine: AsyncEngine, storage: S3Storage, storage_settings: Settings
) -> None:
    assert await run_once(engine, storage, storage_settings) is False


async def test_job_de_objeto_inexistente_esgota_na_primeira_tentativa(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    """Desvio deliberado do teste do brief: o brief (Task 8) foi escrito sem
    conhecer a classificacao de falhas ja implementada e testada na Task 6
    (ProcessPreviewJobUseCase / tests/unit/application/test_previews_use_case.py
    ::test_original_ausente_falha_definitivamente_sem_esperar_cinco_tentativas):
    objeto original ausente e falha PERMANENTE (esgota na 1a tentativa, status
    falhou), nao transitoria. Reproduzir a expectativa literal do brief
    (reagenda com PENDENTE) contradiria esse comportamento ja revisado e
    coberto por teste unitario, entao este teste de integracao verifica o
    comportamento real contra Postgres/MinIO de verdade."""
    tenant = await seed_provisioned_tenant(session, engine, slug="workerfail")
    job_id = uuid4()
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=job_id,
            tenant_slug=tenant.slug,
            object_key=f"{tenant.slug}/inexistente/x.png",
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=uuid4(),
        )
    )
    await session.commit()

    assert await run_once(engine, storage, storage_settings) is True

    relido = await SqlPreviewJobRepository(session).get(job_id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.FALHOU
    assert relido.attempts == 1
    assert relido.last_error is not None and "nao encontrado" in relido.last_error


async def test_foto_de_produto_removida_nao_volta_pelo_worker(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    """Caminho real do achado critico: confirmar a foto enfileira o job, o
    usuario remove a foto dentro da janela de poll do worker (o DELETE nao
    cancela o job) e o worker roda depois. O produto tem que continuar sem foto
    e sem preview - e o job encerra como pronto, nao como falha, porque estar
    obsoleto nao e erro."""
    from sac.application.use_cases.product_photo import DeleteProductPhotoUseCase
    from sac.domain.cadastros import Product
    from sac.infrastructure.repositories_cadastros import SqlProductRepository

    tenant = await seed_provisioned_tenant(session, engine, slug="workerfoto")
    produto_id = uuid4()
    chave = f"{tenant.slug}/catalogo/produtos/{produto_id}/{uuid4()}.png"
    async with _factory(engine, tenant.schema_name)() as ts:
        produtos = SqlProductRepository(ts)
        await produtos.add(
            Product(id=produto_id, name="Alicate com foto", sku=f"WF-{produto_id.hex[:8]}")
        )
        repos = build_attachment_repos(ts)
        await repos.photos.set_photo(produto_id, chave, None)
        await ts.commit()

    storage.put_bytes(chave, _png(), "image/png")
    job_id = uuid4()
    await SqlPreviewJobRepository(session).add(
        PreviewJob(
            id=job_id,
            tenant_slug=tenant.slug,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            product_id=produto_id,
        )
    )
    await session.commit()

    # o usuario remove a foto antes do worker processar o job
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        await DeleteProductPhotoUseCase(SqlProductRepository(ts), repos.photos).execute(produto_id)
        await ts.commit()

    assert await run_once(engine, storage, storage_settings) is True

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        assert await repos.photos.get_photo(produto_id) == (None, None)

    relido = await SqlPreviewJobRepository(session).get(job_id)
    assert relido is not None
    assert relido.status is PreviewJobStatus.PRONTO
    assert relido.attempts == 0
    assert relido.last_error is None


async def test_expiracao_de_pendentes_varre_os_tenants(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    from sqlalchemy import text

    from sac.infrastructure.worker import expire_pending_all

    tenant = await seed_provisioned_tenant(session, engine, slug="workerexp")
    user = await seed_user(session, email="workerexp@t.com")
    chave = f"{tenant.slug}/{uuid4()}/{uuid4()}.png"
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="pendente.png",
            content_type="image/png",
            size_bytes=10,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.PENDENTE,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
        )
        await repos.attachments.add(anexo)
        await ts.execute(
            text(
                f'UPDATE "{tenant.schema_name}".ticket_attachments '
                "SET created_at = now() - interval '2 hours'"
            )
        )
        await ts.commit()
    storage.put_bytes(chave, b"pendente", "image/png")

    await expire_pending_all(engine, storage, minutes=30)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        relido = await repos.attachments.get(anexo.id)
        assert relido is not None
        assert relido.status is AttachmentStatus.EXPIRADO
    # a expiracao apaga o objeto correspondente no storage (Task 10)
    assert storage.head(chave) is None


async def test_expiracao_continua_quando_um_tenant_falha(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    """A varredura roda dentro do run_forever: se a falha de um tenant subisse,
    o processo sairia, o restart traria o worker de volta na mesma falha e as
    previews morreriam para TODOS os tenants. Um tenant ativo sem schema
    provisionado (o caso mais barato de reproduzir) tem que ser apenas logado."""
    from sqlalchemy import text

    from sac.infrastructure.worker import expire_pending_all
    from tests.integration.helpers import seed_tenant

    await seed_tenant(session, slug="workersemschema")

    tenant = await seed_provisioned_tenant(session, engine, slug="workerresil")
    user = await seed_user(session, email="workerresil@t.com")
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=ticket_id,
            filename="pendente.png",
            content_type="image/png",
            size_bytes=10,
            object_key=f"{tenant.slug}/{ticket_id}/{uuid4()}.png",
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.PENDENTE,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=user.id,
        )
        await repos.attachments.add(anexo)
        await ts.execute(
            text(
                f'UPDATE "{tenant.schema_name}".ticket_attachments '
                "SET created_at = now() - interval '2 hours'"
            )
        )
        await ts.commit()

    await expire_pending_all(engine, storage, minutes=30)

    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        relido = await repos.attachments.get(anexo.id)
        assert relido is not None
        assert relido.status is AttachmentStatus.EXPIRADO


async def test_reconciliacao_apaga_orfaos_e_preserva_chaves_conhecidas(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    """A rede de seguranca do que a delecao direta perder, contra Postgres e
    MinIO de verdade. Ficam: o original e as DUAS previews do anexo ativo, a
    foto do produto, seu preview gravado e o preview medio derivado (que o
    worker escreve no bucket mas nenhuma coluna guarda). Saem: o objeto do
    anexo excluido por soft delete que a Task 10 nao conseguiu apagar e o
    upload que ganhou URL assinada e nunca virou linha."""
    from sac.domain.cadastros import Product
    from sac.infrastructure.repositories_cadastros import SqlProductRepository
    from sac.infrastructure.worker import reconcile_orphans_all

    tenant = await seed_provisioned_tenant(session, engine, slug="workerorfao")
    user = await seed_user(session, email="workerorfao@t.com")
    produto_id = uuid4()
    foto = f"{tenant.slug}/catalogo/produtos/{produto_id}/{uuid4()}.png"
    foto_thumb, foto_medium = preview_keys_for(foto)
    async with _factory(engine, tenant.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        ticket_id = await _ticket_id(ts, user.id)
        ativo_key = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        ativo_thumb, ativo_medium = preview_keys_for(ativo_key)
        await repos.attachments.add(
            TicketAttachment(
                id=uuid4(),
                ticket_id=ticket_id,
                filename="ativo.png",
                content_type="image/png",
                size_bytes=8,
                object_key=ativo_key,
                kind=AttachmentKind.IMAGEM,
                status=AttachmentStatus.DISPONIVEL,
                preview_status=PreviewStatus.PRONTO,
                author_user_id=user.id,
                preview_key=ativo_thumb,
                preview_medium_key=ativo_medium,
                confirmed_at=datetime.now(UTC),
            )
        )
        excluido_key = f"{tenant.slug}/{ticket_id}/{uuid4()}.png"
        await repos.attachments.add(
            TicketAttachment(
                id=uuid4(),
                ticket_id=ticket_id,
                filename="excluido.png",
                content_type="image/png",
                size_bytes=8,
                object_key=excluido_key,
                kind=AttachmentKind.IMAGEM,
                status=AttachmentStatus.DISPONIVEL,
                preview_status=PreviewStatus.SEM_PREVIEW,
                author_user_id=user.id,
                deleted_at=datetime.now(UTC),
            )
        )
        await SqlProductRepository(ts).add(
            Product(id=produto_id, name="Alicate com foto", sku=f"RO-{produto_id.hex[:8]}")
        )
        await repos.photos.set_photo(produto_id, foto, foto_thumb)
        await ts.commit()

    solto = f"{tenant.slug}/{uuid4()}/upload-sem-linha.png"
    conhecidos = (ativo_key, ativo_thumb, ativo_medium, foto, foto_thumb, foto_medium)
    for chave in (*conhecidos, excluido_key, solto):
        storage.put_bytes(chave, b"conteudo", "image/png")

    # margem de idade: nada recem-gravado sai, nem o upload sem linha - senao a
    # varredura destruiria uploads em voo.
    await reconcile_orphans_all(engine, storage, hours=24)
    assert storage.head(solto) is not None
    assert storage.head(excluido_key) is not None

    await reconcile_orphans_all(engine, storage, hours=0)

    assert storage.head(solto) is None
    assert storage.head(excluido_key) is None
    for chave in conhecidos:
        assert storage.head(chave) is not None, chave


async def test_reconciliacao_continua_quando_um_tenant_falha(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
) -> None:
    """Mesmo isolamento por tenant da expiracao: a varredura roda dentro do
    run_forever, entao um tenant ativo sem schema provisionado (a leitura das
    chaves conhecidas falha) e apenas logado e os outros tenants seguem sendo
    reconciliados."""
    from sac.infrastructure.worker import reconcile_orphans_all
    from tests.integration.helpers import seed_tenant

    await seed_tenant(session, slug="orfaosemschema")
    tenant = await seed_provisioned_tenant(session, engine, slug="orfaoresil")
    solto = f"{tenant.slug}/{uuid4()}/sem-linha.png"
    storage.put_bytes(solto, b"conteudo", "image/png")

    await reconcile_orphans_all(engine, storage, hours=0)

    assert storage.head(solto) is None


async def test_worker_resolve_tenant_correto_mesmo_com_job_mais_antigo_travado(
    session: AsyncSession,
    engine: AsyncEngine,
    storage: S3Storage,
    storage_settings: Settings,
) -> None:
    """Cobre o finding 1 (achado do code review): claim_next usa FOR UPDATE
    SKIP LOCKED, entao o job globalmente mais antigo pode estar travado por
    outro worker e ser pulado. Se o worker resolvesse o schema do tenant
    ANTES do claim, a partir de um palpite do job mais antigo sem lock (o bug
    corrigido aqui), ele gravaria o preview pronto no tenant errado, de forma
    silenciosa (mark_done ainda marcaria o job como concluido). Este teste
    forca exatamente essa divergencia: trava o job de "tenanta" (o mais
    antigo) numa transacao paralela sem commit, e prova que run_once
    resolve, processa e grava CORRETAMENTE o job de "tenantb" (o unico
    elegivel) - nunca no schema de tenanta. Depois libera o lock e confirma
    que o job de tenanta tambem e processado, no proprio schema, sem
    cruzamento em nenhum dos dois sentidos."""
    from sqlalchemy import text

    agora = datetime.now(UTC)
    tenant_a, anexo_a, job_a_id = await _seed_pending_image(
        session,
        engine,
        storage,
        slug="tenanta",
        user_email="tenanta@t.com",
        next_attempt_at=agora - timedelta(seconds=5),
    )
    tenant_b, anexo_b, _job_b_id = await _seed_pending_image(
        session,
        engine,
        storage,
        slug="tenantb",
        user_email="tenantb@t.com",
        next_attempt_at=agora - timedelta(seconds=1),
    )

    lock_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with lock_factory() as locker:
        # trava a linha do job de tenanta (o mais antigo, seria o "palpite"
        # do bug) sem commitar - claim_next tem que pular para tenantb.
        await locker.execute(
            text("SELECT id FROM preview_jobs WHERE id = :id FOR UPDATE"),
            {"id": job_a_id},
        )

        assert await run_once(engine, storage, storage_settings) is True

        async with _factory(engine, tenant_b.schema_name)() as ts:
            repos = build_attachment_repos(ts)
            atualizado_b = await repos.attachments.get(anexo_b.id)
            assert atualizado_b is not None
            assert atualizado_b.preview_status is PreviewStatus.PRONTO
            thumb_b, medium_b = preview_keys_for(anexo_b.object_key)
            assert atualizado_b.preview_key == thumb_b
            assert atualizado_b.preview_medium_key == medium_b

        # tenanta continua intocado: o job travado nao foi processado, e o
        # anexo de tenanta nao recebeu (por engano) as chaves de tenantb.
        async with _factory(engine, tenant_a.schema_name)() as ts:
            repos = build_attachment_repos(ts)
            ainda_pendente_a = await repos.attachments.get(anexo_a.id)
            assert ainda_pendente_a is not None
            assert ainda_pendente_a.preview_status is PreviewStatus.PENDENTE
            assert ainda_pendente_a.preview_key is None

        await locker.rollback()

    # com o lock liberado, o job de tenanta e o unico elegivel - tem que ser
    # processado e gravado no proprio schema de tenanta.
    assert await run_once(engine, storage, storage_settings) is True
    async with _factory(engine, tenant_a.schema_name)() as ts:
        repos = build_attachment_repos(ts)
        atualizado_a = await repos.attachments.get(anexo_a.id)
        assert atualizado_a is not None
        assert atualizado_a.preview_status is PreviewStatus.PRONTO
        thumb_a, medium_a = preview_keys_for(anexo_a.object_key)
        assert atualizado_a.preview_key == thumb_a
        assert atualizado_a.preview_medium_key == medium_a

    # nunca cruzados: as chaves de preview de cada tenant sao distintas.
    assert atualizado_a.preview_key != atualizado_b.preview_key
