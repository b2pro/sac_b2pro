from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Customer:
    id: UUID
    name: str
    document: str
    phone: str | None = None
    email: str | None = None
    cep: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    active: bool = True
    deleted_at: datetime | None = None


@dataclass
class Product:
    id: UUID
    name: str
    sku: str
    segment: str | None = None
    description: str | None = None
    photo_key: str | None = None
    active: bool = True
    deleted_at: datetime | None = None
