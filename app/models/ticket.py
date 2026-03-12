from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Ticket(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "tickets"

    ticket_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)

    internal_status: Mapped[str] = mapped_column(String(80), default="New", nullable=False, index=True)
    customer_status: Mapped[str] = mapped_column(String(80), default="Received", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)

    assigned_technician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    branch = relationship("Branch")
    customer = relationship("Customer", back_populates="tickets")
    device = relationship("Device", back_populates="tickets")
    assigned_technician = relationship("User", foreign_keys=[assigned_technician_id])
