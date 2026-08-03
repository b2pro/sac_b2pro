"""Indices GIN de trigrama para os identificadores da busca global

Revision ID: 0010_indices_busca_global
Revises: 0009_notifications
Create Date: 2026-08-03

A busca global (Task 7 da Fase 4) casa cliente por documento/telefone/email e
produto por SKU, alem dos indices de nome/order_code ja criados em
0008_indices_busca. Mesmo racional daquela migration: curinga a esquerda
(`ilike '%termo%'`) nao alcanca b-tree nenhum, entao GIN com `gin_trgm_ops`
(extensao pg_trgm) e o indice que atende.

pg_trgm ja foi criada na chain public (0003_pg_trgm): e extensao por
database, nao por schema de tenant, e nao repetimos o CREATE EXTENSION aqui.

O opclass precisa ser qualificado como `public.gin_trgm_ops`: esta migration
roda com search_path no schema do tenant, e sem o prefixo o Postgres nao acha
a opclass ("operator class gin_trgm_ops does not exist for access method
gin") -- ver 0008_indices_busca para o erro exato.
"""

from alembic import op

revision = "0010_indices_busca_global"
down_revision = "0009_notifications"
branch_labels = None
depends_on = None

# (nome, tabela, coluna) dos quatro indices GIN de trigrama.
_TRGM_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_customers_document_trgm", "customers", "document"),
    ("ix_customers_email_trgm", "customers", "email"),
    ("ix_customers_phone_trgm", "customers", "phone"),
    ("ix_products_sku_trgm", "products", "sku"),
)


def upgrade() -> None:
    for name, table, column in _TRGM_INDEXES:
        op.create_index(
            name,
            table,
            [column],
            schema="tenant",
            postgresql_using="gin",
            postgresql_ops={column: "public.gin_trgm_ops"},
        )


def downgrade() -> None:
    for name, table, _ in _TRGM_INDEXES:
        op.drop_index(name, table_name=table, schema="tenant")
