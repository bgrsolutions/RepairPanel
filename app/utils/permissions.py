from functools import wraps

from flask import abort, flash
from flask_login import current_user


def roles_required(*role_names):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            user_roles = {role.name for role in current_user.roles}
            if not any(role in user_roles for role in role_names):
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


def permission_required(check_fn):
    """Decorator that gates a route on a permission_service check function.

    Usage:
        from app.services.permission_service import can_delete_part

        @bp.post("/parts/<id>/delete")
        @login_required
        @permission_required(can_delete_part)
        def delete_part(id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not check_fn():
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator
