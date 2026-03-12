from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class NotificationTemplate(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "notification_templates"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    subject_template: Mapped[str] = mapped_column(String(255), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NotificationEvent(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "notification_events"

    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    quote_id: Mapped[str | None] = mapped_column(ForeignKey("quotes.id"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket = relationship("Ticket")
    quote = relationship("Quote")
    customer = relationship("Customer")


class NotificationDelivery(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "notification_deliveries"

    event_id: Mapped[str] = mapped_column(ForeignKey("notification_events.id"), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("notification_templates.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    event = relationship("NotificationEvent")
    template = relationship("NotificationTemplate")
