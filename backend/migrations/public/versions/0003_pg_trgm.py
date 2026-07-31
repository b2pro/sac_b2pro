"""Habilita pg_trgm para a busca livre de tickets

Revision ID: 0003_pg_trgm
Revises: 0002_preview_jobs
Create Date: 2026-07-31

A busca livre da Task 1 (Fase 3B) filtra cliente, produto e codigo do pedido
com `ilike '%termo%'`. Curinga a esquerda nao alcanca b-tree nenhum, em
nenhuma collation: o filtro de cliente que ja existe hoje gasta 25,8 ms em
Seq Scan de 40 mil clientes so para resolver a subconsulta de ids (medido em
docs/medicao-indices-tenant.md, secao 7). O caminho e indice GIN com
`gin_trgm_ops`, que exige a extensao `pg_trgm`.

A extensao e por DATABASE, nao por schema de tenant, entao entra na chain
`public`. Os indices GIN em si (0008_indices_busca, chain tenant) qualificam
o opclass como `public.gin_trgm_ops` porque a migration de tenant roda com
search_path no proprio schema.

O downgrade derruba a extensao inteira. Rodar este downgrade com algum tenant
ainda na 0008 quebra os indices GIN dele: a ordem correta e reverter os
tenants primeiro, so depois a public.

"""

from alembic import op

revision = "0003_pg_trgm"
down_revision = "0002_preview_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
