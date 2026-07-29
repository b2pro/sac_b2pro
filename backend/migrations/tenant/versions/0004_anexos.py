"""anexos de ticket e preview da foto do produto

Revision ID: 0004_anexos
Revises: 0003_tickets
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op

revision = "0004_anexos"
down_revision = "0003_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("preview_key", sa.String(400), nullable=True),
        sa.Column("preview_medium_key", sa.String(400), nullable=True),
        sa.Column("preview_status", sa.String(12), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes > 0", name="ck_ticket_attachments_size"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_attachments_ticket_id"
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_ticket_attachments_ticket_id", "ticket_attachments", ["ticket_id"], schema="tenant"
    )
    op.create_index(
        "ix_ticket_attachments_status", "ticket_attachments", ["status"], schema="tenant"
    )
    # op.add_column nao usa um sa.Table real internamente (diferente de
    # create_table/create_index), entao nao respeita o schema_translate_map
    # aplicado na conexao pelo env.py: renderiza o schema literal recebido.
    # Resolvemos aqui o schema real do tenant a partir das execution_options
    # da conexao para que o ALTER TABLE va na schema correta.
    bind = op.get_bind()
    translate_map = bind.get_execution_options().get("schema_translate_map") or {}
    tenant_schema = translate_map.get("tenant", "tenant")
    op.add_column(
        "products",
        sa.Column("photo_preview_key", sa.String(255), nullable=True),
        schema=tenant_schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    translate_map = bind.get_execution_options().get("schema_translate_map") or {}
    tenant_schema = translate_map.get("tenant", "tenant")
    op.drop_column("products", "photo_preview_key", schema=tenant_schema)
    op.drop_table("ticket_attachments", schema="tenant")
