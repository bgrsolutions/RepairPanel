from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Supplier(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
