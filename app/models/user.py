import uuid

from flask_login import UserMixin
from sqlalchemy import Boolean, ForeignKey, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


user_roles = Table(
    "user_roles",
    db.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)


user_branch_access = Table(
    "user_branch_access",
    db.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("branch_id", ForeignKey("branches.id"), primary_key=True),
)


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, UserMixin, db.Model):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    default_branch_id: Mapped[str | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    default_branch = relationship("Branch", foreign_keys=[default_branch_id])

    roles = relationship("Role", secondary=user_roles, lazy="joined")
    branches = relationship("Branch", secondary=user_branch_access, lazy="selectin")

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def has_role(self, role_name: str) -> bool:
        return any(role.name == role_name for role in self.roles)

    def get_id(self):
        # Ensure Flask-Login always stores a JSON-serializable identifier.
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    try:
        normalized_id = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None
    return db.session.get(User, normalized_id)
