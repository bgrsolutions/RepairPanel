import logging
from datetime import datetime

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from app.models import AuditLog, PartOrder, Ticket, TicketNote
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status, ticket_age_days

log = logging.getLogger(__name__)

core_bp = Blueprint("core", __name__)


def _fetch_activity_items(limit: int = 12) -> list[dict]:
    """Fetch recent activity from AuditLog, falling back to TicketNote for SQLite."""
    items: list[dict] = []

    # Try AuditLog first (uses JSONB, only works with PostgreSQL)
    try:
        logs = (
            AuditLog.query
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
        for entry in logs:
            description = entry.message or f"{entry.action} on {entry.entity_type}"
            entity_ref = None
            ticket_id = None
            if entry.entity_type == "Ticket" and entry.entity_id:
                ticket_id = entry.entity_id
                entity_ref = entry.entity_id
            elif entry.details and isinstance(entry.details, dict):
                ticket_id = entry.details.get("ticket_id")
                entity_ref = entry.details.get("ticket_number") or ticket_id
            items.append({
                "timestamp": entry.created_at,
                "description": description,
                "entity_ref": entity_ref,
                "ticket_id": ticket_id,
            })
        if items:
            return items
    except Exception:
        log.debug("AuditLog query failed (likely SQLite/JSONB); falling back to TicketNote")

    # Fallback: use TicketNote records
    try:
        notes = (
            TicketNote.query
            .order_by(TicketNote.created_at.desc())
            .limit(limit)
            .all()
        )
        note_type_labels = {
            "internal": "Internal note added",
            "customer_update": "Customer update posted",
            "communication": "Communication logged",
            "diagnostic": "Diagnostic note added",
        }
        for note in notes:
            label = note_type_labels.get(note.note_type, f"Note ({note.note_type}) added")
            ticket = note.ticket
            ticket_number = getattr(ticket, "ticket_number", None) if ticket else None
            content_preview = (note.content[:80] + "...") if len(note.content) > 80 else note.content
            items.append({
                "timestamp": note.created_at,
                "description": f"{label}: {content_preview}",
                "entity_ref": ticket_number,
                "ticket_id": str(ticket.id) if ticket else None,
            })
    except Exception:
        log.debug("TicketNote query also failed; returning empty activity list")

    return items


@core_bp.get("/")
@login_required
def dashboard():
    active_tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()

    now = datetime.utcnow()
    today = now.date()

    stats = {
        "open_tickets": len([t for t in active_tickets if normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES]),
        "awaiting_diagnosis": sum(1 for t in active_tickets if normalize_ticket_status(t.internal_status) == Ticket.STATUS_AWAITING_DIAGNOSTICS),
        "in_repair": sum(1 for t in active_tickets if normalize_ticket_status(t.internal_status) in {Ticket.STATUS_IN_REPAIR, Ticket.STATUS_TESTING_QA}),
        "ready_for_collection": sum(1 for t in active_tickets if normalize_ticket_status(t.internal_status) == Ticket.STATUS_READY_FOR_COLLECTION),
        "aging_tickets": sum(1 for t in active_tickets if ticket_age_days(t, now) >= 3 and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
        "overdue_tickets": sum(1 for t in active_tickets if is_ticket_overdue(t, now, sla_days=current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5))),
        "new_today": sum(1 for t in active_tickets if t.created_at.date() == today),
    }

    recent_tickets = sorted(active_tickets, key=lambda t: t.created_at, reverse=True)[:6]
    overdue_part_ticket_ids = {
        str(order.ticket_id)
        for order in PartOrder.query.filter(PartOrder.ticket_id.is_not(None), PartOrder.estimated_arrival_at.is_not(None)).all()
        if order.status not in {"received", "cancelled"} and order.estimated_arrival_at < now
    }

    attention_tickets = []
    for ticket in active_tickets:
        normalized = normalize_ticket_status(ticket.internal_status)
        if normalized in Ticket.CLOSED_STATUSES:
            continue
        overdue = is_ticket_overdue(ticket, now, sla_days=current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5))
        overdue_parts = str(ticket.id) in overdue_part_ticket_ids
        blocked = overdue_parts and normalized == Ticket.STATUS_AWAITING_PARTS
        if overdue or overdue_parts or blocked:
            attention_tickets.append(ticket)
    attention_tickets = attention_tickets[:8]

    technician_workload = {
        "assigned": sum(1 for t in active_tickets if t.assigned_technician_id and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
        "unassigned": sum(1 for t in active_tickets if not t.assigned_technician_id and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
    }

    activity_items = _fetch_activity_items(limit=12)

    return render_template(
        "core/dashboard.html",
        stats=stats,
        recent_tickets=recent_tickets,
        attention_tickets=attention_tickets,
        technician_workload=technician_workload,
        activity_items=activity_items,
    )
