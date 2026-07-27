from uuid import uuid4

import pytest

from sac.domain.entities import Tenant, TenantStatus, validate_slug
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
