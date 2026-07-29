from collections.abc import Callable
from datetime import datetime

from sac.application.ports_attachments import (
    AttachmentRepository,
    PreviewGenerator,
    PreviewJobRepository,
    ProductPhotoRepository,
    StoragePort,
)
from sac.domain.attachments import (
    MAX_PREVIEW_ATTEMPTS,
    AttachmentKind,
    PreviewStatus,
    next_backoff,
    preview_keys_for,
)
from sac.domain.errors import ValidationError


class _PermanentJobError(Exception):
    """Falha que retry nunca resolve: esgota o job de imediato, na 1a tentativa."""


class _OriginalNotFoundError(_PermanentJobError):
    """Objeto original ausente no bucket: falha permanente, nunca transitoria."""


class _UnsupportedKindError(_PermanentJobError):
    """Job para um kind que este worker nao processa (ex.: video). Video nunca e
    processado no servidor - se um job desses chegar aqui por engano (hoje o
    fluxo de upload so enfileira jobs para imagem), o worker nao deve nem tentar
    abrir os bytes com Pillow."""


class ProcessPreviewJobUseCase:
    """Processa no maximo um job por chamada. O worker chama em laco; os testes
    chamam uma vez. Idempotente: reprocessar sobrescreve os mesmos objetos.

    S3Storage.get_bytes nao distingue objeto ausente de storage indisponivel
    (achado carregado da Task 2). head() sim: devolve None quando a chave nao
    existe. Por isso este use case consulta head antes de get_bytes - um
    objeto original ausente e um erro permanente (o anexo foi excluido ou o
    upload nunca aconteceu) e esgota o job na primeira tentativa, em vez de
    consumir as 5 tentativas com backoff reservadas para instabilidade real de
    rede/storage.
    """

    def __init__(
        self,
        jobs: PreviewJobRepository,
        storage: StoragePort,
        generate: PreviewGenerator,
        attachments_for: Callable[[str], AttachmentRepository],
        photos_for: Callable[[str], ProductPhotoRepository],
    ) -> None:
        self._jobs = jobs
        self._storage = storage
        self._generate = generate
        self._attachments_for = attachments_for
        self._photos_for = photos_for

    async def execute(self, now: datetime) -> bool:
        job = await self._jobs.claim_next(now)
        if job is None:
            return False
        thumb_key, medium_key = preview_keys_for(job.object_key)
        tentativas = job.attempts + 1
        try:
            if job.kind is not AttachmentKind.IMAGEM:
                raise _UnsupportedKindError(f"worker de preview nao processa kind={job.kind}")
            if self._storage.head(job.object_key) is None:
                raise _OriginalNotFoundError(f"objeto original nao encontrado: {job.object_key}")
            original = self._storage.get_bytes(job.object_key)
            thumb, medium = self._generate(original)
            self._storage.put_bytes(thumb_key, thumb, "image/webp")
            self._storage.put_bytes(medium_key, medium, "image/webp")
            if job.attachment_id is not None:
                repo = self._attachments_for(job.tenant_slug)
                anexo = await repo.get(job.attachment_id)
                if anexo is not None:
                    anexo.preview_key = thumb_key
                    anexo.preview_medium_key = medium_key
                    anexo.preview_status = PreviewStatus.PRONTO
                    await repo.update(anexo)
            elif job.product_id is not None:
                photos = self._photos_for(job.tenant_slug)
                atual = await photos.get_photo(job.product_id)
                if atual is not None:
                    await photos.set_photo(job.product_id, atual[0], thumb_key)
            await self._jobs.mark_done(job.id)
        except Exception as exc:  # noqa: BLE001 - qualquer falha reagenda o job
            # ValidationError vindo do gerador (imagem indecodificavel, bomba de
            # descompressao etc.) e sempre permanente: nenhum retry decodifica os
            # mesmos bytes invalidos de forma diferente.
            esgotou = tentativas >= MAX_PREVIEW_ATTEMPTS or isinstance(
                exc, (_PermanentJobError, ValidationError)
            )
            await self._jobs.mark_failed(
                job.id,
                f"{type(exc).__name__}: {exc}",
                now + next_backoff(tentativas),
                exhausted=esgotou,
            )
            if esgotou and job.attachment_id is not None:
                repo = self._attachments_for(job.tenant_slug)
                anexo = await repo.get(job.attachment_id)
                if anexo is not None:
                    anexo.preview_status = PreviewStatus.FALHOU
                    await repo.update(anexo)
        return True
