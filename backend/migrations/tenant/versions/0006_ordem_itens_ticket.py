"""ordem de insercao estavel para os itens do ticket

Revision ID: 0006_ordem_itens_ticket
Revises: 0005_indices_relatorio
Create Date: 2026-07-31

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSequence, DropSequence

revision = "0006_ordem_itens_ticket"
down_revision = "0005_indices_relatorio"
branch_labels = None
depends_on = None


def _tenant_schema() -> str:
    """Schema real deste tenant.

    op.add_column/alter_column/drop_column nao montam um sa.Table de verdade e
    por isso ignoram o schema_translate_map aplicado na conexao pelo env.py:
    renderiam o literal "tenant". Mesmo contorno ja usado em 0004_anexos.
    Construtos nativos (sa.Table, sa.Sequence) continuam usando "tenant".
    """
    translate_map = op.get_bind().get_execution_options().get("schema_translate_map") or {}
    return str(translate_map.get("tenant", "tenant"))


def _ticket_items() -> sa.Table:
    return sa.Table(
        "ticket_items",
        sa.MetaData(),
        sa.Column("id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("seq", sa.BigInteger()),
        schema="tenant",
    )


def upgrade() -> None:
    schema = _tenant_schema()
    items = _ticket_items()
    op.add_column("ticket_items", sa.Column("seq", sa.BigInteger(), nullable=True), schema=schema)
    # Backfill deterministico: created_at empata entre itens gravados na mesma
    # transacao, entao o id desempata. Nao depende da ordem de varredura do
    # Postgres, logo todo tenant (e uma reexecucao) chega ao mesmo resultado.
    ordenados = sa.select(
        items.c.id.label("id"),
        sa.func.row_number().over(order_by=(items.c.created_at, items.c.id)).label("ordem"),
    ).subquery()
    op.execute(items.update().values(seq=ordenados.c.ordem).where(items.c.id == ordenados.c.id))
    # row_number vai de 1 ate a contagem de linhas: a sequence comeca no proximo
    # valor livre para nao colidir com o que acabou de ser preenchido.
    total = op.get_bind().execute(sa.select(sa.func.count()).select_from(items)).scalar() or 0
    op.execute(CreateSequence(sa.Sequence("ticket_item_seq", start=total + 1, schema="tenant")))
    op.alter_column("ticket_items", "seq", nullable=False, schema=schema)


def downgrade() -> None:
    op.drop_column("ticket_items", "seq", schema=_tenant_schema())
    op.execute(DropSequence(sa.Sequence("ticket_item_seq", schema="tenant")))
