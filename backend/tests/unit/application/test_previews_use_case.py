from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sac.application.use_cases.previews import ProcessPreviewJobUseCase
from sac.domain.attachments import (
    AttachmentKind,
    AttachmentStatus,
    PreviewJob,
    PreviewJobStatus,
    PreviewStatus,
    TicketAttachment,
    preview_keys_for,
)
from sac.domain.errors import ValidationError
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryAttachmentRepository,
    InMemoryPreviewJobRepository,
    InMemoryProductPhotoRepository,
)

SLUG = "acme"


def _fake_generate(data: bytes) -> tuple[bytes, bytes]:
    return b"thumb:" + data, b"medium:" + data


class Env:
    def __init__(self) -> None:
        self.jobs = InMemoryPreviewJobRepository()
        self.storage = FakeStorage()
        self.attachments = InMemoryAttachmentRepository()
        self.photos = InMemoryProductPhotoRepository()

    def use_case(self, generate=_fake_generate) -> ProcessPreviewJobUseCase:
        return ProcessPreviewJobUseCase(
            jobs=self.jobs,
            storage=self.storage,
            generate=generate,
            attachments_for=lambda slug: self.attachments,
            photos_for=lambda slug: self.photos,
        )

    async def anexo_com_job(self) -> tuple[TicketAttachment, PreviewJob]:
        anexo = TicketAttachment(
            id=uuid4(),
            ticket_id=uuid4(),
            filename="foto.jpg",
            content_type="image/jpeg",
            size_bytes=10,
            object_key=f"{SLUG}/t/{uuid4()}.jpg",
            kind=AttachmentKind.IMAGEM,
            status=AttachmentStatus.DISPONIVEL,
            preview_status=PreviewStatus.PENDENTE,
            author_user_id=uuid4(),
        )
        await self.attachments.add(anexo)
        self.storage.simulate_upload(anexo.object_key, b"original", "image/jpeg")
        job = PreviewJob(
            id=uuid4(),
            tenant_slug=SLUG,
            object_key=anexo.object_key,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            attachment_id=anexo.id,
        )
        await self.jobs.add(job)
        return anexo, job


async def test_processa_job_e_grava_os_dois_previews() -> None:
    env = Env()
    anexo, job = await env.anexo_com_job()
    processou = await env.use_case().execute(datetime.now(UTC))
    assert processou is True

    thumb_key, medium_key = preview_keys_for(anexo.object_key)
    assert env.storage.objects[thumb_key] == (b"thumb:original", "image/webp")
    assert env.storage.objects[medium_key] == (b"medium:original", "image/webp")

    atualizado = await env.attachments.get(anexo.id)
    assert atualizado is not None
    assert atualizado.preview_status is PreviewStatus.PRONTO
    assert atualizado.preview_key == thumb_key
    assert atualizado.preview_medium_key == medium_key
    assert env.jobs.items[job.id].status is PreviewJobStatus.PRONTO


async def test_fila_vazia_devolve_false() -> None:
    env = Env()
    assert await env.use_case().execute(datetime.now(UTC)) is False


async def test_falha_reagenda_com_backoff_e_esgota_na_quinta() -> None:
    env = Env()
    anexo, job = await env.anexo_com_job()

    def explode(data: bytes) -> tuple[bytes, bytes]:
        raise RuntimeError("pillow quebrou")

    agora = datetime.now(UTC)
    for tentativa in range(1, 6):
        job.status = PreviewJobStatus.PENDENTE
        job.next_attempt_at = agora - timedelta(seconds=1)
        assert await env.use_case(generate=explode).execute(agora) is True
        assert env.jobs.items[job.id].attempts == tentativa
        assert "pillow quebrou" in (env.jobs.items[job.id].last_error or "")

    assert env.jobs.items[job.id].status is PreviewJobStatus.FALHOU
    final = await env.attachments.get(anexo.id)
    assert final is not None and final.preview_status is PreviewStatus.FALHOU


async def test_job_de_produto_grava_no_repositorio_de_fotos() -> None:
    env = Env()
    produto_id = uuid4()
    chave = f"{SLUG}/catalogo/produtos/{produto_id}/{uuid4()}.png"
    env.storage.simulate_upload(chave, b"original", "image/png")
    await env.photos.set_photo(produto_id, chave, None)
    await env.jobs.add(
        PreviewJob(
            id=uuid4(),
            tenant_slug=SLUG,
            object_key=chave,
            kind=AttachmentKind.IMAGEM,
            status=PreviewJobStatus.PENDENTE,
            attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
            product_id=produto_id,
        )
    )
    assert await env.use_case().execute(datetime.now(UTC)) is True
    thumb_key, _ = preview_keys_for(chave)
    assert await env.photos.get_photo(produto_id) == (chave, thumb_key)


async def test_original_ausente_falha_definitivamente_sem_esperar_cinco_tentativas() -> None:
    """Achado carregado da Task 2: get_bytes nao distingue objeto ausente de
    storage fora do ar. head() distingue (devolve None), entao o use case
    consulta head primeiro; um objeto ausente e falha permanente e nao deve
    consumir as 5 tentativas de uma instabilidade real de rede."""
    env = Env()
    anexo, job = await env.anexo_com_job()
    del env.storage.objects[anexo.object_key]

    processou = await env.use_case().execute(datetime.now(UTC))
    assert processou is True

    assert env.jobs.items[job.id].attempts == 1
    assert env.jobs.items[job.id].status is PreviewJobStatus.FALHOU

    atualizado = await env.attachments.get(anexo.id)
    assert atualizado is not None
    assert atualizado.preview_status is PreviewStatus.FALHOU


async def test_job_de_video_falha_definitivamente_sem_chamar_o_gerador_de_imagem() -> None:
    """Restricao vinculante: video nunca e processado no servidor. Hoje so
    anexos de imagem enfileiram job (attachments.py), mas se um job de video
    chegar aqui por qualquer motivo, o worker nao deve nem tentar abrir os
    bytes com Pillow - deve falhar de forma permanente, na 1a tentativa."""
    env = Env()
    anexo = TicketAttachment(
        id=uuid4(),
        ticket_id=uuid4(),
        filename="video.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key=f"{SLUG}/t/{uuid4()}.mp4",
        kind=AttachmentKind.VIDEO,
        status=AttachmentStatus.DISPONIVEL,
        preview_status=PreviewStatus.PENDENTE,
        author_user_id=uuid4(),
    )
    await env.attachments.add(anexo)
    env.storage.simulate_upload(anexo.object_key, b"bytes de video", "video/mp4")
    job = PreviewJob(
        id=uuid4(),
        tenant_slug=SLUG,
        object_key=anexo.object_key,
        kind=AttachmentKind.VIDEO,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        attachment_id=anexo.id,
    )
    await env.jobs.add(job)

    def generate_nao_deveria_ser_chamado(data: bytes) -> tuple[bytes, bytes]:
        raise AssertionError("worker de preview nao deve processar video")

    processou = await env.use_case(generate=generate_nao_deveria_ser_chamado).execute(
        datetime.now(UTC)
    )
    assert processou is True

    assert env.jobs.items[job.id].attempts == 1
    assert env.jobs.items[job.id].status is PreviewJobStatus.FALHOU
    atualizado = await env.attachments.get(anexo.id)
    assert atualizado is not None
    assert atualizado.preview_status is PreviewStatus.FALHOU


async def test_imagem_invalida_falha_definitivamente_sem_esperar_cinco_tentativas() -> None:
    """images.py traduz DecompressionBombError (e qualquer outra imagem
    indecodificavel) em ValidationError. Uma imagem gigante ou corrompida nunca
    vai gerar preview em uma proxima tentativa, entao o use case trata
    ValidationError vindo do gerador como falha permanente - mesmo tratamento
    ja dado a objeto ausente e a job de video - em vez de queimar as 5
    tentativas com backoff (~31 minutos) por um erro que retry nunca resolve."""
    env = Env()
    anexo, job = await env.anexo_com_job()

    def gerador_recusa_a_imagem(data: bytes) -> tuple[bytes, bytes]:
        raise ValidationError("arquivo nao e uma imagem valida")

    processou = await env.use_case(generate=gerador_recusa_a_imagem).execute(datetime.now(UTC))
    assert processou is True

    assert env.jobs.items[job.id].attempts == 1
    assert env.jobs.items[job.id].status is PreviewJobStatus.FALHOU
    atualizado = await env.attachments.get(anexo.id)
    assert atualizado is not None
    assert atualizado.preview_status is PreviewStatus.FALHOU
