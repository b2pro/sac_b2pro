"""Provisiona no bucket o que o codigo nao consegue garantir: a politica de CORS
que o navegador precisa para o PUT direto e a higiene de uploads multipart
abandonados.

Existe porque o MinIO de desenvolvimento e permissivo onde o Wasabi nao e:
`PutBucketCors` nem esta implementado no MinIO (responde NotImplemented), entao
nenhum teste local detecta a falta da politica e o primeiro deploy quebraria o
upload no navegador com um erro opaco. Rodar uma vez por bucket, por ambiente.

    python -m sac.infrastructure.provision_bucket --origem https://sac.b2pro.com.br

As credenciais e o bucket vem das mesmas variaveis SAC_S3_* que o backend usa.
Idempotente: reaplicar a mesma politica nao muda nada. Use --conferir para so
mostrar o que esta no bucket hoje, sem escrever.

O que este script NAO faz, de proposito: expirar objetos nunca confirmados. As
chaves nascem na posicao final (`{tenant}/{ticket}/...`), sem prefixo de staging,
e a confirmacao so muda uma linha no banco — nenhum atributo do objeto no bucket
distingue confirmado de abandonado. Uma regra de Expiration por prefixo apagaria
anexos em uso. Ver docs/armazenamento-anexos.md.
"""

import argparse
import json
import logging
import sys
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import build_client

logger = logging.getLogger("sac.provisionamento")

# `Content-Type` e o header que dispara o preflight (ver putToStorage em
# frontend/src/lib/attachments.ts); PUT e o upload direto e GET/HEAD servem o
# download e o preview. ExposeHeaders com ETag deixa o navegador ler a resposta
# do PUT. Sem `*` em AllowedOrigins: uma URL assinada que vaze nao deve virar
# upload a partir de qualquer site.
ALLOWED_METHODS = ["PUT", "GET", "HEAD"]
ALLOWED_HEADERS = ["Content-Type"]
EXPOSE_HEADERS = ["ETag"]
MAX_AGE_SECONDS = 3000

MULTIPART_RULE_ID = "abortar-multipart-incompleto"


def cors_configuration(origens: list[str]) -> dict[str, Any]:
    return {
        "CORSRules": [
            {
                "AllowedOrigins": origens,
                "AllowedMethods": ALLOWED_METHODS,
                "AllowedHeaders": ALLOWED_HEADERS,
                "ExposeHeaders": EXPOSE_HEADERS,
                "MaxAgeSeconds": MAX_AGE_SECONDS,
            }
        ]
    }


def multipart_lifecycle(dias: int) -> dict[str, Any]:
    """Descarta partes de upload multipart que ficaram pela metade. Nao e a
    mitigacao de objetos orfaos: o upload do SAC e PUT simples, entao esta regra
    e higiene de bucket, nao limpeza de anexo abandonado.
    """
    return {
        "Rules": [
            {
                "ID": MULTIPART_RULE_ID,
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": dias},
            }
        ]
    }


def _mostrar(cliente: Any, bucket: str) -> None:
    try:
        atual = cliente.get_bucket_cors(Bucket=bucket)
        logger.info("CORS atual: %s", json.dumps(atual.get("CORSRules"), default=str))
    except ClientError as erro:
        logger.info("CORS atual: nenhum (%s)", erro.response["Error"].get("Code"))
    try:
        atual = cliente.get_bucket_lifecycle_configuration(Bucket=bucket)
        logger.info("Ciclo de vida atual: %s", json.dumps(atual.get("Rules"), default=str))
    except ClientError as erro:
        logger.info("Ciclo de vida atual: nenhum (%s)", erro.response["Error"].get("Code"))


def aplicar(cliente: Any, bucket: str, origens: list[str], multipart_dias: int | None) -> list[str]:
    """Aplica as politicas e devolve a lista de falhas em linguagem humana. Uma
    falha nao impede a proxima: CORS e ciclo de vida sao independentes, e no MinIO
    o CORS falha por design sem que isso diga nada sobre o resto.
    """
    falhas: list[str] = []

    try:
        cliente.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_configuration(origens))
        logger.info("CORS aplicado para %s", ", ".join(origens))
    except (ClientError, BotoCoreError) as erro:
        codigo = (
            erro.response["Error"].get("Code")
            if isinstance(erro, ClientError)
            else type(erro).__name__
        )
        if codigo == "NotImplemented":
            # MinIO: esperado em desenvolvimento, e ele ja libera CORS por padrao.
            logger.warning(
                "CORS nao aplicado: este storage nao implementa PutBucketCors "
                "(MinIO responde assim, e nao precisa da politica). Em Wasabi isto e erro."
            )
        else:
            falhas.append(f"CORS: {codigo}")
            logger.error("CORS falhou: %s", erro)

    if multipart_dias is not None:
        try:
            cliente.put_bucket_lifecycle_configuration(
                Bucket=bucket, LifecycleConfiguration=multipart_lifecycle(multipart_dias)
            )
            logger.info("Regra %s aplicada (%s dias)", MULTIPART_RULE_ID, multipart_dias)
        except (ClientError, BotoCoreError) as erro:
            codigo = (
                erro.response["Error"].get("Code")
                if isinstance(erro, ClientError)
                else type(erro).__name__
            )
            if codigo == "InvalidArgument":
                # MinIO recusa regra sem Expiration; Wasabi e S3 aceitam.
                logger.warning(
                    "Ciclo de vida nao aplicado: este storage recusa regra so de "
                    "AbortIncompleteMultipartUpload (o MinIO exige Expiration)."
                )
            else:
                falhas.append(f"ciclo de vida: {codigo}")
                logger.error("Ciclo de vida falhou: %s", erro)

    return falhas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="sac-provisionar-bucket",
        description="Aplica CORS e higiene de multipart no bucket de anexos.",
    )
    parser.add_argument(
        "--origem",
        action="append",
        default=[],
        metavar="URL",
        help="origem exata do frontend (repita para mais de um ambiente)",
    )
    parser.add_argument(
        "--multipart-dias",
        type=int,
        default=1,
        help="dias para abortar upload multipart incompleto (0 desliga a regra)",
    )
    parser.add_argument(
        "--conferir",
        action="store_true",
        help="so mostra as politicas atuais do bucket, sem escrever",
    )
    args = parser.parse_args()

    settings = Settings()
    cliente = build_client(
        settings.s3_endpoint_url,
        settings.s3_region,
        settings.s3_access_key,
        settings.s3_secret_key,
    )
    logger.info("bucket %s em %s", settings.s3_bucket, settings.s3_endpoint_url)

    if args.conferir:
        _mostrar(cliente, settings.s3_bucket)
        return

    if not args.origem:
        parser.error("informe pelo menos uma --origem (a URL exata do frontend)")

    falhas = aplicar(
        cliente,
        settings.s3_bucket,
        args.origem,
        args.multipart_dias if args.multipart_dias > 0 else None,
    )
    _mostrar(cliente, settings.s3_bucket)
    if falhas:
        logger.error("provisionamento incompleto: %s", "; ".join(falhas))
        sys.exit(1)
    logger.info("provisionamento concluido")


if __name__ == "__main__":
    main()
