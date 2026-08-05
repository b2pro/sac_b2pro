from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService

SEGREDO = "segredo-de-teste-com-32-bytes-ou-mais"


def _service(access_ttl: timedelta = timedelta(minutes=15)) -> JwtTokenService:
    return JwtTokenService(SEGREDO, "HS256", access_ttl, timedelta(days=7))


def test_hash_e_verificacao_de_senha() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("senha-forte-123")
    assert password_hash != "senha-forte-123"
    assert hasher.verify(password_hash, "senha-forte-123")
    assert not hasher.verify(password_hash, "senha-errada")
    assert not hasher.verify("hash-invalido", "qualquer")


def test_roundtrip_de_access_token() -> None:
    service = _service()
    user_id = uuid4()
    token = service.create_access(user_id, "b2pro", Role.ADMIN, False, credentials_version=3)
    payload = service.decode(token, expected_type="access")
    assert payload.user_id == user_id
    assert payload.tenant_slug == "b2pro"
    assert payload.role is Role.ADMIN
    assert payload.is_super_admin is False
    assert payload.token_type == "access"
    assert payload.credentials_version == 3


def test_token_sem_claim_de_versao_decodifica_como_zero() -> None:
    """Zero nunca bate com a versao do banco (comeca em 1), entao um token do
    formato antigo e recusado no refresh em vez de passar por omissao."""
    service = _service()
    token = jwt.encode(
        {"sub": str(uuid4()), "type": "access", "sa": True},
        SEGREDO,
        algorithm="HS256",
    )
    assert service.decode(token, expected_type="access").credentials_version == 0


def test_token_de_super_admin_sem_tenant() -> None:
    service = _service()
    token = service.create_access(uuid4(), None, None, True, credentials_version=1)
    payload = service.decode(token, expected_type="access")
    assert payload.tenant_slug is None
    assert payload.role is None
    assert payload.is_super_admin is True


def test_tipo_de_token_errado_e_rejeitado() -> None:
    service = _service()
    refresh = service.create_refresh(uuid4(), None, None, True, credentials_version=1)
    with pytest.raises(AuthError):
        service.decode(refresh, expected_type="access")


def test_token_expirado_e_rejeitado() -> None:
    service = _service(access_ttl=timedelta(seconds=-1))
    token = service.create_access(uuid4(), None, None, True, credentials_version=1)
    with pytest.raises(AuthError):
        service.decode(token, expected_type="access")


def test_segredo_errado_e_rejeitado() -> None:
    token = _service().create_access(uuid4(), None, None, True, credentials_version=1)
    outro = JwtTokenService(
        "outro-segredo-de-teste-com-32-bytes", "HS256", timedelta(minutes=15), timedelta(days=7)
    )
    with pytest.raises(AuthError):
        outro.decode(token, expected_type="access")
