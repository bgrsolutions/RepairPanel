"""Phase 11: add ticket_id to portal_tokens for public repair status access.

Revision ID: d8e0f2a4b6c8
Revises: c7d9e1f3a5b7
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = "d8e0f2a4b6c8"
down_revision = "c7d9e1f3a5b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("portal_tokens", sa.Column("ticket_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_portal_tokens_ticket_id"), "portal_tokens", ["ticket_id"], unique=False)
    op.create_foreign_key("fk_portal_tokens_ticket_id", "portal_tokens", "tickets", ["ticket_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_portal_tokens_ticket_id", "portal_tokens", type_="foreignkey")
    op.drop_index(op.f("ix_portal_tokens_ticket_id"), table_name="portal_tokens")
    op.drop_column("portal_tokens", "ticket_id")
