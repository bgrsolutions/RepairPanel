import secrets
from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class Quote(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "quotes"

    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    notes_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    options = relationship("QuoteOption", back_populates="quote", cascade="all, delete-orphan", lazy="selectin")
    approvals = relationship("QuoteApproval", back_populates="quote", cascade="all, delete-orphan", lazy="selectin")

    @property
    def is_standalone(self) -> bool:
        return self.ticket_id is None

    @property
    def display_customer_name(self) -> str:
        if self.ticket and self.ticket.customer:
            return self.ticket.customer.full_name
        if self.customer:
            return self.customer.full_name
        return self.customer_name or "Unknown"

    @property
    def display_device(self) -> str:
        if self.ticket and self.ticket.device:
            return f"{self.ticket.device.brand} {self.ticket.device.model}"
        return self.device_description or ""


class QuoteOption(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "quote_options"

    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    quote = relationship("Quote", back_populates="options")
    lines = relationship("QuoteLine", back_populates="option", cascade="all, delete-orphan", lazy="selectin")


class QuoteLine(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "quote_lines"

    option_id: Mapped[str] = mapped_column(ForeignKey("quote_options.id"), nullable=False, index=True)
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    part_id: Mapped[str | None] = mapped_column(ForeignKey("parts.id"), nullable=True, index=True)

    option = relationship("QuoteOption", back_populates="lines")
    part = relationship("Part")


class QuoteApproval(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "quote_approvals"

    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(24))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    declined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_choice: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stripe_checkout_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7))

    quote = relationship("Quote", back_populates="approvals")
