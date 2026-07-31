"""Indices GIN de trigrama para a busca livre de tickets

Revision ID: 0008_indices_busca
Revises: 0007_indices_parciais
Create Date: 2026-07-31

A busca livre da Task 1 (Fase 3B) filtra cliente, produto e codigo do pedido
com `ilike '%termo%'`. Medido em docs/medicao-indices-tenant.md (secao 7): o
filtro de cliente que ja existe hoje gasta 25,8 ms em Seq Scan de 40 mil
clientes so para resolver a subconsulta de ids. Curinga a esquerda nao
alcanca b-tree nenhum; o indice que atende esse padrao e GIN com
`gin_trgm_ops`, da extensao `pg_trgm`.

A extensao e criada na chain public (0003_pg_trgm), nao aqui: ela e por
database, nao por schema de tenant, e `sac-migrate all` roda public antes de
tenants. Esta migration nao repete o CREATE EXTENSION.

O opclass precisa ser qualificado como `public.gin_trgm_ops`: esta migration
roda com search_path no schema do tenant, e sem o prefixo o Postgres nao acha
a opclass ("operator class gin_trgm_ops does not exist for access method
gin").

"""

from alembic import op

revision = "0008_indices_busca"
down_revision = "0007_indices_parciais"
branch_labels = None
depends_on = None

# (nome, tabela, coluna) dos tres indices GIN de trigrama.
_TRGM_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_customers_name_trgm", "customers", "name"),
    ("ix_products_name_trgm", "products", "name"),
    ("ix_tickets_order_code_trgm", "tickets", "order_code"),
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
