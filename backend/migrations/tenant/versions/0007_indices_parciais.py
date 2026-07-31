"""deleted_at vira predicado parcial em vez de coluna lider dos indices

Revision ID: 0007_indices_parciais
Revises: 0006_ordem_itens_ticket
Create Date: 2026-07-31

Medido em um schema descartavel com 100 mil tickets, 156 mil itens e 135 mil
anexos (1% de exclusao logica, distribuicao de status enviesada), com ANALYZE:

- Toda query de ticket filtra deleted_at IS NULL, mas 99% das linhas satisfazem
  o predicado. Como coluna LIDER de um b-tree isso custa 8 bytes por entrada e
  nao entrega seletividade; como PREDICADO PARCIAL custa zero e ainda dispensa
  a recheck de deleted_at no heap. Exemplo: a contagem por atendente saiu de
  Bitmap Heap Scan (9,6 ms, ~2000 buffers) para Index Only Scan (0,97 ms, 11
  buffers) so por trocar a forma do indice.
- ix_tickets_deleted_at_status ERA usado (Index Only Scan no GROUP BY status do
  dashboard e nos counts do relatorio) — a medicao anterior, feita em 738
  linhas, concluiu o contrario porque naquele volume Seq Scan vence tudo. Ele
  sai porque o parcial ix_tickets_status faz o mesmo trabalho e ainda substitui
  o single-column homonimo da 0003, nao porque seja inutil.
- ix_tickets_deleted_at_closed_at sai sem substituto: nenhum plano o escolheu —
  o tempo medio de resolucao entra por status, e closed_at IS NOT NULL nao
  filtra nada dentro de status = 'finalizado'.
- brand_id continua indexado, na forma parcial. A marca so tem duas categorias,
  entao nenhum plano a usa para restringir linhas; ela serve como Index Only
  Scan da contagem do dashboard por marca (8,0 ms contra 42,9 ms de Seq Scan
  quando o indice nao existe) e como o menor indice que cobre deleted_at.
- ix_tickets_opened_at troca (deleted_at, opened_at) por (opened_at) parcial:
  3.104 KB -> 2.184 KB e, principalmente, habilita Index Scan + Incremental
  Sort no ORDER BY opened_at DESC, id da tabela do relatorio (143,6 ms -> 0,43
  ms) e do export CSV (178,4 ms com merge externo de 24 MB -> 29,4 ms).
- Em anexos o parcial NAO se aplica: list_pending_before (varredura de anexos
  pendentes) filtra status/created_at sem deleted_at, entao um indice parcial
  ficaria inalcancavel para ela. O composto liderado por deleted_at cede lugar
  a (status, created_at), que serve a galeria pela ordenacao (107,5 ms -> 0,58
  ms) E o varredor pelo prefixo status, dispensando
  ix_ticket_attachments_status.

Massa, planos completos e tamanhos em docs/medicao-indices-tenant.md.

"""

import sqlalchemy as sa
from alembic import op

revision = "0007_indices_parciais"
down_revision = "0006_ordem_itens_ticket"
branch_labels = None
depends_on = None

_ALIVE = sa.text("deleted_at IS NULL")

# (nome, coluna) dos indices de tickets na forma nova, todos parciais.
_TICKET_PARTIAL: tuple[tuple[str, str], ...] = (
    ("ix_tickets_status", "status"),
    ("ix_tickets_brand_id", "brand_id"),
    ("ix_tickets_opened_at", "opened_at"),
    ("ix_tickets_last_activity_at", "last_activity_at"),
    ("ix_tickets_due_at", "due_at"),
    ("ix_tickets_customer_id", "customer_id"),
    ("ix_tickets_attendant_user_id", "attendant_user_id"),
)

# Compostos da 0005 (saem de vez) e single-column da 0003 (voltam parciais).
_TICKET_OLD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_tickets_deleted_at_status", ("deleted_at", "status")),
    ("ix_tickets_deleted_at_brand_id", ("deleted_at", "brand_id")),
    ("ix_tickets_deleted_at_opened_at", ("deleted_at", "opened_at")),
    ("ix_tickets_deleted_at_closed_at", ("deleted_at", "closed_at")),
    ("ix_tickets_status", ("status",)),
    ("ix_tickets_last_activity_at", ("last_activity_at",)),
    ("ix_tickets_due_at", ("due_at",)),
    ("ix_tickets_customer_id", ("customer_id",)),
    ("ix_tickets_attendant_user_id", ("attendant_user_id",)),
)

_ATTACHMENT_OLD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_ticket_attachments_deleted_at_status_created_at", ("deleted_at", "status", "created_at")),
    ("ix_ticket_attachments_status", ("status",)),
)


def upgrade() -> None:
    for name, _ in _TICKET_OLD:
        op.drop_index(name, table_name="tickets", schema="tenant")
    for name, column in _TICKET_PARTIAL:
        op.create_index(name, "tickets", [column], schema="tenant", postgresql_where=_ALIVE)
    for name, _ in _ATTACHMENT_OLD:
        op.drop_index(name, table_name="ticket_attachments", schema="tenant")
    op.create_index(
        "ix_ticket_attachments_status_created_at",
        "ticket_attachments",
        ["status", "created_at"],
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticket_attachments_status_created_at",
        table_name="ticket_attachments",
        schema="tenant",
    )
    for name, columns in _ATTACHMENT_OLD:
        op.create_index(name, "ticket_attachments", list(columns), schema="tenant")
    for name, _ in _TICKET_PARTIAL:
        op.drop_index(name, table_name="tickets", schema="tenant")
    for name, columns in _TICKET_OLD:
        op.create_index(name, "tickets", list(columns), schema="tenant")
