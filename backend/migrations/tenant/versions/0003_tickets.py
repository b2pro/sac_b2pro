"""tickets do tenant

Revision ID: 0003_tickets
Revises: 0002_cadastros
Create Date: 2026-07-28

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSequence, DropSequence

revision = "0003_tickets"
down_revision = "0002_cadastros"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(CreateSequence(sa.Sequence("ticket_number_seq", schema="tenant")))
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # sem default de coluna no DDL de proposito: o valor vem do Sequence
        # ticket_number_seq aplicado pelo ORM (default fica em models_tenant.py).
        sa.Column("number", sa.BigInteger(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("attendant_user_id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("purchase_channel_id", sa.Uuid(), nullable=True),
        sa.Column("order_code", sa.String(60), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("final_notes", sa.Text(), nullable=True),
        sa.Column("solution_type_id", sa.Uuid(), nullable=True),
        sa.Column("warranty_order_code", sa.String(60), nullable=True),
        sa.Column("warranty_tracking_code", sa.String(60), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("number", name="uq_tickets_number"),
        sa.ForeignKeyConstraint(["brand_id"], ["tenant.brands.id"], name="fk_tickets_brand_id"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["tenant.customers.id"], name="fk_tickets_customer_id"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_channel_id"],
            ["tenant.purchase_channels.id"],
            name="fk_tickets_purchase_channel_id",
        ),
        sa.ForeignKeyConstraint(
            ["solution_type_id"],
            ["tenant.solution_types.id"],
            name="fk_tickets_solution_type_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("defect_type_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity >= 1", name="ck_ticket_items_quantity"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_items_ticket_id"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["tenant.products.id"], name="fk_ticket_items_product_id"
        ),
        sa.ForeignKeyConstraint(
            ["defect_type_id"],
            ["tenant.defect_types.id"],
            name="fk_ticket_items_defect_type_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_comments_ticket_id"
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["tenant.ticket_comments.id"],
            name="fk_ticket_comments_reply_to_id",
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_timeline_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_timeline_events_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "ticket_reads",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticket_id", "user_id", name="pk_ticket_reads"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_ticket_reads_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "reverse_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tenant.tickets.id"], name="fk_reverse_codes_ticket_id"
        ),
        schema="tenant",
    )
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("warn_hours", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("priority", name="uq_sla_policies_priority"),
        schema="tenant",
    )
    op.create_index("ix_tickets_status", "tickets", ["status"], schema="tenant")
    op.create_index("ix_tickets_last_activity_at", "tickets", ["last_activity_at"], schema="tenant")
    op.create_index("ix_tickets_due_at", "tickets", ["due_at"], schema="tenant")
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"], schema="tenant")
    op.create_index(
        "ix_tickets_attendant_user_id", "tickets", ["attendant_user_id"], schema="tenant"
    )
    op.create_index("ix_ticket_items_ticket_id", "ticket_items", ["ticket_id"], schema="tenant")
    op.create_index(
        "ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"], schema="tenant"
    )
    op.create_index(
        "ix_ticket_timeline_events_ticket_id",
        "ticket_timeline_events",
        ["ticket_id"],
        schema="tenant",
    )
    op.create_index("ix_reverse_codes_ticket_id", "reverse_codes", ["ticket_id"], schema="tenant")


def downgrade() -> None:
    for table in (
        "sla_policies",
        "reverse_codes",
        "ticket_reads",
        "ticket_timeline_events",
        "ticket_comments",
        "ticket_items",
        "tickets",
    ):
        op.drop_table(table, schema="tenant")
    op.execute(DropSequence(sa.Sequence("ticket_number_seq", schema="tenant")))
