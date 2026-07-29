"""fila global de previews

Revision ID: 0002_preview_jobs
Revises: 677496d18d74
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0002_preview_jobs"
down_revision = "677496d18d74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preview_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_slug", sa.String(63), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(attachment_id IS NOT NULL)::int + (product_id IS NOT NULL)::int = 1",
            name="ck_preview_jobs_owner",
        ),
    )
    op.create_index("ix_preview_jobs_pendentes", "preview_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("preview_jobs")
