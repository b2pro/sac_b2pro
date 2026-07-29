from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sac.application.use_cases.previews import PermanentJobError, ProcessPreviewJobUseCase
from sac.domain.attachments import (
    AttachmentKind,
    PreviewJob,
    PreviewJobStatus,
)
from sac.infrastructure.worker import _same_tenant
from tests.unit.fakes_attachments import (
    FakeStorage,
    InMemoryAttachmentRepository,
    InMemoryPreviewJobRepository,
    InMemoryProductPhotoRepository,
)


def _job(slug: str = "acme") -> PreviewJob:
    return PreviewJob(
        id=uuid4(),
        tenant_slug=slug,
        object_key=f"{slug}/t/{uuid4()}.png",
        kind=AttachmentKind.IMAGEM,
        status=PreviewJobStatus.PENDENTE,
        attempts=0,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        attachment_id=uuid4(),
    )


def test_same_tenant_devolve_o_repositorio_quando_o_slug_bate() -> None:
    job = _job()
    repo = InMemoryAttachmentRepository()
    assert _same_tenant("acme", job, repo) is repo


def test_divergencia_de_tenant_e_falha_permanente() -> None:
    job = _job()
    with pytest.raises(PermanentJobError):
        _same_tenant("outro", job, InMemoryAttachmentRepository())


async def test_divergencia_de_tenant_esgota_o_job_na_primeira_tentativa() -> None:
    """A guarda protege contra gravar no tenant errado. Um AssertionError seria
    engolido pelo `except Exception` do use case e reagendado 5 vezes com
    backoff; PermanentJobError esgota de uma vez, com a mensagem em last_error."""
    jobs = InMemoryPreviewJobRepository()
    storage = FakeStorage()
    job = _job()
    await jobs.add(job)
    storage.simulate_upload(job.object_key, b"original", "image/png")

    use_case = ProcessPreviewJobUseCase(
        jobs=jobs,
        storage=storage,
        generate=lambda data: (b"thumb", b"medium"),
        # simula a divergencia: a sessao foi traduzida para outro tenant
        attachments_for=lambda slug: _same_tenant("outro", job, InMemoryAttachmentRepository()),
        photos_for=lambda slug: _same_tenant("outro", job, InMemoryProductPhotoRepository()),
    )
    assert await use_case.execute(datetime.now(UTC)) is True

    processado = jobs.items[job.id]
    assert processado.status is PreviewJobStatus.FALHOU
    assert processado.attempts == 1
    assert processado.last_error is not None
    assert "resolucao de tenant inconsistente" in processado.last_error
