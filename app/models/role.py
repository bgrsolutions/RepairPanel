from sqlalchemy import String, Table, Column, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import TimestampMixin, UUIDMixin


role_permissions = Table(
    "role_permissions",
    db.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission", String(100), primary_key=True),
)


class Role(UUIDMixin, TimestampMixin, db.Model):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self):
        return f"<Role {self.name}>"
