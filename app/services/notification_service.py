import json

from app.extensions import db
from app.models import NotificationDelivery, NotificationEvent, NotificationTemplate, Ticket


SUPPORTED_EVENT_TYPES = {
    "ticket_created",
    "diagnosis_complete",
    "quote_ready",
    "quote_approved",
    "quote_declined",
    "part_arrived",
    "ready_for_collection",
}


def create_notification_event(event_type: str, ticket: Ticket, context: dict | None = None):
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError("Unsupported event type")

    event = NotificationEvent(
        event_type=event_type,
        ticket_id=ticket.id,
        quote_id=None,
        customer_id=ticket.customer_id,
        context_json=json.dumps(context or {}),
    )
    db.session.add(event)
    db.session.flush()

    template = NotificationTemplate.query.filter_by(key=event_type, language=ticket.customer.preferred_language, is_active=True).first()
    if template is None:
        template = NotificationTemplate.query.filter_by(key=event_type, language="en", is_active=True).first()

    delivery = NotificationDelivery(
        event_id=event.id,
        template_id=template.id if template else None,
        channel="email",
        recipient=ticket.customer.email,
        status="pending",
    )
    db.session.add(delivery)
    return event, delivery
