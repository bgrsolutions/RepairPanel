"""phase2 intake foundations

Revision ID: 8a2b9d3f2c1e
Revises: 5c614de9449c
Create Date: 2026-03-12 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8a2b9d3f2c1e"
down_revision = "5c614de9449c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "intake_submissions",
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("converted_ticket_id", sa.Uuid(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("customer_phone", sa.String(length=50), nullable=True),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("device_brand", sa.String(length=80), nullable=False),
        sa.Column("device_model", sa.String(length=120), nullable=False),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("imei", sa.String(length=60), nullable=True),
        sa.Column("reported_fault", sa.Text(), nullable=False),
        sa.Column("accessories", sa.Text(), nullable=True),
        sa.Column("intake_notes", sa.Text(), nullable=True),
        sa.Column("preferred_language", sa.String(length=5), nullable=False),
        sa.Column("preferred_contact_method", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["converted_ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index(op.f("ix_intake_submissions_branch_id"), "intake_submissions", ["branch_id"], unique=False)
    op.create_index(op.f("ix_intake_submissions_converted_ticket_id"), "intake_submissions", ["converted_ticket_id"], unique=False)
    op.create_index(op.f("ix_intake_submissions_customer_id"), "intake_submissions", ["customer_id"], unique=False)
    op.create_index(op.f("ix_intake_submissions_device_id"), "intake_submissions", ["device_id"], unique=False)
    op.create_index(op.f("ix_intake_submissions_reference"), "intake_submissions", ["reference"], unique=True)
    op.create_index(op.f("ix_intake_submissions_status"), "intake_submissions", ["status"], unique=False)

    op.create_table(
        "intake_disclaimer_acceptances",
        sa.Column("intake_submission_id", sa.Uuid(), nullable=False),
        sa.Column("disclaimer_key", sa.String(length=80), nullable=False),
        sa.Column("disclaimer_text", sa.Text(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["intake_submission_id"], ["intake_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intake_disclaimer_acceptances_intake_submission_id"), "intake_disclaimer_acceptances", ["intake_submission_id"], unique=False)

    op.create_table(
        "intake_signatures",
        sa.Column("intake_submission_id", sa.Uuid(), nullable=False),
        sa.Column("signer_name", sa.String(length=120), nullable=True),
        sa.Column("signature_data", sa.Text(), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["intake_submission_id"], ["intake_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intake_signatures_intake_submission_id"), "intake_signatures", ["intake_submission_id"], unique=False)

    op.create_table(
        "attachments",
        sa.Column("intake_submission_id", sa.Uuid(), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("is_public_upload", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["intake_submission_id"], ["intake_submissions.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attachments_intake_submission_id"), "attachments", ["intake_submission_id"], unique=False)
    op.create_index(op.f("ix_attachments_ticket_id"), "attachments", ["ticket_id"], unique=False)

    op.create_table(
        "portal_tokens",
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=False),
        sa.Column("intake_submission_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["intake_submission_id"], ["intake_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_portal_tokens_intake_submission_id"), "portal_tokens", ["intake_submission_id"], unique=False)
    op.create_index(op.f("ix_portal_tokens_token"), "portal_tokens", ["token"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_portal_tokens_token"), table_name="portal_tokens")
    op.drop_index(op.f("ix_portal_tokens_intake_submission_id"), table_name="portal_tokens")
    op.drop_table("portal_tokens")

    op.drop_index(op.f("ix_attachments_ticket_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_intake_submission_id"), table_name="attachments")
    op.drop_table("attachments")

    op.drop_index(op.f("ix_intake_signatures_intake_submission_id"), table_name="intake_signatures")
    op.drop_table("intake_signatures")

    op.drop_index(op.f("ix_intake_disclaimer_acceptances_intake_submission_id"), table_name="intake_disclaimer_acceptances")
    op.drop_table("intake_disclaimer_acceptances")

    op.drop_index(op.f("ix_intake_submissions_status"), table_name="intake_submissions")
    op.drop_index(op.f("ix_intake_submissions_reference"), table_name="intake_submissions")
    op.drop_index(op.f("ix_intake_submissions_device_id"), table_name="intake_submissions")
    op.drop_index(op.f("ix_intake_submissions_customer_id"), table_name="intake_submissions")
    op.drop_index(op.f("ix_intake_submissions_converted_ticket_id"), table_name="intake_submissions")
    op.drop_index(op.f("ix_intake_submissions_branch_id"), table_name="intake_submissions")
    op.drop_table("intake_submissions")
