"""Phase 6: Business identity, service catalogue, booking foundation

Adds:
- companies table (legal/business entity)
- Extends branches with store/location fields (company_id, address, phone, etc.)
- repair_services table (service catalogue)
- bookings table (calendar/scheduling foundation)

Revision ID: b5c7d9e1f3a5
Revises: a4b6c8d0e2f4
Create Date: 2026-03-16 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b5c7d9e1f3a5"
down_revision = "a4b6c8d0e2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Companies table ---
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("trading_name", sa.String(200), nullable=True),
        sa.Column("cif_nif", sa.String(30), nullable=True),
        sa.Column("tax_mode", sa.String(20), nullable=False, server_default="IGIC"),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("logo_path", sa.String(500), nullable=True),
        sa.Column("default_quote_terms", sa.Text(), nullable=True),
        sa.Column("default_repair_terms", sa.Text(), nullable=True),
        sa.Column("document_footer", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Extend branches with store/location fields ---
    op.add_column("branches", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.add_column("branches", sa.Column("address_line_1", sa.String(255), nullable=True))
    op.add_column("branches", sa.Column("address_line_2", sa.String(255), nullable=True))
    op.add_column("branches", sa.Column("postcode", sa.String(20), nullable=True))
    op.add_column("branches", sa.Column("city", sa.String(120), nullable=True))
    op.add_column("branches", sa.Column("island_or_region", sa.String(120), nullable=True))
    op.add_column("branches", sa.Column("country", sa.String(80), nullable=True, server_default="Spain"))
    op.add_column("branches", sa.Column("phone", sa.String(50), nullable=True))
    op.add_column("branches", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("branches", sa.Column("opening_hours", sa.Text(), nullable=True))
    op.add_column("branches", sa.Column("ticket_prefix", sa.String(10), nullable=True))
    op.add_column("branches", sa.Column("quote_prefix", sa.String(10), nullable=True))
    op.create_index("ix_branches_company_id", "branches", ["company_id"])
    op.create_foreign_key("fk_branches_company_id", "branches", "companies", ["company_id"], ["id"])

    # --- Repair services table ---
    op.create_table(
        "repair_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("device_category", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_part_id", sa.Uuid(), nullable=True),
        sa.Column("labour_minutes", sa.Integer(), nullable=True),
        sa.Column("suggested_sale_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["default_part_id"], ["parts.id"]),
    )
    op.create_index("ix_repair_services_device_category", "repair_services", ["device_category"])
    op.create_index("ix_repair_services_default_part_id", "repair_services", ["default_part_id"])

    # --- Bookings table ---
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("repair_service_id", sa.Uuid(), nullable=True),
        sa.Column("linked_ticket_id", sa.Uuid(), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["location_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["repair_service_id"], ["repair_services.id"]),
        sa.ForeignKeyConstraint(["linked_ticket_id"], ["tickets.id"]),
    )
    op.create_index("ix_bookings_location_id", "bookings", ["location_id"])
    op.create_index("ix_bookings_customer_id", "bookings", ["customer_id"])
    op.create_index("ix_bookings_repair_service_id", "bookings", ["repair_service_id"])
    op.create_index("ix_bookings_linked_ticket_id", "bookings", ["linked_ticket_id"])
    op.create_index("ix_bookings_start_time", "bookings", ["start_time"])
    op.create_index("ix_bookings_status", "bookings", ["status"])


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("repair_services")
    op.drop_constraint("fk_branches_company_id", "branches", type_="foreignkey")
    op.drop_index("ix_branches_company_id", table_name="branches")
    op.drop_column("branches", "quote_prefix")
    op.drop_column("branches", "ticket_prefix")
    op.drop_column("branches", "opening_hours")
    op.drop_column("branches", "email")
    op.drop_column("branches", "phone")
    op.drop_column("branches", "country")
    op.drop_column("branches", "island_or_region")
    op.drop_column("branches", "city")
    op.drop_column("branches", "postcode")
    op.drop_column("branches", "address_line_2")
    op.drop_column("branches", "address_line_1")
    op.drop_column("branches", "company_id")
    op.drop_table("companies")
