import io

import pytest
from PIL import Image

from sac.domain.errors import ValidationError
from sac.infrastructure.images import generate_previews


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 100, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_gera_thumb_e_media_em_webp_respeitando_proporcao() -> None:
    thumb, medio = generate_previews(_png(3000, 1500))
    with Image.open(io.BytesIO(thumb)) as img:
        assert img.format == "WEBP"
        assert img.width == 400
        assert img.height == 200
    with Image.open(io.BytesIO(medio)) as img:
        assert img.format == "WEBP"
        assert img.width == 1200
        assert img.height == 600


def test_imagem_menor_que_o_alvo_nao_e_ampliada() -> None:
    thumb, medio = generate_previews(_png(200, 100))
    with Image.open(io.BytesIO(thumb)) as img:
        assert (img.width, img.height) == (200, 100)
    with Image.open(io.BytesIO(medio)) as img:
        assert (img.width, img.height) == (200, 100)


def test_bytes_que_nao_sao_imagem_viram_erro_de_validacao() -> None:
    with pytest.raises(ValidationError):
        generate_previews(b"isto nao e uma imagem")
