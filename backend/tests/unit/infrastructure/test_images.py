import io

import pytest
from PIL import Image

from sac.domain.errors import ValidationError
from sac.infrastructure.images import generate_previews


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 100, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def _png_rgba(width: int, height: int, color: tuple[int, int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), color=color).save(buffer, format="PNG")
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


def test_fundo_transparente_e_composto_sobre_branco_e_nao_mantem_a_cor_por_baixo() -> None:
    """convert('RGB') direto em RGBA nao composita: mantem os valores de RGB que
    estavam por baixo do alpha, que sao arbitrarios por encoder. Um pixel
    totalmente transparente criado sobre vermelho puro nao pode sobreviver como
    vermelho no preview - fotos de catalogo em PNG com fundo transparente sao
    comuns (STALEKS/KODI) e um preview com fundo vermelho seria visualmente
    quebrado."""
    origem = _png_rgba(200, 100, (255, 0, 0, 0))
    thumb, medio = generate_previews(origem)
    for conteudo in (thumb, medio):
        with Image.open(io.BytesIO(conteudo)) as img:
            assert img.mode == "RGB"
            r, g, b = img.convert("RGB").getpixel((img.width // 2, img.height // 2))
            # tolerancia pela quantizacao com perdas do WEBP: perto de branco, nao exato.
            assert r > 250 and g > 250 and b > 250


def test_imagem_gigante_vira_erro_de_validacao() -> None:
    """DecompressionBombError subclassa Exception diretamente (nao OSError nem
    ValueError), entao escapava do except da funcao sem virar ValidationError -
    quebrando o contrato da camada de infraestrutura de so levantar erros de
    dominio. Baixamos o limite temporariamente para nao precisar alocar uma
    imagem de 80 megapixels de verdade."""
    limite_original = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 100
    try:
        with pytest.raises(ValidationError):
            generate_previews(_png(200, 100))
    finally:
        Image.MAX_IMAGE_PIXELS = limite_original
