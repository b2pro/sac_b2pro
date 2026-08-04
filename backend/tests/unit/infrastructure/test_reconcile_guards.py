"""Guardas da reconciliacao de orfaos, que apaga objeto do bucket sem volta.

Nenhum destes testes exercita a varredura em si (isso e
tests/unit/application/test_storage_reconcile.py e
tests/integration/test_worker.py). Eles protegem as duas condicoes que, se
quebrarem em silencio, transformam a varredura em perda de anexo vivo: a margem
de idade configurada e a cobertura das colunas de chave.
"""

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from sac.infrastructure.models_tenant import ProductModel, TicketAttachmentModel
from sac.infrastructure.repositories_attachments import (
    ATTACHMENT_KEY_COLUMNS,
    PRODUCT_KEY_COLUMNS,
)
from sac.infrastructure.settings import Settings


def _colunas_de_chave(model: Any) -> set[str]:
    return {nome for nome in model.__table__.columns.keys() if nome.endswith("_key")}


def test_margem_de_idade_da_reconciliacao_nao_pode_ser_zerada() -> None:
    """`SAC_RECONCILE_ORPHANS_HOURS=0` num .env ou num override de compose
    desligaria a unica protecao do upload em voo - e a foto de produto nao tem
    linha nenhuma no banco antes do confirmar, entao 0 destruiria todo upload de
    foto em andamento na proxima passada. Comentario nao segura operacao
    irreversivel: o floor e validado pelo proprio Settings.
    """
    with pytest.raises(PydanticValidationError):
        Settings(reconcile_orphans_hours=0)
    with pytest.raises(PydanticValidationError):
        Settings(reconcile_orphans_hours=-1)
    assert Settings().reconcile_orphans_hours == 24
    assert Settings(reconcile_orphans_hours=1).reconcile_orphans_hours == 1


def test_known_keys_cobre_todas_as_colunas_de_chave_de_anexo() -> None:
    """Amarra a consulta de chaves conhecidas ao schema: uma coluna de chave
    nova em ticket_attachments falha aqui, alto e claro, em vez de virar
    delecao silenciosa do objeto que ela aponta. A heuristica e o sufixo `_key`,
    convencao que as duas tabelas seguem hoje.
    """
    assert {coluna.key for coluna in ATTACHMENT_KEY_COLUMNS} == _colunas_de_chave(
        TicketAttachmentModel
    )


def test_known_keys_cobre_todas_as_colunas_de_chave_de_foto_de_produto() -> None:
    assert {coluna.key for coluna in PRODUCT_KEY_COLUMNS} == _colunas_de_chave(ProductModel)
