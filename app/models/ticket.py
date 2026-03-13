from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Ticket(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "tickets"

    STATUS_UNASSIGNED = "unassigned"
    STATUS_ASSIGNED = "assigned"
    STATUS_AWAITING_DIAGNOSTICS = "awaiting_diagnostics"
    STATUS_AWAITING_QUOTE_APPROVAL = "awaiting_quote_approval"
    STATUS_AWAITING_PARTS = "awaiting_parts"
    STATUS_IN_REPAIR = "in_repair"
    STATUS_TESTING_QA = "testing_qa"
    STATUS_READY_FOR_COLLECTION = "ready_for_collection"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    ACTIVE_STATUSES = {
        STATUS_UNASSIGNED,
        STATUS_ASSIGNED,
        STATUS_AWAITING_DIAGNOSTICS,
        STATUS_AWAITING_QUOTE_APPROVAL,
        STATUS_AWAITING_PARTS,
        STATUS_IN_REPAIR,
        STATUS_TESTING_QA,
        STATUS_READY_FOR_COLLECTION,
    }
    CLOSED_STATUSES = {STATUS_COMPLETED, STATUS_CANCELLED}

    ticket_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)

    internal_status: Mapped[str] = mapped_column(String(80), default=STATUS_UNASSIGNED, nullable=False, index=True)
    customer_status: Mapped[str] = mapped_column(String(80), default="Received", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)

    assigned_technician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sla_target_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    quoted_completion_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    issue_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    branch = relationship("Branch")
    customer = relationship("Customer", back_populates="tickets")
    device = relationship("Device", back_populates="tickets")
    assigned_technician = relationship("User", foreign_keys=[assigned_technician_id])

    @property
    def is_closed(self) -> bool:
        return self.internal_status in self.CLOSED_STATUSES
