"""Phase 17: Warranty, branded communications, customer aftercare.

Revision ID: a1b2c3d4e5f6
Revises: e9f0a1b2c3d4
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_warranties",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("tickets.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id"), nullable=False, index=True),
        sa.Column("branch_id", sa.Uuid(), sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("warranty_type", sa.String(30), nullable=False, server_default="standard"),
        sa.Column("warranty_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("covers_labour", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("covers_parts", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("repair_summary", sa.Text(), nullable=True),
        sa.Column("parts_used", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active", index=True),
        sa.Column("voided_reason", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("voided_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_claim_at", sa.DateTime(), nullable=True),
        sa.Column("claim_notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("email_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )

    # Add default warranty configuration to companies
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("default_warranty_days", sa.Integer(), nullable=True, server_default="90"))
        batch_op.add_column(sa.Column("default_warranty_terms", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("default_warranty_terms")
        batch_op.drop_column("default_warranty_days")

    op.drop_table("ticket_warranties")
