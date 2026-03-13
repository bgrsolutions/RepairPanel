import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


class AppSetting(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)

    branch = relationship("Branch")
