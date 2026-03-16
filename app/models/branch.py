import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Branch(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "branches"

    # --- Original fields (preserved) ---
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Phase 6B: Store/Location fields ---
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    island_or_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True, default="Spain")
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_prefix: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quote_prefix: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="branches", lazy="selectin")

    def __repr__(self):
        return f"<Branch {self.code}>"

    @property
    def full_address(self):
        parts = [self.address_line_1, self.address_line_2, self.postcode, self.city, self.island_or_region, self.country]
        return ", ".join(p for p in parts if p)
