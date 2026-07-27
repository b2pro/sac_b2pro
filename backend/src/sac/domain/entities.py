import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sac.domain.errors import ValidationError
from sac.domain.permissions import Role

TENANT_SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def validate_slug(slug: str) -> str:
    if not TENANT_SLUG_RE.fullmatch(slug):
        raise ValidationError(
            "slug invalido: use 2 a 40 caracteres entre a-z, 0-9 e _",
            details={"slug": slug},
        )
    return slug


class TenantStatus(StrEnum):
    ATIVA = "ativa"
    TESTE = "teste"
    SUSPENSA = "suspensa"
    INATIVA = "inativa"


@dataclass
class User:
    id: UUID
    name: str
    email: str
    password_hash: str
    is_super_admin: bool = False
    active: bool = True
    deleted_at: datetime | None = None


@dataclass
class Tenant:
    id: UUID
    slug: str
    name: str
    status: TenantStatus = TenantStatus.ATIVA
    modules: dict[str, bool] = field(default_factory=dict)
    deleted_at: datetime | None = None

    @property
    def schema_name(self) -> str:
        return f"t_{self.slug}"


@dataclass
class UserTenant:
    user_id: UUID
    tenant_id: UUID
    role: Role
    active: bool = True
