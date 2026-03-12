from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class Diagnostic(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "diagnostics"

    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    entered_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    customer_reported_fault: Mapped[str] = mapped_column(Text, nullable=False)
    technician_diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_repair: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_labour: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    repair_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket = relationship("Ticket")
    entered_by_user = relationship("User")
