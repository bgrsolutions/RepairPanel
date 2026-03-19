"""Phase 18.5: intake/device enrichment, structured checklists, archiving.

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f7
Create Date: 2026-03-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c4d5e6f7a8b9"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    # Device: richer fields for Apple/Samsung data
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("imei2", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("eid", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("model_number", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("purchase_country", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("sold_by", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("production_date", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("warranty_status", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("activation_status", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("applecare_eligible", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("technical_support", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("blacklist_status", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("buyer_code", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("last_lookup_at", sa.DateTime(), nullable=True))

    # IntakeSubmission: structured pre-checks + archiving
    with op.batch_alter_table("intake_submissions") as batch_op:
        batch_op.add_column(sa.Column("precheck_data", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("archived_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True))

    # RepairChecklist: link to intake
    with op.batch_alter_table("repair_checklists") as batch_op:
        batch_op.add_column(sa.Column("intake_submission_id", sa.Uuid(), sa.ForeignKey("intake_submissions.id"), nullable=True))
        batch_op.create_index("ix_repair_checklists_intake_submission_id", ["intake_submission_id"])


def downgrade():
    with op.batch_alter_table("repair_checklists") as batch_op:
        batch_op.drop_index("ix_repair_checklists_intake_submission_id")
        batch_op.drop_column("intake_submission_id")

    with op.batch_alter_table("intake_submissions") as batch_op:
        batch_op.drop_column("archived_by_user_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("precheck_data")

    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("last_lookup_at")
        batch_op.drop_column("buyer_code")
        batch_op.drop_column("blacklist_status")
        batch_op.drop_column("technical_support")
        batch_op.drop_column("applecare_eligible")
        batch_op.drop_column("activation_status")
        batch_op.drop_column("warranty_status")
        batch_op.drop_column("production_date")
        batch_op.drop_column("sold_by")
        batch_op.drop_column("purchase_country")
        batch_op.drop_column("model_number")
        batch_op.drop_column("eid")
        batch_op.drop_column("imei2")
