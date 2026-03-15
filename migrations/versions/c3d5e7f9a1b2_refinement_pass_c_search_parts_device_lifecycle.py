"""refinement pass c search parts device lifecycle

Revision ID: c3d5e7f9a1b2
Revises: a2b4c6d8e0f2
Create Date: 2026-03-13 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c3d5e7f9a1b2"
down_revision = "a2b4c6d8e0f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("parts", sa.Column("default_supplier_id", sa.Uuid(), nullable=True))
    op.add_column("parts", sa.Column("lead_time_days", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_parts_default_supplier_id"), "parts", ["default_supplier_id"], unique=False)
    op.create_foreign_key("fk_parts_default_supplier_id_suppliers", "parts", "suppliers", ["default_supplier_id"], ["id"])

    op.alter_column("devices", "customer_id", existing_type=sa.Uuid(), nullable=True)


def downgrade():
    op.alter_column("devices", "customer_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_constraint("fk_parts_default_supplier_id_suppliers", "parts", type_="foreignkey")
    op.drop_index(op.f("ix_parts_default_supplier_id"), table_name="parts")
    op.drop_column("parts", "lead_time_days")
    op.drop_column("parts", "default_supplier_id")
