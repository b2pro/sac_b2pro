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


def generate_previews(
    data: bytes, thumb_px: int = 400, medium_px: int = 1200
) -> tuple[bytes, bytes]:
    try:
        with Image.open(io.BytesIO(data)) as original:
            original.load()
            rgb = original.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("arquivo nao e uma imagem valida") from exc
    return _resize(rgb, thumb_px), _resize(rgb, medium_px)
