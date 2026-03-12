from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class ExportQueueItem(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "export_queue_items"

    system: Mapped[str] = mapped_column(String(50), nullable=False, default="odoo", index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, default="ticket", index=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_handled_externally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ticket = relationship("Ticket")
