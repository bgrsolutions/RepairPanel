import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class Booking(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "bookings"

    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    repair_service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repair_services.id"), nullable=True, index=True
    )
    linked_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tickets.id"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id"), nullable=True, index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    converted_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tickets.id"), nullable=True, index=True
    )

    # Phase 16 lifecycle statuses
    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_ARRIVED = "arrived"
    STATUS_NO_SHOW = "no_show"
    STATUS_CONVERTED = "converted"
    STATUS_CANCELLED = "cancelled"

    # Legacy statuses kept for backward compat
    STATUS_SCHEDULED = "scheduled"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"

    ACTIVE_STATUSES = {STATUS_NEW, STATUS_CONFIRMED, STATUS_ARRIVED}
    TERMINAL_STATUSES = {STATUS_NO_SHOW, STATUS_CONVERTED, STATUS_CANCELLED}

    # Valid status transitions
    VALID_TRANSITIONS = {
        STATUS_NEW: {STATUS_CONFIRMED, STATUS_ARRIVED, STATUS_CANCELLED, STATUS_NO_SHOW},
        STATUS_CONFIRMED: {STATUS_ARRIVED, STATUS_CANCELLED, STATUS_NO_SHOW},
        STATUS_ARRIVED: {STATUS_CONVERTED, STATUS_CANCELLED},
        # Legacy scheduled maps same as new
        STATUS_SCHEDULED: {STATUS_CONFIRMED, STATUS_ARRIVED, STATUS_CANCELLED, STATUS_NO_SHOW},
        STATUS_IN_PROGRESS: {STATUS_CONVERTED, STATUS_CANCELLED, STATUS_COMPLETED},
        STATUS_COMPLETED: set(),
        STATUS_NO_SHOW: set(),
        STATUS_CONVERTED: set(),
        STATUS_CANCELLED: set(),
    }

    ALL_STATUSES = [
        STATUS_NEW, STATUS_CONFIRMED, STATUS_ARRIVED,
        STATUS_NO_SHOW, STATUS_CONVERTED, STATUS_CANCELLED,
    ]

    # Relationships
    location = relationship("Branch", foreign_keys=[location_id], lazy="selectin")
    customer = relationship("Customer", foreign_keys=[customer_id], lazy="selectin")
    repair_service = relationship("RepairService", foreign_keys=[repair_service_id], lazy="selectin")
    linked_ticket = relationship("Ticket", foreign_keys=[linked_ticket_id], lazy="selectin")
    converted_ticket = relationship("Ticket", foreign_keys=[converted_ticket_id], lazy="selectin")
    device = relationship("Device", foreign_keys=[device_id], lazy="selectin")

    def can_transition_to(self, new_status: str) -> bool:
        """Check if a status transition is valid."""
        allowed = self.VALID_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def is_converted(self) -> bool:
        return self.status == self.STATUS_CONVERTED

    def __repr__(self):
        return f"<Booking {self.id} @ {self.start_time}>"
