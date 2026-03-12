import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class TicketNote(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "ticket_notes"

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    ticket = relationship("Ticket")
    author_user = relationship("User")
