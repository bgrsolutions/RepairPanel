from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Customer(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "customers"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)

    # Phase 7A: Business/company identity
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, default="individual", index=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cif_vat: Mapped[str | None] = mapped_column(String(30), nullable=True)
    billing_address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    billing_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    billing_country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    primary_branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    primary_branch = relationship("Branch")

    devices = relationship("Device", back_populates="customer", lazy="selectin")
    tickets = relationship("Ticket", back_populates="customer", lazy="selectin")

    @property
    def is_business(self) -> bool:
        return self.customer_type == "business"

    @property
    def display_name(self) -> str:
        if self.is_business and self.company_name:
            return f"{self.company_name} ({self.full_name})"
        return self.full_name

    @property
    def short_name(self) -> str:
        if self.is_business and self.company_name:
            return self.company_name
        parts = self.full_name.split()
        return parts[-1] if parts else self.full_name

    @property
    def billing_address(self) -> str:
        parts = [self.billing_address_line_1, self.billing_address_line_2,
                 self.billing_postcode, self.billing_city, self.billing_region, self.billing_country]
        return ", ".join(p for p in parts if p)
