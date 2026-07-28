from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TenantBase(DeclarativeBase):
    pass


class TenantTableMixin:
    __table_args__ = {"schema": "tenant"}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogModelBase(TenantTableMixin, TenantBase):
    __abstract__ = True

    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class BrandModel(CatalogModelBase):
    __tablename__ = "brands"


class DefectTypeModel(CatalogModelBase):
    __tablename__ = "defect_types"


class SolutionTypeModel(CatalogModelBase):
    __tablename__ = "solution_types"


class PurchaseChannelModel(CatalogModelBase):
    __tablename__ = "purchase_channels"


class ProductModel(TenantTableMixin, TenantBase):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    segment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CustomerModel(TenantTableMixin, TenantBase):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200))
    document: Mapped[str] = mapped_column(String(14), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
