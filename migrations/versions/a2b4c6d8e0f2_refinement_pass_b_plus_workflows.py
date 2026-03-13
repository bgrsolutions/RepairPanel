"""refinement pass b plus workflows

Revision ID: a2b4c6d8e0f2
Revises: f1a2b3c4d5e6
Create Date: 2026-03-12 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a2b4c6d8e0f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("quoted_completion_at", sa.DateTime(), nullable=True))
    op.add_column("tickets", sa.Column("issue_summary", sa.Text(), nullable=True))
    op.create_index(op.f("ix_tickets_quoted_completion_at"), "tickets", ["quoted_completion_at"], unique=False)

    op.add_column("quote_lines", sa.Column("part_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_quote_lines_part_id"), "quote_lines", ["part_id"], unique=False)
    op.create_foreign_key(None, "quote_lines", "parts", ["part_id"], ["id"])

    op.alter_column("part_orders", "ticket_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("part_orders", sa.Column("order_type", sa.String(length=20), nullable=False, server_default="repair"))
    op.add_column("part_orders", sa.Column("supplier_reference", sa.String(length=120), nullable=True))
    op.add_column("part_orders", sa.Column("tracking_number", sa.String(length=120), nullable=True))
    op.add_column("part_orders", sa.Column("estimated_arrival_at", sa.DateTime(), nullable=True))
    op.add_column("part_orders", sa.Column("ordered_at", sa.DateTime(), nullable=True))
    op.add_column("part_orders", sa.Column("notes", sa.Text(), nullable=True))
    op.create_index(op.f("ix_part_orders_order_type"), "part_orders", ["order_type"], unique=False)

    op.add_column("part_order_lines", sa.Column("description_override", sa.String(length=255), nullable=True))
    op.add_column("part_order_lines", sa.Column("supplier_sku", sa.String(length=120), nullable=True))
    op.add_column("part_order_lines", sa.Column("received_quantity", sa.Numeric(12, 2), nullable=False, server_default="0"))

    op.execute("""
        UPDATE part_orders
        SET order_type = CASE WHEN ticket_id IS NULL THEN 'stock' ELSE 'repair' END
    """)

    op.execute("""
        UPDATE part_orders
        SET status = CASE
            WHEN status = 'partially_arrived' THEN 'partially_received'
            WHEN status = 'arrived' THEN 'received'
            ELSE status
        END
    """)


def downgrade():
    op.execute("""
        UPDATE part_orders
        SET status = CASE
            WHEN status = 'partially_received' THEN 'partially_arrived'
            WHEN status = 'received' THEN 'arrived'
            ELSE status
        END
    """)

    op.drop_column("part_order_lines", "received_quantity")
    op.drop_column("part_order_lines", "supplier_sku")
    op.drop_column("part_order_lines", "description_override")

    op.drop_index(op.f("ix_part_orders_order_type"), table_name="part_orders")
    op.drop_column("part_orders", "notes")
    op.drop_column("part_orders", "ordered_at")
    op.drop_column("part_orders", "estimated_arrival_at")
    op.drop_column("part_orders", "tracking_number")
    op.drop_column("part_orders", "supplier_reference")
    op.drop_column("part_orders", "order_type")
    op.alter_column("part_orders", "ticket_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_constraint(None, "quote_lines", type_="foreignkey")
    op.drop_index(op.f("ix_quote_lines_part_id"), table_name="quote_lines")
    op.drop_column("quote_lines", "part_id")

    op.drop_index(op.f("ix_tickets_quoted_completion_at"), table_name="tickets")
    op.drop_column("tickets", "issue_summary")
    op.drop_column("tickets", "quoted_completion_at")
