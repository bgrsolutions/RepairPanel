import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


part_category_links = Table(
    "part_category_links",
    db.metadata,
    db.Column("part_id", ForeignKey("parts.id"), primary_key=True),
    db.Column("category_id", ForeignKey("part_categories.id"), primary_key=True),
)


class Part(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "parts"

    sku: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    lead_time_days: Mapped[int | None] = mapped_column(nullable=True)
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    sale_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    serial_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True, default=3)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    default_supplier = relationship("Supplier")
    categories = relationship("PartCategory", secondary=part_category_links, back_populates="parts", lazy="noload")
    supplier_links = relationship("PartSupplier", back_populates="part", cascade="all, delete-orphan", lazy="noload")


class PartCategory(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "part_categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parts = relationship("Part", secondary=part_category_links, back_populates="categories", lazy="noload")


class PartSupplier(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "part_suppliers"

    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    part = relationship("Part", back_populates="supplier_links")
    supplier = relationship("Supplier")


class StockLayer(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "stock_layers"

    part_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parts.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_locations.id"), nullable=False, index=True)
    source_movement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stock_movements.id"), nullable=True, index=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    quantity_received: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_remaining: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    part = relationship("Part")
    branch = relationship("Branch")
    location = relationship("StockLocation")
    source_movement = relationship("StockMovement")


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
