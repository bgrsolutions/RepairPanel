"""Phase 7: customer business identity and printing foundations

Revision ID: c7d9e1f3a5b7
Revises: b5c7d9e1f3a5
Create Date: 2026-03-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'c7d9e1f3a5b7'
down_revision = 'b5c7d9e1f3a5'
branch_labels = None
depends_on = None


def upgrade():
    # Extend customers table with business/company fields
    op.add_column('customers', sa.Column('customer_type', sa.String(20), nullable=False, server_default='individual'))
    op.add_column('customers', sa.Column('company_name', sa.String(200), nullable=True))
    op.add_column('customers', sa.Column('cif_vat', sa.String(30), nullable=True))
    op.add_column('customers', sa.Column('billing_address_line_1', sa.String(255), nullable=True))
    op.add_column('customers', sa.Column('billing_address_line_2', sa.String(255), nullable=True))
    op.add_column('customers', sa.Column('billing_postcode', sa.String(20), nullable=True))
    op.add_column('customers', sa.Column('billing_city', sa.String(120), nullable=True))
    op.add_column('customers', sa.Column('billing_region', sa.String(120), nullable=True))
    op.add_column('customers', sa.Column('billing_country', sa.String(80), nullable=True))
    op.add_column('customers', sa.Column('billing_email', sa.String(255), nullable=True))
    op.add_column('customers', sa.Column('billing_phone', sa.String(50), nullable=True))

    op.create_index('ix_customers_customer_type', 'customers', ['customer_type'])


def downgrade():
    op.drop_index('ix_customers_customer_type', table_name='customers')

    op.drop_column('customers', 'billing_phone')
    op.drop_column('customers', 'billing_email')
    op.drop_column('customers', 'billing_country')
    op.drop_column('customers', 'billing_region')
    op.drop_column('customers', 'billing_city')
    op.drop_column('customers', 'billing_postcode')
    op.drop_column('customers', 'billing_address_line_2')
    op.drop_column('customers', 'billing_address_line_1')
    op.drop_column('customers', 'cif_vat')
    op.drop_column('customers', 'company_name')
    op.drop_column('customers', 'customer_type')
