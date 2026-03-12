"""phase3 diagnostics and quotes

Revision ID: c3f9a7b21e10
Revises: 8a2b9d3f2c1e
Create Date: 2026-03-12 16:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3f9a7b21e10"
down_revision = "8a2b9d3f2c1e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diagnostics",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("entered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("customer_reported_fault", sa.Text(), nullable=False),
        sa.Column("technician_diagnosis", sa.Text(), nullable=False),
        sa.Column("recommended_repair", sa.Text(), nullable=True),
        sa.Column("estimated_labour", sa.Numeric(10, 2), nullable=True),
        sa.Column("repair_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["entered_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_diagnostics_ticket_id"), "diagnostics", ["ticket_id"], unique=False)

    op.create_table(
        "quotes",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("notes_snapshot", sa.Text(), nullable=True),
        sa.Column("terms_snapshot", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quotes_status"), "quotes", ["status"], unique=False)
    op.create_index(op.f("ix_quotes_ticket_id"), "quotes", ["ticket_id"], unique=False)

    op.create_table(
        "quote_options",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_options_quote_id"), "quote_options", ["quote_id"], unique=False)

    op.create_table(
        "quote_lines",
        sa.Column("option_id", sa.Uuid(), nullable=False),
        sa.Column("line_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["option_id"], ["quote_options.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_lines_option_id"), "quote_lines", ["option_id"], unique=False)

    op.create_table(
        "quote_approvals",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("actor_contact", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=True),
        sa.Column("declined_reason", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_quote_approvals_quote_id"), "quote_approvals", ["quote_id"], unique=False)
    op.create_index(op.f("ix_quote_approvals_token"), "quote_approvals", ["token"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_quote_approvals_token"), table_name="quote_approvals")
    op.drop_index(op.f("ix_quote_approvals_quote_id"), table_name="quote_approvals")
    op.drop_table("quote_approvals")

    op.drop_index(op.f("ix_quote_lines_option_id"), table_name="quote_lines")
    op.drop_table("quote_lines")

    op.drop_index(op.f("ix_quote_options_quote_id"), table_name="quote_options")
    op.drop_table("quote_options")

    op.drop_index(op.f("ix_quotes_ticket_id"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_status"), table_name="quotes")
    op.drop_table("quotes")

    op.drop_index(op.f("ix_diagnostics_ticket_id"), table_name="diagnostics")
    op.drop_table("diagnostics")
