import httpx
import pytest

from sac.domain.errors import StorageUnavailableError
from sac.infrastructure.storage import S3Storage


async def test_presigned_put_e_head(storage: S3Storage) -> None:
    chave = "acme/teste/arquivo.png"
    url = storage.presigned_put(chave, "image/png", ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.put(url, content=b"conteudo-fake", headers={"Content-Type": "image/png"})
    assert res.status_code == 200

    head = storage.head(chave)
    assert head is not None
    assert head.content_type == "image/png"
    assert head.size_bytes == len(b"conteudo-fake")


async def test_head_de_objeto_inexistente_e_none(storage: S3Storage) -> None:
    assert storage.head("acme/teste/nao-existe.png") is None


async def test_put_com_content_type_diferente_do_assinado_e_recusado(
    storage: S3Storage,
) -> None:
    chave = "acme/teste/mismatch.png"
    url = storage.presigned_put(chave, "image/png", ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.put(url, content=b"x", headers={"Content-Type": "application/pdf"})
    assert res.status_code >= 400
    assert storage.head(chave) is None


async def test_put_bytes_get_bytes_e_presigned_get(storage: S3Storage) -> None:
    chave = "acme/teste/servidor.webp"
    storage.put_bytes(chave, b"bytes-do-servidor", "image/webp")
    assert storage.get_bytes(chave) == b"bytes-do-servidor"

    url = storage.presigned_get(chave, ttl_seconds=60)
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
    assert res.status_code == 200
    assert res.content == b"bytes-do-servidor"


async def test_delete_remove_objeto_e_e_idempotente(storage: S3Storage) -> None:
    chave = "acme/teste/apagar.png"
    storage.put_bytes(chave, b"para apagar", "image/png")
    assert storage.head(chave) is not None

    storage.delete(chave)
    assert storage.head(chave) is None

    # idempotente: apagar de novo o mesmo objeto, ja ausente, nao e erro
    storage.delete(chave)

    # idempotente tambem para uma chave que nunca existiu no bucket
    storage.delete("acme/teste/nunca-existiu.png")


def test_url_publica_usa_o_endpoint_publico(storage_public: S3Storage) -> None:
    url = storage_public.presigned_get("acme/teste/qualquer.png", ttl_seconds=60)
    assert url.startswith("http://127.0.0.1:9000/")


def test_storage_fora_do_ar_vira_erro_de_dominio() -> None:
    quebrado = S3Storage.from_values(
        endpoint_url="http://localhost:9",
        public_endpoint_url="http://localhost:9",
        region="us-east-1",
        bucket="inexistente",
        access_key="x",
        secret_key="y",
    )
    with pytest.raises(StorageUnavailableError):
        quebrado.head("qualquer/chave.png")
