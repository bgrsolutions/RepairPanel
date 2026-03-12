from datetime import datetime

from app.extensions import db
from app.models import PartOrderEvent


def append_order_event(order, event_type: str, notes: str | None = None):
    order.status = event_type
    event = PartOrderEvent(order_id=order.id, event_type=event_type, occurred_at=datetime.utcnow(), notes=notes)
    db.session.add(event)
    db.session.flush()
    return event
