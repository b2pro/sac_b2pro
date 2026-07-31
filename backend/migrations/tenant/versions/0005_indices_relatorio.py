"""indices de performance para dashboard/relatorio/galeria (Fase 3)

Revision ID: 0005_indices_relatorio
Revises: 0004_anexos
Create Date: 2026-07-31

"""

from alembic import op

revision = "0005_indices_relatorio"
down_revision = "0004_anexos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # deleted_at (exclusao logica) e o filtro base de praticamente toda query
    # de dashboard/relatorio (repositories_reporting.py); os compostos abaixo
    # lideram com ele em vez de indexar cada coluna sozinha.
    op.create_index(
        "ix_tickets_deleted_at_status", "tickets", ["deleted_at", "status"], schema="tenant"
    )
    op.create_index(
        "ix_tickets_deleted_at_brand_id", "tickets", ["deleted_at", "brand_id"], schema="tenant"
    )
    op.create_index(
        "ix_tickets_deleted_at_opened_at", "tickets", ["deleted_at", "opened_at"], schema="tenant"
    )
    # closed_at aparece como predicado real (closed_at IS NOT NULL no tempo medio
    # de resolucao). approved_at/declined_at, ao contrario, so aparecem dentro de
    # count(*) FILTER (...) do dashboard: FILTER e avaliado linha a linha depois
    # da varredura, nunca vira predicado de indice — por isso nao ha indice para
    # essas duas colunas aqui.
    op.create_index(
        "ix_tickets_deleted_at_closed_at", "tickets", ["deleted_at", "closed_at"], schema="tenant"
    )
    # Galeria de midias (_media_stmt): filtra deleted_at/status e ordena por
    # created_at com paginacao - o composto cobre WHERE e ORDER BY na mesma
    # leitura de indice.
    op.create_index(
        "ix_ticket_attachments_deleted_at_status_created_at",
        "ticket_attachments",
        ["deleted_at", "status", "created_at"],
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticket_attachments_deleted_at_status_created_at",
        table_name="ticket_attachments",
        schema="tenant",
    )
    op.drop_index("ix_tickets_deleted_at_closed_at", table_name="tickets", schema="tenant")
    op.drop_index("ix_tickets_deleted_at_opened_at", table_name="tickets", schema="tenant")
    op.drop_index("ix_tickets_deleted_at_brand_id", table_name="tickets", schema="tenant")
    op.drop_index("ix_tickets_deleted_at_status", table_name="tickets", schema="tenant")
