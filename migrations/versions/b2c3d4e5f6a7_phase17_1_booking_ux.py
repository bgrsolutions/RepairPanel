"""Phase 17.1 — Booking intake UX improvements.

Adds customer_email and device_description columns to bookings table
to support inline customer creation and booking-stage device description.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-17

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookings", sa.Column("customer_email", sa.String(255), nullable=True))
    op.add_column("bookings", sa.Column("device_description", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("bookings", "device_description")
    op.drop_column("bookings", "customer_email")
