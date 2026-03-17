from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class TicketWarranty(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    """Warranty record captured when a ticket is completed/closed.

    Tracks the warranty period, type, coverage, terms, and claim history.
    Links to the original ticket, customer, device, and branch.
    """
    __tablename__ = "ticket_warranties"

    # Warranty type constants
    TYPE_NO_WARRANTY = "no_warranty"
    TYPE_STANDARD = "standard"
    TYPE_CUSTOM = "custom"

    VALID_TYPES = {TYPE_NO_WARRANTY, TYPE_STANDARD, TYPE_CUSTOM}

    # Status constants
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CLAIMED = "claimed"
    STATUS_VOIDED = "voided"

    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)

    # Warranty type and coverage
    warranty_type: Mapped[str] = mapped_column(String(30), nullable=False, default=TYPE_STANDARD)
    warranty_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    covers_labour: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    covers_parts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Warranty terms / notes
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parts_used: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_ACTIVE, index=True)
    voided_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Claim tracking
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_claim_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who created/issued the warranty
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Email notification tracking
    email_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    ticket = relationship("Ticket", backref="warranty", foreign_keys=[ticket_id])
    customer = relationship("Customer", backref="warranties")
    device = relationship("Device", backref="warranties")
    branch = relationship("Branch")
    voided_by = relationship("User", foreign_keys=[voided_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    @property
    def is_active(self) -> bool:
        if self.warranty_type == self.TYPE_NO_WARRANTY:
            return False
        return self.status == self.STATUS_ACTIVE and datetime.utcnow() <= self.expires_at

    @property
    def is_expired(self) -> bool:
        if self.warranty_type == self.TYPE_NO_WARRANTY:
            return False
        return self.status == self.STATUS_EXPIRED or (
            self.status == self.STATUS_ACTIVE and datetime.utcnow() > self.expires_at
        )

    @property
    def days_remaining(self) -> int:
        if self.warranty_type == self.TYPE_NO_WARRANTY:
            return 0
        if self.status != self.STATUS_ACTIVE:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def coverage_description(self) -> str:
        if self.warranty_type == self.TYPE_NO_WARRANTY:
            return "No warranty"
        parts = []
        if self.covers_labour:
            parts.append("Labour")
        if self.covers_parts:
            parts.append("Parts")
        return " + ".join(parts) if parts else "Limited"

    @property
    def type_label(self) -> str:
        labels = {
            self.TYPE_NO_WARRANTY: "No Warranty",
            self.TYPE_STANDARD: "Standard",
            self.TYPE_CUSTOM: "Custom",
        }
        return labels.get(self.warranty_type, self.warranty_type)

    @property
    def status_label(self) -> str:
        if self.warranty_type == self.TYPE_NO_WARRANTY:
            return "No Warranty"
        labels = {
            self.STATUS_ACTIVE: "Active",
            self.STATUS_EXPIRED: "Expired",
            self.STATUS_CLAIMED: "Claimed",
            self.STATUS_VOIDED: "Voided",
        }
        # Check for runtime expiry even if status not yet updated
        if self.status == self.STATUS_ACTIVE and datetime.utcnow() > self.expires_at:
            return "Expired"
        return labels.get(self.status, self.status)

    def __repr__(self):
        return f"<TicketWarranty ticket={self.ticket_id} type={self.warranty_type} status={self.status}>"
