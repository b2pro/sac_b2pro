from datetime import timedelta
from uuid import UUID

import pytest

from sac.domain.attachments import (
    ALLOWED_CONTENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_TICKET,
    MAX_PREVIEW_ATTEMPTS,
    AttachmentKind,
    build_object_key,
    build_product_photo_key,
    extension_for,
    kind_for,
    next_backoff,
    preview_keys_for,
    validate_size,
)
from sac.domain.errors import ValidationError

TICKET = UUID("11111111-1111-1111-1111-111111111111")
UID = UUID("22222222-2222-2222-2222-222222222222")


def test_tipos_aceitos_e_seus_kinds() -> None:
    assert kind_for("image/jpeg") is AttachmentKind.IMAGEM
    assert kind_for("image/png") is AttachmentKind.IMAGEM
    assert kind_for("image/webp") is AttachmentKind.IMAGEM
    assert kind_for("application/pdf") is AttachmentKind.PDF
    assert kind_for("video/mp4") is AttachmentKind.VIDEO
    assert kind_for("video/quicktime") is AttachmentKind.VIDEO
    assert kind_for("video/webm") is AttachmentKind.VIDEO
    assert len(ALLOWED_CONTENT_TYPES) == 7


def test_tipo_recusado() -> None:
    for mime in ("image/gif", "application/zip", "text/html", ""):
        with pytest.raises(ValidationError) as exc:
            kind_for(mime)
        assert exc.value.details == {"field": "content_type"}


def test_extensao_vem_do_mime() -> None:
    assert extension_for("image/jpeg") == "jpg"
    assert extension_for("image/png") == "png"
    assert extension_for("image/webp") == "webp"
    assert extension_for("application/pdf") == "pdf"
    assert extension_for("video/mp4") == "mp4"
    assert extension_for("video/quicktime") == "mov"
    assert extension_for("video/webm") == "webm"


def test_limite_de_tamanho() -> None:
    assert MAX_ATTACHMENT_BYTES == 52_428_800
    assert MAX_ATTACHMENTS_PER_TICKET == 10
    validate_size(1)
    validate_size(MAX_ATTACHMENT_BYTES)
    for invalido in (0, -1, MAX_ATTACHMENT_BYTES + 1):
        with pytest.raises(ValidationError) as exc:
            validate_size(invalido)
        assert exc.value.details == {"field": "size_bytes"}


def test_chave_gerada_no_servidor_ignora_o_nome_do_arquivo() -> None:
    chave = build_object_key("acme", TICKET, "image/jpeg", UID)
    assert chave == f"acme/{TICKET}/{UID}.jpg"
    foto = build_product_photo_key("acme", UID, "image/png", TICKET)
    assert foto == f"acme/catalogo/produtos/{UID}/{TICKET}.png"


def test_chaves_de_preview_derivam_do_original() -> None:
    thumb, medio = preview_keys_for(f"acme/{TICKET}/{UID}.jpg")
    assert thumb == f"acme/{TICKET}/previews/{UID}.webp"
    assert medio == f"acme/{TICKET}/previews/{UID}_medium.webp"


def test_backoff_exponencial_limitado() -> None:
    assert MAX_PREVIEW_ATTEMPTS == 5
    assert next_backoff(1) == timedelta(minutes=1)
    assert next_backoff(2) == timedelta(minutes=2)
    assert next_backoff(3) == timedelta(minutes=4)
    assert next_backoff(4) == timedelta(minutes=8)
    assert next_backoff(5) == timedelta(minutes=16)
    assert next_backoff(9) == timedelta(minutes=16)
