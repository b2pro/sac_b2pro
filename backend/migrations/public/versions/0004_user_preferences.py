"""Preferencias de usuario: tema e opcoes de notificacao

Revision ID: 0004_user_preferences
Revises: 0003_pg_trgm
Create Date: 2026-08-03

Tabela global (schema public), nao por schema de tenant: usuarios sao
globais no SAC-B2PRO e um mesmo usuario pode pertencer a varios tenants, por
isso a preferencia de tema/notificacao o acompanha em qualquer um deles em
vez de ser duplicada por tenant.

PK e o proprio user_id (relacao 1:1 com users): nao ha necessidade de id
proprio, e isso viabiliza upsert direto por ON CONFLICT (user_id).
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_user_preferences"
down_revision = "0003_pg_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("theme", sa.String(10), nullable=False, server_default="sistema"),
        sa.Column("notify_toast", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_sound", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
