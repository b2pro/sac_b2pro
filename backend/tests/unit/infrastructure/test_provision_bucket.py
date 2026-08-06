from typing import Any

import pytest
from botocore.exceptions import ClientError

from sac.infrastructure.provision_bucket import (
    MULTIPART_RULE_ID,
    _mostrar,
    aplicar,
    cors_configuration,
    mesclar_multipart,
    multipart_lifecycle,
    regras_atuais,
)


def _erro(codigo: str, operacao: str) -> ClientError:
    return ClientError({"Error": {"Code": codigo, "Message": codigo}}, operacao)


class FakeS3:
    """Client S3 de mentira: registra as chamadas e levanta o erro programado
    para cada operacao, como MinIO e Wasabi fazem de formas diferentes.
    """

    def __init__(
        self,
        erros: dict[str, ClientError] | None = None,
        regras: list[dict[str, Any]] | None = None,
        cors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self._erros = erros or {}
        self._regras = regras
        self._cors = cors

    def _executar(self, operacao: str, **kwargs: Any) -> dict[str, Any]:
        self.chamadas.append((operacao, kwargs))
        erro = self._erros.get(operacao)
        if erro is not None:
            raise erro
        return {}

    def put_bucket_cors(self, **kwargs: Any) -> dict[str, Any]:
        return self._executar("put_bucket_cors", **kwargs)

    def put_bucket_lifecycle_configuration(self, **kwargs: Any) -> dict[str, Any]:
        return self._executar("put_bucket_lifecycle_configuration", **kwargs)

    def get_bucket_lifecycle_configuration(self, **kwargs: Any) -> dict[str, Any]:
        self.chamadas.append(("get_bucket_lifecycle_configuration", kwargs))
        erro = self._erros.get("get_bucket_lifecycle_configuration")
        if erro is not None:
            raise erro
        if self._regras is None:
            raise _erro("NoSuchLifecycleConfiguration", "GetBucketLifecycleConfiguration")
        return {"Rules": self._regras}

    def get_bucket_cors(self, **kwargs: Any) -> dict[str, Any]:
        self.chamadas.append(("get_bucket_cors", kwargs))
        erro = self._erros.get("get_bucket_cors")
        if erro is not None:
            raise erro
        if self._cors is None:
            raise _erro("NoSuchCORSConfiguration", "GetBucketCors")
        return {"CORSRules": self._cors}


def test_cors_permite_so_o_header_que_dispara_o_preflight() -> None:
    regra = cors_configuration(["https://sac.b2pro.com.br"])["CORSRules"][0]

    assert regra["AllowedOrigins"] == ["https://sac.b2pro.com.br"]
    # `Content-Type` e o unico header que o PUT do navegador manda: a assinatura
    # vai na query string, entao nao ha x-amz-* nem Authorization para liberar.
    assert regra["AllowedHeaders"] == ["Content-Type"]
    assert regra["AllowedMethods"] == ["PUT", "GET", "HEAD"]
    assert regra["ExposeHeaders"] == ["ETag"]


def test_cors_nunca_libera_origem_curinga() -> None:
    origens = cors_configuration(["https://a.example", "https://b.example"])["CORSRules"][0]

    assert "*" not in origens["AllowedOrigins"]
    assert origens["AllowedOrigins"] == ["https://a.example", "https://b.example"]


def test_regra_de_multipart_nao_expira_objeto_nenhum() -> None:
    """A regra e higiene de upload multipart. Se algum dia ganhar `Expiration`,
    apagaria anexos confirmados: as chaves nascem na posicao final, sem prefixo de
    staging que permita distinguir abandonado de em uso.
    """
    regra = multipart_lifecycle(1)["Rules"][0]

    assert regra["ID"] == MULTIPART_RULE_ID
    assert regra["AbortIncompleteMultipartUpload"] == {"DaysAfterInitiation": 1}
    assert "Expiration" not in regra
    assert "NoncurrentVersionExpiration" not in regra


def test_aplicar_no_caminho_feliz_configura_as_duas_politicas() -> None:
    cliente = FakeS3()

    falhas = aplicar(cliente, "sac-prod", ["https://sac.b2pro.com.br"], 1)

    assert falhas == []
    # o ciclo de vida e lido antes de ser escrito, para nao apagar outras regras
    assert [nome for nome, _ in cliente.chamadas] == [
        "put_bucket_cors",
        "get_bucket_lifecycle_configuration",
        "put_bucket_lifecycle_configuration",
    ]
    _, kwargs = cliente.chamadas[0]
    assert kwargs["Bucket"] == "sac-prod"


def test_aplicar_tolera_o_que_o_minio_nao_implementa() -> None:
    """Em desenvolvimento as duas politicas sao recusadas pelo MinIO — CORS porque
    nao existe lá, ciclo de vida porque ele exige Expiration. Nenhuma das duas e
    falha de provisionamento: o MinIO ja libera CORS por padrao.
    """
    cliente = FakeS3(
        {
            "put_bucket_cors": _erro("NotImplemented", "PutBucketCors"),
            "put_bucket_lifecycle_configuration": _erro(
                "InvalidArgument", "PutBucketLifecycleConfiguration"
            ),
        }
    )

    assert aplicar(cliente, "sac-dev", ["http://localhost:5173"], 1) == []


def test_aplicar_reporta_falha_real_e_nao_para_na_primeira() -> None:
    cliente = FakeS3({"put_bucket_cors": _erro("AccessDenied", "PutBucketCors")})

    falhas = aplicar(cliente, "sac-prod", ["https://sac.b2pro.com.br"], 1)

    assert falhas == ["CORS: AccessDenied"]
    # credencial sem permissao de CORS nao impede tentar o ciclo de vida
    assert "put_bucket_lifecycle_configuration" in [nome for nome, _ in cliente.chamadas]


def test_aplicar_sem_dias_de_multipart_nao_toca_o_ciclo_de_vida() -> None:
    cliente = FakeS3()

    assert aplicar(cliente, "sac-prod", ["https://sac.b2pro.com.br"], None) == []
    assert [nome for nome, _ in cliente.chamadas] == ["put_bucket_cors"]


def test_bucket_sem_ciclo_de_vida_nao_e_erro() -> None:
    assert regras_atuais(FakeS3(), "sac-prod") == []


def test_falha_real_ao_ler_ciclo_de_vida_sobe() -> None:
    cliente = FakeS3(
        {"get_bucket_lifecycle_configuration": _erro("AccessDenied", "GetBucketLifecycle")}
    )

    with pytest.raises(ClientError):
        regras_atuais(cliente, "sac-prod")


def test_mesclar_preserva_regra_de_outro_id() -> None:
    """PutBucketLifecycleConfiguration substitui a configuracao inteira do bucket.
    Reaplicar so a regra de multipart apagaria em silencio uma regra criada
    depois — por exemplo a de staging, se o projeto seguir por esse caminho.
    """
    staging = {
        "ID": "expira-staging",
        "Status": "Enabled",
        "Filter": {"Prefix": "staging/"},
        "Expiration": {"Days": 1},
    }

    mesclado = mesclar_multipart([staging], 1)

    ids = [regra["ID"] for regra in mesclado["Rules"]]
    assert ids == ["expira-staging", MULTIPART_RULE_ID]
    assert staging in mesclado["Rules"]


def test_mesclar_substitui_a_propria_regra_em_vez_de_duplicar() -> None:
    antiga = multipart_lifecycle(7)["Rules"][0]

    mesclado = mesclar_multipart([antiga], 1)

    assert len(mesclado["Rules"]) == 1
    assert mesclado["Rules"][0]["AbortIncompleteMultipartUpload"] == {"DaysAfterInitiation": 1}


def test_aplicar_manda_ao_bucket_a_configuracao_mesclada() -> None:
    staging = {
        "ID": "expira-staging",
        "Status": "Enabled",
        "Filter": {"Prefix": "staging/"},
        "Expiration": {"Days": 1},
    }
    cliente = FakeS3(regras=[staging])

    assert aplicar(cliente, "sac-prod", ["https://sac.b2pro.com.br"], 1) == []

    enviado = next(
        kwargs for nome, kwargs in cliente.chamadas if nome == "put_bucket_lifecycle_configuration"
    )
    ids = [regra["ID"] for regra in enviado["LifecycleConfiguration"]["Rules"]]
    assert ids == ["expira-staging", MULTIPART_RULE_ID]


def test_conferir_nao_afirma_ausencia_quando_nao_conseguiu_ler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AccessDenied nao e ausencia de configuracao.

    O modo de falha que este teste fecha aconteceu de verdade num primeiro
    deploy: a credencial nao tinha permissao de bucket, o `--conferir` respondeu
    "CORS atual: nenhum (AccessDenied)", e a conclusao natural -- errada -- foi
    que o bucket estava sem CORS. O CORS estava aplicado; quem nao conseguia
    ler era a credencial. Um diagnostico que afirma o que nao verificou custa
    mais caro que um diagnostico que se cala.
    """
    cliente = FakeS3(
        erros={
            "get_bucket_cors": _erro("AccessDenied", "GetBucketCors"),
            "get_bucket_lifecycle_configuration": _erro(
                "AccessDenied", "GetBucketLifecycleConfiguration"
            ),
        }
    )

    with caplog.at_level("INFO", logger="sac.provisionamento"):
        _mostrar(cliente, "sac-prod")

    texto = caplog.text
    assert "nao foi possivel verificar" in texto
    assert "AccessDenied" in texto
    assert "nenhum" not in texto


def test_conferir_afirma_ausencia_quando_o_bucket_realmente_nao_tem(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O outro lado: NoSuchCORSConfiguration e ausencia de verdade, e continua
    sendo reportada como ausencia -- senao o teste acima teria sido "resolvido"
    tornando a saida vaga para todo caso, o que perde informacao real."""
    with caplog.at_level("INFO", logger="sac.provisionamento"):
        _mostrar(FakeS3(), "sac-prod")

    texto = caplog.text
    assert "nenhum" in texto
    assert "nao foi possivel verificar" not in texto


def test_conferir_mostra_a_configuracao_quando_consegue_ler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cliente = FakeS3(
        cors=[{"AllowedOrigins": ["https://solucionix.com.br"]}],
        regras=[{"ID": MULTIPART_RULE_ID}],
    )

    with caplog.at_level("INFO", logger="sac.provisionamento"):
        _mostrar(cliente, "sac-prod")

    texto = caplog.text
    assert "solucionix.com.br" in texto
    assert MULTIPART_RULE_ID in texto
    assert "nao foi possivel verificar" not in texto
    assert "nenhum" not in texto
