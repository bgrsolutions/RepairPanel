import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Device(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "devices"

    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    imei: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer", back_populates="devices")

    tickets = relationship("Ticket", back_populates="device", lazy="selectin")

    # --- Phase 18: Richer device details ---
    storage: Mapped[str | None] = mapped_column(String(60), nullable=True)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    carrier_lock: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fmi_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cosmetic_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    battery_health: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cpu: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ram: Mapped[str | None] = mapped_column(String(60), nullable=True)
    storage_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gpu: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_info: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Phase 18: Secure access/unlock data ---
    unlock_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unlock_value_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    unlock_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Phase 18: IMEI lookup cache ---
    imei_lookup_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Phase 18.5: Richer device data ---
    imei2: Mapped[str | None] = mapped_column(String(60), nullable=True)
    eid: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purchase_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sold_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    production_date: Mapped[str | None] = mapped_column(String(60), nullable=True)
    warranty_status: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activation_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    applecare_eligible: Mapped[str | None] = mapped_column(String(120), nullable=True)
    technical_support: Mapped[str | None] = mapped_column(String(120), nullable=True)
    blacklist_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    buyer_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_lookup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# --- Phase 18: Device-type pre-check definitions ---

class DevicePreCheckTemplate(UUIDMixin, TimestampMixin, db.Model):
    """Defines which pre-check items apply to which device category."""
    __tablename__ = "device_precheck_templates"

    device_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    check_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label_en: Mapped[str] = mapped_column(String(200), nullable=False)
    label_es: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --- Phase 18: Service-Parts linking ---

service_part_links = db.Table(
    "service_part_links",
    db.Column("service_id", ForeignKey("repair_services.id"), primary_key=True),
    db.Column("part_id", ForeignKey("parts.id"), primary_key=True),
    db.Column("quantity", Numeric(10, 2), default=1, nullable=False),
)
