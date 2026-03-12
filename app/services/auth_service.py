from flask_login import login_user, logout_user

from app.models import User
from app.services.audit_service import log_action


def authenticate(email: str, password: str):
    user = User.query.filter_by(email=email.lower().strip()).first()
    if not user:
        return None
    if not user.is_active or user.deleted_at is not None:
        return None
    if not user.check_password(password):
        return None

    login_user(user)
    log_action("auth.login", "User", str(user.id), message="User login successful")
    return user


def sign_out():
    log_action("auth.logout", "User", message="User logout")
    logout_user()
