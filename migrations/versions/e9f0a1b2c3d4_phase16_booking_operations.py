"""Phase 16: Booking operations, intake queue, service scheduling foundations.

Revision ID: e9f0a1b2c3d4
Revises: d8e0f2a4b6c8
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = "e9f0a1b2c3d4"
down_revision = "d8e0f2a4b6c8"
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to bookings table
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.add_column(sa.Column("device_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("staff_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("customer_name", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("converted_ticket_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_bookings_device_id", ["device_id"])
        batch_op.create_index("ix_bookings_converted_ticket_id", ["converted_ticket_id"])
        batch_op.create_foreign_key(
            "fk_bookings_device_id", "devices", ["device_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_bookings_converted_ticket_id", "tickets", ["converted_ticket_id"], ["id"]
        )

    # Migrate existing statuses: scheduled -> new
    op.execute("UPDATE bookings SET status = 'new' WHERE status = 'scheduled'")
    # Migrate in_progress -> arrived
    op.execute("UPDATE bookings SET status = 'arrived' WHERE status = 'in_progress'")
    # Migrate completed -> converted
    op.execute("UPDATE bookings SET status = 'converted' WHERE status = 'completed'")

    # Default new bookings status to 'new'
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.alter_column("status", server_default="new")


def downgrade():
    # Revert status migrations
    op.execute("UPDATE bookings SET status = 'scheduled' WHERE status = 'new'")
    op.execute("UPDATE bookings SET status = 'in_progress' WHERE status = 'arrived'")
    op.execute("UPDATE bookings SET status = 'completed' WHERE status = 'converted'")

    with op.batch_alter_table("bookings") as batch_op:
        batch_op.alter_column("status", server_default="scheduled")
        batch_op.drop_constraint("fk_bookings_converted_ticket_id", type_="foreignkey")
        batch_op.drop_constraint("fk_bookings_device_id", type_="foreignkey")
        batch_op.drop_index("ix_bookings_converted_ticket_id")
        batch_op.drop_index("ix_bookings_device_id")
        batch_op.drop_column("converted_ticket_id")
        batch_op.drop_column("customer_name")
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("staff_notes")
        batch_op.drop_column("device_id")
