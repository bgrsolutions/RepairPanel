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
    # Detect database dialect to use correct type for UUID columns.
    # tickets.id is UUID (via UUIDMixin), so the FK column must match.
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else "sqlite"

    if dialect == "postgresql":
        col_type = sa.dialects.postgresql.UUID(as_uuid=True)
    else:
        # SQLite / others: store UUID as 36-char string
        col_type = sa.String(36)

    # Guard against partial-failure re-runs: only add column if missing
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("portal_tokens")}

    if "ticket_id" not in existing_cols:
        op.add_column("portal_tokens", sa.Column("ticket_id", col_type, nullable=True))

    existing_indexes = {idx["name"] for idx in insp.get_indexes("portal_tokens") if idx.get("name")}
    if "ix_portal_tokens_ticket_id" not in existing_indexes:
        op.create_index(op.f("ix_portal_tokens_ticket_id"), "portal_tokens", ["ticket_id"], unique=False)

    existing_fks = {fk["name"] for fk in insp.get_foreign_keys("portal_tokens") if fk.get("name")}
    if "fk_portal_tokens_ticket_id" not in existing_fks:
        op.create_foreign_key("fk_portal_tokens_ticket_id", "portal_tokens", "tickets", ["ticket_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_portal_tokens_ticket_id", "portal_tokens", type_="foreignkey")
    op.drop_index(op.f("ix_portal_tokens_ticket_id"), table_name="portal_tokens")
    op.drop_column("portal_tokens", "ticket_id")
