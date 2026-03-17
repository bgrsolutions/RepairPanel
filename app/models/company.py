from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Company(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "companies"

    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trading_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cif_nif: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tax_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="IGIC")
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_quote_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_repair_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_footer: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_warranty_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=90)
    default_warranty_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    branches = relationship("Branch", back_populates="company", lazy="selectin")

    def __repr__(self):
        return f"<Company {self.legal_name}>"

    @property
    def display_name(self):
        return self.trading_name or self.legal_name
