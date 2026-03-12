from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.models import NotificationDelivery, NotificationEvent, NotificationTemplate, Ticket
from app.services.notification_service import SUPPORTED_EVENT_TYPES, create_notification_event


notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.get("/templates")
@login_required
def list_templates():
    templates = NotificationTemplate.query.order_by(NotificationTemplate.key.asc()).all()
    return render_template("notifications/templates.html", templates=templates)


@notifications_bp.post("/templates")
@login_required
def create_template():
    key = request.form.get("key", "").strip()
    subject = request.form.get("subject_template", "").strip()
    body = request.form.get("body_template", "").strip()
    language = request.form.get("language", "en").strip() or "en"
    if not key or not subject or not body:
        flash(_("Template key, subject and body are required"), "error")
        return redirect(url_for("notifications.list_templates"))

    template = NotificationTemplate(
        key=key,
        channel="email",
        language=language,
        subject_template=subject,
        body_template=body,
        is_active=True,
    )
    db.session.add(template)
    db.session.commit()
    flash(_("Notification template created"), "success")
    return redirect(url_for("notifications.list_templates"))


@notifications_bp.get("/events")
@login_required
def list_events():
    events = NotificationEvent.query.order_by(NotificationEvent.created_at.desc()).limit(100).all()
    deliveries = NotificationDelivery.query.order_by(NotificationDelivery.created_at.desc()).limit(100).all()
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(50).all()
    return render_template(
        "notifications/events.html",
        events=events,
        deliveries=deliveries,
        tickets=tickets,
        event_types=sorted(SUPPORTED_EVENT_TYPES),
    )


@notifications_bp.post("/events")
@login_required
def create_event():
    ticket_id = request.form.get("ticket_id")
    event_type = request.form.get("event_type")
    ticket = db.session.get(Ticket, ticket_id) if ticket_id else None
    if not ticket:
        flash(_("Ticket is required"), "error")
        return redirect(url_for("notifications.list_events"))

    create_notification_event(event_type=event_type, ticket=ticket, context={"source": "manual"})
    db.session.commit()
    flash(_("Notification event queued"), "success")
    return redirect(url_for("notifications.list_events"))
