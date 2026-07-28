"""cadastros do tenant

Revision ID: 0002_cadastros
Revises: 0001_baseline
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_cadastros"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

CATALOG_TABLES = ("brands", "defect_types", "solution_types", "purchase_channels")


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for table in CATALOG_TABLES:
        op.create_table(
            table,
            sa.Column("name", sa.String(120), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            *_base_columns(),
            schema="tenant",
        )
    op.create_table(
        "products",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False, unique=True),
        sa.Column("segment", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_key", sa.String(255), nullable=True),
        *_base_columns(),
        schema="tenant",
    )
    op.create_table(
        "customers",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("document", sa.String(14), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("cep", sa.String(8), nullable=True),
        sa.Column("street", sa.String(200), nullable=True),
        sa.Column("number", sa.String(20), nullable=True),
        sa.Column("complement", sa.String(100), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        *_base_columns(),
        schema="tenant",
    )


def downgrade() -> None:
    for table in ("customers", "products", *reversed(CATALOG_TABLES)):
        op.drop_table(table, schema="tenant")
