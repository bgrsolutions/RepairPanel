from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Customer(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "customers"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)

    primary_branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    primary_branch = relationship("Branch")

    devices = relationship("Device", back_populates="customer", lazy="selectin")
    tickets = relationship("Ticket", back_populates="customer", lazy="selectin")
