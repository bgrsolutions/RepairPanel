import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Part(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "parts"

    sku: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    sale_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    serial_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StockLocation(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "stock_locations"

    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_type: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    branch = relationship("Branch")


class StockLevel(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "stock_levels"

    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_locations.id"), nullable=False, index=True)
    on_hand_qty: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    reserved_qty: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    part = relationship("Part")
    branch = relationship("Branch")
    location = relationship("StockLocation")


class StockMovement(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "stock_movements"

    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stock_locations.id"), nullable=True, index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    part = relationship("Part")
    branch = relationship("Branch")
    location = relationship("StockLocation")
    ticket = relationship("Ticket")


class StockReservation(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "stock_reservations"

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_locations.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="reserved", index=True)

    ticket = relationship("Ticket")
    part = relationship("Part")
    branch = relationship("Branch")
    location = relationship("StockLocation")
