"""refinement pass A ticket SLA/status foundations

Revision ID: f1a2b3c4d5e6
Revises: e7b9a4d2c6f1
Create Date: 2026-03-12 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e7b9a4d2c6f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("sla_target_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_tickets_sla_target_at"), "tickets", ["sla_target_at"], unique=False)

    op.execute("""
        UPDATE tickets
        SET internal_status = CASE
            WHEN lower(internal_status) = 'new' THEN 'unassigned'
            WHEN lower(internal_status) = 'awaiting diagnosis' THEN 'awaiting_diagnostics'
            WHEN lower(internal_status) = 'awaiting quote approval' THEN 'awaiting_quote_approval'
            WHEN lower(internal_status) = 'awaiting parts' THEN 'awaiting_parts'
            WHEN lower(internal_status) = 'in repair' THEN 'in_repair'
            WHEN lower(internal_status) IN ('testing / qa', 'testing', 'qa') THEN 'testing_qa'
            WHEN lower(internal_status) = 'ready for collection' THEN 'ready_for_collection'
            WHEN lower(internal_status) = 'collected' THEN 'completed'
            ELSE internal_status
        END
    """)

    op.execute("""
        UPDATE tickets
        SET sla_target_at = created_at + interval '5 day'
        WHERE sla_target_at IS NULL
    """)


def downgrade():
    op.execute("""
        UPDATE tickets
        SET internal_status = CASE
            WHEN internal_status = 'unassigned' THEN 'New'
            WHEN internal_status = 'awaiting_diagnostics' THEN 'Awaiting Diagnosis'
            WHEN internal_status = 'awaiting_quote_approval' THEN 'Awaiting Quote Approval'
            WHEN internal_status = 'awaiting_parts' THEN 'Awaiting Parts'
            WHEN internal_status = 'in_repair' THEN 'In Repair'
            WHEN internal_status = 'testing_qa' THEN 'Testing / QA'
            WHEN internal_status = 'ready_for_collection' THEN 'Ready for Collection'
            WHEN internal_status = 'completed' THEN 'Collected'
            ELSE internal_status
        END
    """)
    op.drop_index(op.f("ix_tickets_sla_target_at"), table_name="tickets")
    op.drop_column("tickets", "sla_target_at")
