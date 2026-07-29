from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sac.application.ports_tickets import TicketActor
from sac.application.use_cases.attachments import (
    ConfirmUploadUseCase,
    DeleteAttachmentUseCase,
    ExpirePendingUseCase,
    GetAttachmentUrlUseCase,
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

    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
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
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.SEM_PREVIEW
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

    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.PRONTO
    assert anexo.preview_key == preview_key
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
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
    assert anexo.preview_status is PreviewStatus.SEM_PREVIEW


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
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

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
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)
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
    anexo = await env.confirm_uc().execute(ATENDENTE, ticket.id, intent.attachment_id)

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
    anexo = await env.confirm_uc().execute(ADMIN, ticket.id, intent.attachment_id)

    with pytest.raises(PermissionDeniedError):
        await DeleteAttachmentUseCase(env.tickets, env.attachments).execute(
            ATENDENTE, ticket.id, anexo.id
        )


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
