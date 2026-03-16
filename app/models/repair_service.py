import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class RepairService(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "repair_services"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    device_category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parts.id"), nullable=True, index=True
    )
    labour_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    default_part = relationship("Part", foreign_keys=[default_part_id], lazy="selectin")

    def __repr__(self):
        return f"<RepairService {self.name}>"
