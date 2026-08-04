from datetime import datetime
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from sac.application.ports_attachments import ObjectHead
from sac.domain.errors import StorageUnavailableError
from sac.infrastructure.settings import Settings

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


def build_client(endpoint_url: str, region: str, access_key: str, secret_key: str) -> Any:
    """Client S3 cru. Publico porque o provisionamento do bucket
    (provision_bucket.py) precisa do mesmo client, com a mesma assinatura v4 e o
    mesmo addressing style que o gateway usa."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class S3Storage:
    """Gateway S3. Mantem dois clients: o interno faz HEAD/download/upload do
    servidor; o publico assina as URLs entregues ao navegador. A assinatura cobre
    o header Host, por isso trocar o endpoint depois de assinar invalidaria a URL.
    """

    def __init__(self, internal: Any, public: Any, bucket: str) -> None:
        self._internal = internal
        self._public = public
        self._bucket = bucket

    @classmethod
    def from_values(
        cls,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3Storage":
        internal = build_client(endpoint_url, region, access_key, secret_key)
        public = (
            internal
            if not public_endpoint_url or public_endpoint_url == endpoint_url
            else build_client(public_endpoint_url, region, access_key, secret_key)
        )
        return cls(internal, public, bucket)

    def presigned_put(self, key: str, content_type: str, ttl_seconds: int) -> str:
        # Sem limite de tamanho por design: presigned URL de put_object nao
        # suporta content-length-range (isso e feature de POST policy). Quem
        # tiver a URL pode gravar mais bytes que o declarado; a confirmacao
        # rejeita via HEAD e o anexo expira, mas o objeto fica no bucket. Risco
        # aceito e regra de ciclo de vida que o mitiga estao em
        # docs/armazenamento-anexos.md.
        try:
            return str(
                self._public.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket,
                        "Key": key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=ttl_seconds,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def presigned_get(self, key: str, ttl_seconds: int) -> str:
        try:
            return str(
                self._public.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=ttl_seconds,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def head(self, key: str) -> ObjectHead | None:
        try:
            res = self._internal.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND_CODES:
                return None
            raise StorageUnavailableError("storage indisponivel") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError("storage indisponivel") from exc
        return ObjectHead(
            content_type=str(res.get("ContentType", "")),
            size_bytes=int(res.get("ContentLength", 0)),
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._internal.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            res = self._internal.get_object(Bucket=self._bucket, Key=key)
            return bytes(res["Body"].read())
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def list_keys(self, prefix: str) -> list[tuple[str, datetime]]:
        """Todas as chaves sob o prefixo, com o last_modified que o proprio
        bucket informa (ja timezone-aware, em UTC). Pagina com o paginator: um
        list_objects_v2 cru pararia em 1000 objetos e a reconciliacao passaria a
        ver como inexistente tudo o que ficou de fora - o que nao apaga nada
        indevido (chave ausente da listagem nunca e apagada), mas deixaria orfaos
        eternos no bucket.
        """
        try:
            paginator = self._internal.get_paginator("list_objects_v2")
            return [
                (str(obj["Key"]), obj["LastModified"])
                for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
                for obj in page.get("Contents", [])
            ]
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("storage indisponivel") from exc

    def delete(self, key: str) -> None:
        # Idempotente por design: apagar uma chave que nao existe nao e erro.
        # delete_object do S3 ja nao levanta ClientError de not-found na
        # pratica, mas o codigo trata esse caso mesmo assim para nao depender
        # dessa leniencia de comportamento do servidor.
        try:
            self._internal.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND_CODES:
                return
            raise StorageUnavailableError("storage indisponivel") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError("storage indisponivel") from exc


def build_storage(settings: Settings) -> S3Storage:
    return S3Storage.from_values(
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_endpoint_url,
        region=settings.s3_region,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
