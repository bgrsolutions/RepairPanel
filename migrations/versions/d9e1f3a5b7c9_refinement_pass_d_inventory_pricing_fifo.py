"""refinement pass d inventory pricing fifo

Revision ID: d9e1f3a5b7c9
Revises: c3d5e7f9a1b2
Create Date: 2026-03-13 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d9e1f3a5b7c9"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("parts", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("parts", sa.Column("image_url", sa.String(length=255), nullable=True))
    op.add_column("parts", sa.Column("low_stock_threshold", sa.Integer(), nullable=True))

    op.create_table(
        "part_categories",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_part_categories_name"), "part_categories", ["name"], unique=True)
    op.create_index(op.f("ix_part_categories_code"), "part_categories", ["code"], unique=True)

    op.create_table(
        "part_category_links",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["part_categories.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.PrimaryKeyConstraint("part_id", "category_id"),
    )

    op.create_table(
        "part_suppliers",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_sku", sa.String(length=120), nullable=True),
        sa.Column("supplier_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_part_suppliers_part_id"), "part_suppliers", ["part_id"], unique=False)
    op.create_index(op.f("ix_part_suppliers_supplier_id"), "part_suppliers", ["supplier_id"], unique=False)

    op.create_table(
        "stock_layers",
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("source_movement_id", sa.Uuid(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("quantity_received", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity_remaining", sa.Numeric(12, 2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["stock_locations.id"]),
        sa.ForeignKeyConstraint(["part_id"], ["parts.id"]),
        sa.ForeignKeyConstraint(["source_movement_id"], ["stock_movements.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_layers_part_id"), "stock_layers", ["part_id"], unique=False)
    op.create_index(op.f("ix_stock_layers_branch_id"), "stock_layers", ["branch_id"], unique=False)
    op.create_index(op.f("ix_stock_layers_location_id"), "stock_layers", ["location_id"], unique=False)
    op.create_index(op.f("ix_stock_layers_source_movement_id"), "stock_layers", ["source_movement_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_stock_layers_source_movement_id"), table_name="stock_layers")
    op.drop_index(op.f("ix_stock_layers_location_id"), table_name="stock_layers")
    op.drop_index(op.f("ix_stock_layers_branch_id"), table_name="stock_layers")
    op.drop_index(op.f("ix_stock_layers_part_id"), table_name="stock_layers")
    op.drop_table("stock_layers")

    op.drop_index(op.f("ix_part_suppliers_supplier_id"), table_name="part_suppliers")
    op.drop_index(op.f("ix_part_suppliers_part_id"), table_name="part_suppliers")
    op.drop_table("part_suppliers")

    op.drop_table("part_category_links")
    op.drop_index(op.f("ix_part_categories_code"), table_name="part_categories")
    op.drop_index(op.f("ix_part_categories_name"), table_name="part_categories")
    op.drop_table("part_categories")

    op.drop_column("parts", "low_stock_threshold")
    op.drop_column("parts", "image_url")
    op.drop_column("parts", "description")
