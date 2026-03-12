"""phase4 operations inventory

Revision ID: d4a1c2e9b7f0
Revises: c3f9a7b21e10
Create Date: 2026-03-12 18:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d4a1c2e9b7f0"
down_revision = "c3f9a7b21e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_notes",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("note_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_notes_note_type"), "ticket_notes", ["note_type"], unique=False)
    op.create_index(op.f("ix_ticket_notes_ticket_id"), "ticket_notes", ["ticket_id"], unique=False)

    op.create_table(
        "suppliers",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("account_reference", sa.String(length=120), nullable=True),
        sa.Column("default_lead_time_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_suppliers_name"), "suppliers", ["name"], unique=True)

    op.create_table(
        "parts",
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("barcode", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("supplier_sku", sa.String(length=120), nullable=True),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("serial_tracking", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_parts_barcode"), "parts", ["barcode"], unique=False)
    op.create_index(op.f("ix_parts_sku"), "parts", ["sku"], unique=True)

    op.create_table(
        "stock_locations",
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_locations_branch_id"), "stock_locations", ["branch_id"], unique=False)

    op.create_table(
        "stock_levels",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("on_hand_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserved_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_levels_branch_id"), "stock_levels", ["branch_id"], unique=False)
    op.create_index(op.f("ix_stock_levels_location_id"), "stock_levels", ["location_id"], unique=False)
    op.create_index(op.f("ix_stock_levels_part_id"), "stock_levels", ["part_id"], unique=False)

    op.create_table(
        "stock_movements",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_movements_branch_id"), "stock_movements", ["branch_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_location_id"), "stock_movements", ["location_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_movement_type"), "stock_movements", ["movement_type"], unique=False)
    op.create_index(op.f("ix_stock_movements_part_id"), "stock_movements", ["part_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_ticket_id"), "stock_movements", ["ticket_id"], unique=False)

    op.create_table(
        "stock_reservations",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_reservations_branch_id"), "stock_reservations", ["branch_id"], unique=False)
    op.create_index(op.f("ix_stock_reservations_location_id"), "stock_reservations", ["location_id"], unique=False)
    op.create_index(op.f("ix_stock_reservations_part_id"), "stock_reservations", ["part_id"], unique=False)
    op.create_index(op.f("ix_stock_reservations_status"), "stock_reservations", ["status"], unique=False)
    op.create_index(op.f("ix_stock_reservations_ticket_id"), "stock_reservations", ["ticket_id"], unique=False)

    op.create_table(
        "part_orders",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("shipping_reference", sa.String(length=120), nullable=True),
        sa.Column("eta_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_part_orders_branch_id"), "part_orders", ["branch_id"], unique=False)
    op.create_index(op.f("ix_part_orders_status"), "part_orders", ["status"], unique=False)
    op.create_index(op.f("ix_part_orders_supplier_id"), "part_orders", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_part_orders_ticket_id"), "part_orders", ["ticket_id"], unique=False)

    op.create_table(
        "part_order_lines",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["part_orders.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_part_order_lines_order_id"), "part_order_lines", ["order_id"], unique=False)
    op.create_index(op.f("ix_part_order_lines_part_id"), "part_order_lines", ["part_id"], unique=False)
    op.create_index(op.f("ix_part_order_lines_status"), "part_order_lines", ["status"], unique=False)

    op.create_table(
        "part_order_events",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["part_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_part_order_events_event_type"), "part_order_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_part_order_events_order_id"), "part_order_events", ["order_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_part_order_events_order_id"), table_name="part_order_events")
    op.drop_index(op.f("ix_part_order_events_event_type"), table_name="part_order_events")
    op.drop_table("part_order_events")
    op.drop_index(op.f("ix_part_order_lines_status"), table_name="part_order_lines")
    op.drop_index(op.f("ix_part_order_lines_part_id"), table_name="part_order_lines")
    op.drop_index(op.f("ix_part_order_lines_order_id"), table_name="part_order_lines")
    op.drop_table("part_order_lines")
    op.drop_index(op.f("ix_part_orders_ticket_id"), table_name="part_orders")
    op.drop_index(op.f("ix_part_orders_supplier_id"), table_name="part_orders")
    op.drop_index(op.f("ix_part_orders_status"), table_name="part_orders")
    op.drop_index(op.f("ix_part_orders_branch_id"), table_name="part_orders")
    op.drop_table("part_orders")
    op.drop_index(op.f("ix_stock_reservations_ticket_id"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_status"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_part_id"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_location_id"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_branch_id"), table_name="stock_reservations")
    op.drop_table("stock_reservations")
    op.drop_index(op.f("ix_stock_movements_ticket_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_part_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_movement_type"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_location_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_branch_id"), table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index(op.f("ix_stock_levels_part_id"), table_name="stock_levels")
    op.drop_index(op.f("ix_stock_levels_location_id"), table_name="stock_levels")
    op.drop_index(op.f("ix_stock_levels_branch_id"), table_name="stock_levels")
    op.drop_table("stock_levels")
    op.drop_index(op.f("ix_stock_locations_branch_id"), table_name="stock_locations")
    op.drop_table("stock_locations")
    op.drop_index(op.f("ix_parts_sku"), table_name="parts")
    op.drop_index(op.f("ix_parts_barcode"), table_name="parts")
    op.drop_table("parts")
    op.drop_index(op.f("ix_suppliers_name"), table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index(op.f("ix_ticket_notes_ticket_id"), table_name="ticket_notes")
    op.drop_index(op.f("ix_ticket_notes_note_type"), table_name="ticket_notes")
    op.drop_table("ticket_notes")
