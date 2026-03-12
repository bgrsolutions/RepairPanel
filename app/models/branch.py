from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Branch(UUIDMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "branches"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<Branch {self.code}>"
