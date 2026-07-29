from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.attachments import (
    ConfirmUploadUseCase,
    DeleteAttachmentUseCase,
    DiscardIntentUseCase,
    ExpirePendingUseCase,
    GetAttachmentUrlUseCase,
    IntentDiscardResult,
    ListAttachmentsUseCase,
    RequestUploadUseCase,
    UploadIntentInput,
)
from sac.domain.attachments import (
    AttachmentStatus,
    PreviewStatus,
)
from sac.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from sac.domain.permissions import Role
from sac.domain.tickets import Ticket, TicketPriority, TicketStatus
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryAttachmentRepository,
    InMemoryPreviewJobRepository,
)
from tests.unit.fakes_tickets import InMemoryTicketRepository

ADMIN = TicketActor(user_id=uuid4(), role=Role.ADMIN)
ATENDENTE = TicketActor(user_id=uuid4(), role=Role.ATENDENTE)
SLUG = "acme"


class Env:
    def __init__(self) -> None:
        self.tickets = InMemoryTicketRepository()
        self.attachments = InMemoryAttachmentRepository()
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()

    async def ticket(self, actor: TicketActor = ADMIN, **over: object) -> Ticket:
        agora = datetime.now(UTC)
        base: dict[str, object] = {
            "id": uuid4(),
            "number": 0,
            "brand_id": uuid4(),
            "status": TicketStatus.ABERTO,
            "priority": TicketPriority.MEDIA,
            "attendant_user_id": actor.user_id,
            "opened_at": agora,
            "due_at": agora + timedelta(hours=72),
            "last_activity_at": agora,
        }
        base.update(over)
        return await self.tickets.add(Ticket(**base))  # type: ignore[arg-type]

    def request_uc(self) -> RequestUploadUseCase:
        return RequestUploadUseCase(self.tickets, self.attachments, self.storage, tenant_slug=SLUG)

    def confirm_uc(self) -> ConfirmUploadUseCase:
        return ConfirmUploadUseCase(
            self.tickets, self.attachments, self.jobs, self.storage, tenant_slug=SLUG
        )


async def test_intencao_gera_chave_no_servidor_e_url_assinada() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput(filename="../etc/passwd.jpg", content_type="image/jpeg", size_bytes=1000),
    )
    assert intent.object_key.startswith(f"{SLUG}/{ticket.id}/")
    assert intent.object_key.endswith(".jpg")
    assert "passwd" not in intent.object_key
    assert intent.upload_url == f"https://fake/put/{intent.object_key}"
    assert intent.preview_upload_url is None
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    assert anexo.status is AttachmentStatus.PENDENTE
    assert anexo.preview_status is PreviewStatus.PENDENTE
    assert anexo.filename == "../etc/passwd.jpg"


async def test_intencao_de_video_com_preview_devolve_duas_urls() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput(
            filename="clipe.mp4",
            content_type="video/mp4",
            size_bytes=5_000_000,
            with_preview=True,
        ),
    )
    assert intent.preview_upload_url is not None
    assert "/previews/" in intent.preview_upload_url


async def test_intencao_recusa_tipo_tamanho_e_cota() -> None:
    env = Env()
    ticket = await env.ticket()
    uc = env.request_uc()
    with pytest.raises(ValidationError):
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("x.gif", "image/gif", 100))
    with pytest.raises(ValidationError):
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("x.jpg", "image/jpeg", 52_428_801))
    for _ in range(10):
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("ok.jpg", "image/jpeg", 10))
    with pytest.raises(ConflictError) as exc:
        await uc.execute(ADMIN, ticket.id, UploadIntentInput("ok.jpg", "image/jpeg", 10))
    assert exc.value.details == {"limite": 10}


async def test_intencao_bloqueada_em_ticket_encerrado_e_para_alheio() -> None:
    env = Env()
    encerrado = await env.ticket(status=TicketStatus.FINALIZADO)
    with pytest.raises(ConflictError):
        await env.request_uc().execute(
            ADMIN, encerrado.id, UploadIntentInput("x.jpg", "image/jpeg", 10)
        )
    do_admin = await env.ticket()
    with pytest.raises(NotFoundError):
        await env.request_uc().execute(
            ATENDENTE, do_admin.id, UploadIntentInput("x.jpg", "image/jpeg", 10)
        )


async def test_confirmacao_de_imagem_enfileira_preview() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 12)
    )
    env.storage.simulate_upload(intent.object_key, b"123456789012", "image/jpeg")

    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    anexo = view.attachment
    assert anexo.status is AttachmentStatus.DISPONIVEL
    assert anexo.confirmed_at is not None
    assert anexo.preview_status is PreviewStatus.PENDENTE
    assert len(env.jobs.items) == 1
    job = next(iter(env.jobs.items.values()))
    assert job.tenant_slug == SLUG
    assert job.attachment_id == anexo.id
    assert job.object_key == anexo.object_key


async def test_confirmacao_de_pdf_nao_gera_job() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("nota.pdf", "application/pdf", 5)
    )
    env.storage.simulate_upload(intent.object_key, b"12345", "application/pdf")
    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert view.attachment.preview_status is PreviewStatus.SEM_PREVIEW
    assert env.jobs.items == {}


async def test_confirmacao_de_video_usa_thumb_do_navegador() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput("clipe.mp4", "video/mp4", 9, with_preview=True),
    )
    env.storage.simulate_upload(intent.object_key, b"123456789", "video/mp4")
    assert intent.preview_upload_url is not None
    preview_key = intent.preview_upload_url.removeprefix("https://fake/put/")
    env.storage.simulate_upload(preview_key, b"webp", "image/webp")

    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert view.attachment.preview_status is PreviewStatus.PRONTO
    assert view.attachment.preview_key == preview_key
    assert view.preview_url == f"https://fake/get/{preview_key}"
    assert env.jobs.items == {}


async def test_confirmacao_de_video_sem_thumb_fica_sem_preview() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput("clipe.mp4", "video/mp4", 9, with_preview=True),
    )
    env.storage.simulate_upload(intent.object_key, b"123456789", "video/mp4")
    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert view.attachment.preview_status is PreviewStatus.SEM_PREVIEW


async def test_confirmacao_de_video_com_thumb_grande_demais_fica_sem_preview() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN,
        ticket.id,
        UploadIntentInput("clipe.mp4", "video/mp4", 9, with_preview=True),
    )
    env.storage.simulate_upload(intent.object_key, b"123456789", "video/mp4")
    assert intent.preview_upload_url is not None
    preview_key = intent.preview_upload_url.removeprefix("https://fake/put/")
    # thumb enviada pelo navegador excede o limite de tamanho: uma thumb ruim
    # nao pode bloquear a confirmacao do video em si.
    env.storage.simulate_upload(preview_key, b"x" * 52_428_801, "image/webp")

    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert view.attachment.status is AttachmentStatus.DISPONIVEL
    assert view.attachment.preview_status is PreviewStatus.SEM_PREVIEW
    assert view.attachment.preview_key is None
    assert view.preview_url is None


async def test_confirmacao_falha_sem_objeto_ou_com_head_divergente() -> None:
    env = Env()
    ticket = await env.ticket()
    uc = env.confirm_uc()

    sem_objeto = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, sem_objeto.attachment_id)
    assert exc.value.details == {"field": "object_key"}

    grande = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(grande.object_key, b"x" * 52_428_801, "image/jpeg")
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, grande.attachment_id)
    assert exc.value.details == {"field": "size_bytes"}

    mime_errado = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(mime_errado.object_key, b"1234567890", "application/pdf")
    with pytest.raises(ValidationError) as exc:
        await uc.execute(ADMIN, ticket.id, mime_errado.attachment_id)
    assert exc.value.details == {"field": "content_type"}


async def test_listagem_traz_url_de_preview_apenas_quando_pronto() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    anexo = view.attachment

    vistas = await ListAttachmentsUseCase(env.tickets, env.attachments, env.storage).execute(
        ADMIN, ticket.id
    )
    assert len(vistas) == 1
    assert vistas[0].preview_url is None

    anexo.preview_status = PreviewStatus.PRONTO
    anexo.preview_key = "acme/t/previews/x.webp"
    await env.attachments.update(anexo)
    vistas = await ListAttachmentsUseCase(env.tickets, env.attachments, env.storage).execute(
        ADMIN, ticket.id
    )
    assert vistas[0].preview_url == "https://fake/get/acme/t/previews/x.webp"


async def test_url_por_variante() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    anexo = view.attachment
    anexo.preview_status = PreviewStatus.PRONTO
    anexo.preview_medium_key = "acme/t/previews/x_medium.webp"
    await env.attachments.update(anexo)

    uc = GetAttachmentUrlUseCase(env.tickets, env.attachments, env.storage)
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "medio") == (
        "https://fake/get/acme/t/previews/x_medium.webp"
    )
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "original") == (
        f"https://fake/get/{anexo.object_key}"
    )
    # sem preview medio, medio cai no original
    anexo.preview_medium_key = None
    await env.attachments.update(anexo)
    assert await uc.execute(ADMIN, ticket.id, anexo.id, "medio") == (
        f"https://fake/get/{anexo.object_key}"
    )


async def test_exclusao_por_autor_e_por_papel() -> None:
    env = Env()
    ticket = await env.ticket(actor=ATENDENTE)
    intent = await env.request_uc().execute(
        ATENDENTE, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    view = await env.confirm_uc().execute(ATENDENTE, ticket.id, intent.attachment_id)
    anexo = view.attachment

    uc = DeleteAttachmentUseCase(env.tickets, env.attachments)
    # admin pode excluir anexo de outro autor
    await uc.execute(ADMIN, ticket.id, anexo.id)
    apagado = await env.attachments.get(anexo.id)
    assert apagado is not None and apagado.deleted_at is not None
    # o objeto permanece no bucket
    assert anexo.object_key in env.storage.objects


async def test_atendente_nao_exclui_anexo_de_outro_autor() -> None:
    env = Env()
    ticket = await env.ticket(actor=ATENDENTE)
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    view = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

    with pytest.raises(PermissionDeniedError):
        await DeleteAttachmentUseCase(env.tickets, env.attachments).execute(
            ATENDENTE, ticket.id, view.attachment.id
        )


async def test_descartar_intencao_pendente_devolve_a_vaga() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    # a intencao ja ocupa vaga na cota antes do upload existir
    assert await env.attachments.count_active(ticket.id) == 1

    resultado = await DiscardIntentUseCase(env.tickets, env.attachments).execute(
        ADMIN, ticket.id, intent.attachment_id
    )

    assert resultado is IntentDiscardResult.DESCARTADO
    descartado = await env.attachments.get(intent.attachment_id)
    assert descartado is not None and descartado.deleted_at is not None
    assert await env.attachments.count_active(ticket.id) == 0


async def test_descartar_intencao_nao_apaga_anexo_ja_confirmado() -> None:
    """O caso que motivou este use case: a resposta do confirmar se perde depois
    do servidor ter commitado, o cliente acha que falhou e pede o descarte. O
    servidor e a autoridade sobre o status, e um anexo DISPONIVEL nao pode ser
    apagado por um pedido de descarte de intencao.
    """
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    env.storage.simulate_upload(intent.object_key, b"1234567890", "image/jpeg")
    await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

    resultado = await DiscardIntentUseCase(env.tickets, env.attachments).execute(
        ADMIN, ticket.id, intent.attachment_id
    )

    assert resultado is IntentDiscardResult.DISPONIVEL
    intacto = await env.attachments.get(intent.attachment_id)
    assert intacto is not None
    assert intacto.deleted_at is None
    assert intacto.status is AttachmentStatus.DISPONIVEL
    assert len(await env.attachments.list_by_ticket(ticket.id)) == 1


async def test_descartar_intencao_de_outro_autor_e_recusado_ate_para_admin() -> None:
    """Mais restrito que DeleteAttachmentUseCase de proposito: excluir um anexo
    visivel e moderacao (admin pode), descartar uma intencao pendente e desfazer
    o proprio upload em andamento — ninguem mais tem motivo para isso.
    """
    env = Env()
    ticket = await env.ticket(actor=ATENDENTE)
    intent = await env.request_uc().execute(
        ATENDENTE, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )

    with pytest.raises(PermissionDeniedError):
        await DiscardIntentUseCase(env.tickets, env.attachments).execute(
            ADMIN, ticket.id, intent.attachment_id
        )

    preservado = await env.attachments.get(intent.attachment_id)
    assert preservado is not None and preservado.deleted_at is None


async def test_descartar_intencao_funciona_com_ticket_encerrado() -> None:
    """Diferente das outras escritas de anexo, que recusam ticket encerrado: a
    vaga precisa voltar mesmo se o ticket fechou no meio do upload, e a linha
    pendente nem aparece na listagem do ticket.
    """
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    ticket.status = TicketStatus.FINALIZADO
    await env.tickets.update(ticket)

    resultado = await DiscardIntentUseCase(env.tickets, env.attachments).execute(
        ADMIN, ticket.id, intent.attachment_id
    )

    assert resultado is IntentDiscardResult.DESCARTADO
    assert await env.attachments.count_active(ticket.id) == 0


async def test_descartar_intencao_expirada_nao_reescreve_a_linha() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    anexo.status = AttachmentStatus.EXPIRADO
    await env.attachments.update(anexo)

    resultado = await DiscardIntentUseCase(env.tickets, env.attachments).execute(
        ADMIN, ticket.id, intent.attachment_id
    )

    # a varredura ja liberou a vaga (expirado nao conta em count_active), entao
    # o descarte e um no-op idempotente em vez de um segundo soft-delete.
    assert resultado is IntentDiscardResult.DESCARTADO
    assert await env.attachments.count_active(ticket.id) == 0
    ainda_expirado = await env.attachments.get(intent.attachment_id)
    assert ainda_expirado is not None and ainda_expirado.deleted_at is None


async def test_descartar_intencao_inexistente_da_404() -> None:
    env = Env()
    ticket = await env.ticket()

    with pytest.raises(NotFoundError):
        await DiscardIntentUseCase(env.tickets, env.attachments).execute(ADMIN, ticket.id, uuid4())


async def test_pendentes_antigos_expiram() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    anexo.created_at = datetime.now(UTC) - timedelta(hours=2)
    await env.attachments.update(anexo)

    total = await ExpirePendingUseCase(env.attachments, minutes=30).execute()
    assert total == 1
    expirado = await env.attachments.get(anexo.id)
    assert expirado is not None and expirado.status is AttachmentStatus.EXPIRADO


async def test_pendente_ja_excluido_nao_e_recontado_como_expirado() -> None:
    env = Env()
    ticket = await env.ticket()
    intent = await env.request_uc().execute(
        ADMIN, ticket.id, UploadIntentInput("foto.jpg", "image/jpeg", 10)
    )
    anexo = await env.attachments.get(intent.attachment_id)
    assert anexo is not None
    anexo.created_at = datetime.now(UTC) - timedelta(hours=2)
    anexo.deleted_at = datetime.now(UTC)
    await env.attachments.update(anexo)

    # a query real (list_pending_before) nao filtra deleted_at, entao o fake
    # precisa devolver a linha ja excluida para o teste provar o guard de fato.
    pendentes_crus = await env.attachments.list_pending_before(datetime.now(UTC))
    assert any(a.id == anexo.id for a in pendentes_crus)

    total = await ExpirePendingUseCase(env.attachments, minutes=30).execute()
    assert total == 0
    ainda_pendente = await env.attachments.get(anexo.id)
    assert ainda_pendente is not None
    assert ainda_pendente.status is AttachmentStatus.PENDENTE
