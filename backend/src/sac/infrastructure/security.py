from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

from sac.application.ports import TokenPayload
from sac.domain.errors import AuthError
from sac.domain.permissions import Role
from sac.infrastructure.settings import Settings


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = _Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False


class JwtTokenService:
    def __init__(
        self, secret: str, algorithm: str, access_ttl: timedelta, refresh_ttl: timedelta
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    @classmethod
    def from_settings(cls, settings: Settings) -> "JwtTokenService":
        return cls(
            settings.jwt_secret,
            settings.jwt_algorithm,
            timedelta(minutes=settings.access_token_ttl_minutes),
            timedelta(days=settings.refresh_token_ttl_days),
        )

    def create_access(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str:
        return self._create(user_id, tenant_slug, role, is_super_admin, "access", self._access_ttl)

    def create_refresh(
        self, user_id: UUID, tenant_slug: str | None, role: Role | None, is_super_admin: bool
    ) -> str:
        return self._create(
            user_id, tenant_slug, role, is_super_admin, "refresh", self._refresh_ttl
        )

    def _create(
        self,
        user_id: UUID,
        tenant_slug: str | None,
        role: Role | None,
        is_super_admin: bool,
        token_type: str,
        ttl: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        claims: dict[str, object] = {
            "sub": str(user_id),
            "type": token_type,
            "sa": is_super_admin,
            "iat": now,
            "exp": now + ttl,
        }
        if tenant_slug is not None:
            claims["tenant"] = tenant_slug
        if role is not None:
            claims["role"] = role.value
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def decode(self, token: str, expected_type: str) -> TokenPayload:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise AuthError("token invalido ou expirado") from exc
        if claims.get("type") != expected_type:
            raise AuthError("tipo de token invalido")
        role_value = claims.get("role")
        return TokenPayload(
            user_id=UUID(claims["sub"]),
            tenant_slug=claims.get("tenant"),
            role=Role(role_value) if role_value else None,
            is_super_admin=bool(claims.get("sa", False)),
            token_type=expected_type,
        )
