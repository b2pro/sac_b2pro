from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CatalogKind(StrEnum):
    BRAND = "brand"
    DEFECT_TYPE = "defect_type"
    SOLUTION_TYPE = "solution_type"
    PURCHASE_CHANNEL = "purchase_channel"


@dataclass
class CatalogItem:
    id: UUID
    name: str
    description: str | None = None
    active: bool = True
    deleted_at: datetime | None = None
