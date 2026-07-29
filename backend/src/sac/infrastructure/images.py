import io

from PIL import Image, UnidentifiedImageError

from sac.domain.errors import ValidationError

# Limite defensivo: uma imagem gigante nao pode derrubar o worker por memoria.
Image.MAX_IMAGE_PIXELS = 80_000_000


def _resize(source: Image.Image, largest_side: int) -> bytes:
    copy = source.copy()
    copy.thumbnail((largest_side, largest_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="WEBP", quality=82, method=4)
    return buffer.getvalue()


def _to_rgb(image: Image.Image) -> Image.Image:
    """Descarta o canal alpha compositando sobre um fundo branco. `convert("RGB")`
    direto num modo com transparencia NAO composita: mantem os valores de RGB
    que estavam por baixo do alpha, que sao arbitrarios por encoder (um pixel
    vermelho totalmente transparente pode virar (255, 0, 0) em vez de branco).
    PNG e um content-type aceito e fotos de catalogo com fundo transparente sao
    comuns, entao a composicao evita previews com cores erradas.
    """
    mode = image.mode
    if mode == "P" and "transparency" in image.info:
        image = image.convert("RGBA")
        mode = image.mode
    if mode in ("RGBA", "LA"):
        rgba = image.convert("RGBA")
        fundo = Image.new("RGB", image.size, (255, 255, 255))
        fundo.paste(rgba, mask=rgba.getchannel("A"))
        return fundo
    return image.convert("RGB")


def generate_previews(
    data: bytes, thumb_px: int = 400, medium_px: int = 1200
) -> tuple[bytes, bytes]:
    try:
        with Image.open(io.BytesIO(data)) as original:
            original.load()
            rgb = _to_rgb(original)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError("arquivo nao e uma imagem valida") from exc
    return _resize(rgb, thumb_px), _resize(rgb, medium_px)
