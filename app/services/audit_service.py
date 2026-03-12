from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def log_action(action: str, entity_type: str, entity_id: str | None = None, details: dict | None = None, message: str | None = None):
    actor_user_id = str(current_user.id) if current_user.is_authenticated else None
    ip_address = request.remote_addr if has_request_context() else None
    user_agent = request.user_agent.string if has_request_context() else None

    audit = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        message=message,
    )
    db.session.add(audit)
    db.session.commit()
