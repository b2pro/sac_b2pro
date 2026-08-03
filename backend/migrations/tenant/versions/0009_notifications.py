"""tabela de notificacoes por tenant

Revision ID: 0009_notifications
Revises: 0008_indices_busca
Create Date: 2026-08-03

Base da Task 1 da Fase 4 (Acabamento): nenhuma outra parte do sistema
consome esta tabela ainda, as tasks seguintes fazem o fan-out, a emissao e a
API. Os dois indices cobrem os dois acessos do dropdown de notificacoes: o
parcial resolve a contagem/lista de nao lidas (read_at IS NULL e a minoria
depois de algum uso), o composto resolve a lista paginada completa ordenada
por created_at desc, que nao pode reusar o parcial porque nao filtra por
read_at.

"""

import sqlalchemy as sa
from alembic import op

revision = "0009_notifications"
down_revision = "0008_indices_busca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        # BigInteger para espelhar tickets.number (0003_tickets), a coluna de
        # origem que esta desnormalizada aqui.
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("snippet", sa.String(200), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_notifications_ticket_id"
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        schema="tenant",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created", table_name="notifications", schema="tenant")
    op.drop_index("ix_notifications_user_unread", table_name="notifications", schema="tenant")
    op.drop_table("notifications", schema="tenant")
