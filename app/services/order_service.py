from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models import PartOrderEvent


def append_order_event(order, event_type: str, notes: str | None = None):
    order.status = event_type
    event = PartOrderEvent(order_id=order.id, event_type=event_type, occurred_at=datetime.utcnow(), notes=notes)
    db.session.add(event)
    db.session.flush()
    return event


def order_total_cost(order) -> Decimal:
    total = Decimal("0")
    for line in order.lines:
        qty = Decimal(str(line.quantity or 0))
        unit = Decimal(str(line.unit_cost or 0))
        total += qty * unit
    return total


def line_remaining_qty(line) -> Decimal:
    return max(Decimal(str(line.quantity or 0)) - Decimal(str(line.received_quantity or 0)), Decimal("0"))
