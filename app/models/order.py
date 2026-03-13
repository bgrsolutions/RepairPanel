import uuid

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class PartOrder(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "part_orders"

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, default="repair", index=True)

    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estimated_arrival_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    ordered_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket = relationship("Ticket")
    supplier = relationship("Supplier")
    branch = relationship("Branch")
    lines = relationship("PartOrderLine", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    events = relationship("PartOrderEvent", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class PartOrderLine(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "part_order_lines"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("part_orders.id"), nullable=False, index=True)
    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    description_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    received_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)

    order = relationship("PartOrder", back_populates="lines")
    part = relationship("Part")


class PartOrderEvent(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "part_order_events"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("part_orders.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order = relationship("PartOrder", back_populates="events")
