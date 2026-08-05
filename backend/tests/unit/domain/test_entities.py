from uuid import uuid4

import pytest

from sac.domain.entities import Tenant, TenantStatus, User, validate_slug
from sac.domain.errors import ValidationError


def test_slug_valido() -> None:
    assert validate_slug("kodi_staleks_01") == "kodi_staleks_01"


@pytest.mark.parametrize("slug", ["", "a", "Maiusculo", "com-hifen", "com espaco", "a" * 41])
def test_slug_invalido(slug: str) -> None:
    with pytest.raises(ValidationError):
        validate_slug(slug)


def test_schema_name_deriva_do_slug() -> None:
    tenant = Tenant(id=uuid4(), slug="b2pro", name="B2PRO")
    assert tenant.schema_name == "t_b2pro"
    assert tenant.status is TenantStatus.ATIVA
    assert tenant.modules == {}


def test_trocar_senha_incrementa_a_versao_de_credencial() -> None:
    """A invariante mora no dominio para nao depender de quem chama lembrar de
    incrementar: qualquer caminho que troque a senha invalida os tokens antigos."""
    user = User(id=uuid4(), name="Ana", email="ana@b2.com", password_hash="antigo")
    assert user.credentials_version == 1

    user.change_password("novo")

    assert user.password_hash == "novo"
    assert user.credentials_version == 2
