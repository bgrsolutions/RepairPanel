"""refinement pass f portal settings and quote payments

Revision ID: e2f4a6b8c0d1
Revises: d9e1f3a5b7c9
Create Date: 2026-03-13 16:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f4a6b8c0d1'
down_revision = 'd9e1f3a5b7c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=120), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('branch_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_settings_branch_id'), 'app_settings', ['branch_id'], unique=False)
    op.create_index(op.f('ix_app_settings_key'), 'app_settings', ['key'], unique=False)

    op.add_column('quote_approvals', sa.Column('payment_choice', sa.String(length=30), nullable=True))
    op.add_column('quote_approvals', sa.Column('payment_status', sa.String(length=30), nullable=True))
    op.add_column('quote_approvals', sa.Column('stripe_session_id', sa.String(length=128), nullable=True))
    op.add_column('quote_approvals', sa.Column('stripe_checkout_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('quote_approvals', 'stripe_checkout_url')
    op.drop_column('quote_approvals', 'stripe_session_id')
    op.drop_column('quote_approvals', 'payment_status')
    op.drop_column('quote_approvals', 'payment_choice')

    op.drop_index(op.f('ix_app_settings_key'), table_name='app_settings')
    op.drop_index(op.f('ix_app_settings_branch_id'), table_name='app_settings')
    op.drop_table('app_settings')
