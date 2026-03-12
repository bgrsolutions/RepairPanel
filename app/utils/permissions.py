from functools import wraps

from flask import abort
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
