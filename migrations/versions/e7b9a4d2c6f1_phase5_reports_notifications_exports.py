"""phase5 reports notifications exports

Revision ID: e7b9a4d2c6f1
Revises: d4a1c2e9b7f0
Create Date: 2026-03-12 19:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e7b9a4d2c6f1"
down_revision = "d4a1c2e9b7f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_templates",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("subject_template", sa.String(length=255), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_templates_key"), "notification_templates", ["key"], unique=True)

    op.create_table(
        "notification_events",
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_events_customer_id"), "notification_events", ["customer_id"], unique=False)
    op.create_index(op.f("ix_notification_events_event_type"), "notification_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_notification_events_quote_id"), "notification_events", ["quote_id"], unique=False)
    op.create_index(op.f("ix_notification_events_ticket_id"), "notification_events", ["ticket_id"], unique=False)

    op.create_table(
        "notification_deliveries",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["notification_events.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["notification_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_deliveries_event_id"), "notification_deliveries", ["event_id"], unique=False)
    op.create_index(op.f("ix_notification_deliveries_status"), "notification_deliveries", ["status"], unique=False)
    op.create_index(op.f("ix_notification_deliveries_template_id"), "notification_deliveries", ["template_id"], unique=False)

    op.create_table(
        "export_queue_items",
        sa.Column("system", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("external_reference", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payment_handled_externally", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_export_queue_items_entity_type"), "export_queue_items", ["entity_type"], unique=False)
    op.create_index(op.f("ix_export_queue_items_status"), "export_queue_items", ["status"], unique=False)
    op.create_index(op.f("ix_export_queue_items_system"), "export_queue_items", ["system"], unique=False)
    op.create_index(op.f("ix_export_queue_items_ticket_id"), "export_queue_items", ["ticket_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_export_queue_items_ticket_id"), table_name="export_queue_items")
    op.drop_index(op.f("ix_export_queue_items_system"), table_name="export_queue_items")
    op.drop_index(op.f("ix_export_queue_items_status"), table_name="export_queue_items")
    op.drop_index(op.f("ix_export_queue_items_entity_type"), table_name="export_queue_items")
    op.drop_table("export_queue_items")

    op.drop_index(op.f("ix_notification_deliveries_template_id"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_status"), table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_event_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")

    op.drop_index(op.f("ix_notification_events_ticket_id"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_quote_id"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_event_type"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_customer_id"), table_name="notification_events")
    op.drop_table("notification_events")

    op.drop_index(op.f("ix_notification_templates_key"), table_name="notification_templates")
    op.drop_table("notification_templates")
