"""phase4 add sale_price to part_order_lines

Adds sale_price column to part_order_lines so purchase orders can track
the intended sale price per line. On stock receive, the sale price is
applied to the part record.

Revision ID: a4b6c8d0e2f4
Revises: f3a5b7c9d1e2
Create Date: 2026-03-15 22:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4b6c8d0e2f4"
down_revision = "f3a5b7c9d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "part_order_lines",
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("part_order_lines", "sale_price")
