"""phase3 standalone quotes and repair checklists

Adds standalone quote support columns (customer_id, customer_name,
device_description) to quotes table, makes ticket_id nullable, and
creates repair_checklists + checklist_items tables.

Revision ID: f3a5b7c9d1e2
Revises: e2f4a6b8c0d1
Create Date: 2026-03-15 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a5b7c9d1e2"
down_revision = "e2f4a6b8c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Standalone quote support on quotes table --

    # Make ticket_id nullable (was NOT NULL, now allows standalone quotes)
    op.alter_column(
        "quotes", "ticket_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )

    # Add standalone quote columns
    op.add_column("quotes", sa.Column("customer_id", sa.Uuid(), nullable=True))
    op.add_column("quotes", sa.Column("customer_name", sa.String(length=200), nullable=True))
    op.add_column("quotes", sa.Column("device_description", sa.String(length=500), nullable=True))

    op.create_index(op.f("ix_quotes_customer_id"), "quotes", ["customer_id"], unique=False)
    op.create_foreign_key(
        "fk_quotes_customer_id_customers",
        "quotes", "customers",
        ["customer_id"], ["id"],
    )

    # -- Repair checklists --

    op.create_table(
        "repair_checklists",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_type", sa.String(length=30), nullable=False),
        sa.Column("device_category", sa.String(length=50), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repair_checklists_ticket_id"),
        "repair_checklists", ["ticket_id"], unique=False,
    )
    op.create_index(
        op.f("ix_repair_checklists_checklist_type"),
        "repair_checklists", ["checklist_type"], unique=False,
    )

    op.create_table(
        "checklist_items",
        sa.Column("checklist_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("checked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["checklist_id"], ["repair_checklists.id"]),
        sa.ForeignKeyConstraint(["checked_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checklist_items_checklist_id"),
        "checklist_items", ["checklist_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_checklist_items_checklist_id"), table_name="checklist_items")
    op.drop_table("checklist_items")

    op.drop_index(op.f("ix_repair_checklists_checklist_type"), table_name="repair_checklists")
    op.drop_index(op.f("ix_repair_checklists_ticket_id"), table_name="repair_checklists")
    op.drop_table("repair_checklists")

    op.drop_constraint("fk_quotes_customer_id_customers", "quotes", type_="foreignkey")
    op.drop_index(op.f("ix_quotes_customer_id"), table_name="quotes")
    op.drop_column("quotes", "device_description")
    op.drop_column("quotes", "customer_name")
    op.drop_column("quotes", "customer_id")

    op.alter_column(
        "quotes", "ticket_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
