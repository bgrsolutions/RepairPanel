from sqlalchemy import ForeignKey, String
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

    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer", back_populates="devices")

    tickets = relationship("Ticket", back_populates="device", lazy="selectin")
