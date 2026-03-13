import json
from decimal import Decimal

from app.extensions import db
from app.models import ExportQueueItem, PartOrder, Quote, StockReservation, Ticket
from app.services.quote_service import compute_quote_totals


def _as_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def build_ticket_export_payload(ticket: Ticket) -> dict:
    latest_quote = Quote.query.filter_by(ticket_id=ticket.id).order_by(Quote.version.desc(), Quote.created_at.desc()).first()
    option_totals, quote_total = ([], 0)
    labour_lines = []
    if latest_quote:
        option_totals, quote_total = compute_quote_totals(latest_quote)
        for option in latest_quote.options:
            for line in option.lines:
                if line.line_type == "labour":
                    labour_lines.append(
                        {
                            "description": line.description,
                            "quantity": _as_float(line.quantity),
                            "unit_price": _as_float(line.unit_price),
                        }
                    )

    reservations = StockReservation.query.filter_by(ticket_id=ticket.id).all()
    parts_used = [
        {
            "sku": r.part.sku,
            "name": r.part.name,
            "quantity": _as_float(r.quantity),
            "status": r.status,
        }
        for r in reservations
    ]

    orders = PartOrder.query.filter_by(ticket_id=ticket.id).all()
    ordered_parts = [
        {
            "supplier": o.supplier.name,
            "status": o.status,
            "estimated_arrival_at": o.estimated_arrival_at.isoformat() if o.estimated_arrival_at else None,
            "tracking_number": o.tracking_number,
            "supplier_reference": o.supplier_reference,
            "reference": o.reference,
        }
        for o in orders
    ]

    return {
        "customer": {
            "name": ticket.customer.full_name,
            "phone": ticket.customer.phone,
            "email": ticket.customer.email,
            "preferred_language": ticket.customer.preferred_language,
        },
        "device": {
            "category": ticket.device.category,
            "brand": ticket.device.brand,
            "model": ticket.device.model,
            "serial_number": ticket.device.serial_number,
            "imei": ticket.device.imei,
        },
        "ticket": {
            "ticket_number": ticket.ticket_number,
            "branch_code": ticket.branch.code,
            "internal_status": ticket.internal_status,
            "customer_status": ticket.customer_status,
            "priority": ticket.priority,
        },
        "labour_lines": labour_lines,
        "parts_used": parts_used,
        "ordered_parts": ordered_parts,
        "quote": {
            "quote_total": _as_float(quote_total),
            "option_totals": [
                {"option_id": str(item["option"].id), "option_name": item["option"].name, "total": _as_float(item["total"])}
                for item in option_totals
            ],
            "currency": latest_quote.currency if latest_quote else "EUR",
            "status": latest_quote.status if latest_quote else "none",
        },
        "payment_handled_externally": True,
    }


def queue_ticket_export(ticket: Ticket, system: str = "odoo") -> ExportQueueItem:
    payload = build_ticket_export_payload(ticket)
    item = ExportQueueItem(
        system=system,
        entity_type="ticket",
        ticket_id=ticket.id,
        payload_json=json.dumps(payload),
        status="queued",
        payment_handled_externally=True,
    )
    db.session.add(item)
    db.session.flush()
    return item
