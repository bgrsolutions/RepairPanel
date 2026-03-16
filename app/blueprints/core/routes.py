import logging
from datetime import datetime, timedelta

from flask import Blueprint, current_app, render_template
from flask_login import login_required
from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.models import AuditLog, PartOrder, Ticket, TicketNote
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status, ticket_age_days

log = logging.getLogger(__name__)

core_bp = Blueprint("core", __name__)


_ACTION_LABELS = {
    "ticket.create": "New ticket created",
    "ticket.archive": "Ticket archived",
    "ticket.reopen": "Ticket reopened",
    "ticket.send_update": "Customer update sent",
    "diagnostic.save": "Diagnostics recorded",
    "intake.create": "New intake submitted",
    "intake.convert": "Intake converted to ticket",
    "quote.create": "Quote created",
    "quote.send": "Quote sent for approval",
    "quote.approve": "Quote approved",
    "quote.decline": "Quote declined",
}


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
            # Build a human-friendly description
            action_label = _ACTION_LABELS.get(entry.action, entry.action.replace(".", " ").replace("_", " ").title())
            details = entry.details if isinstance(entry.details, dict) else {}
            ticket_number = details.get("ticket_number", "")
            ticket_id = None
            entity_ref = None

            if entry.entity_type == "Ticket" and entry.entity_id:
                ticket_id = entry.entity_id
                entity_ref = ticket_number or entry.entity_id
            elif details.get("ticket_id"):
                ticket_id = details["ticket_id"]
                entity_ref = ticket_number or ticket_id

            # Build context string with ticket number
            description = action_label
            if ticket_number:
                description = f"{action_label} — {ticket_number}"
            elif entry.message:
                description = entry.message

            # Add actor name if available
            actor_name = None
            if entry.actor_user_id:
                try:
                    from app.models import User
                    actor = db.session.get(User, entry.actor_user_id)
                    if actor:
                        actor_name = actor.full_name
                except Exception:
                    pass

            items.append({
                "timestamp": entry.created_at,
                "description": description,
                "entity_ref": entity_ref,
                "ticket_id": ticket_id,
                "actor": actor_name,
                "action_type": entry.action.split(".")[0] if entry.action else "other",
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
        note_type_icons = {
            "internal": "ticket",
            "customer_update": "ticket",
            "communication": "ticket",
            "diagnostic": "diagnostic",
        }
        for note in notes:
            label = note_type_labels.get(note.note_type, f"Note ({note.note_type}) added")
            ticket = note.ticket
            ticket_number = getattr(ticket, "ticket_number", None) if ticket else None
            customer_name = ticket.customer.full_name if ticket and ticket.customer else None
            content_preview = (note.content[:60] + "...") if note.content and len(note.content) > 60 else (note.content or "")
            description = f"{label}: {content_preview}"
            if ticket_number:
                description = f"{label} on {ticket_number}"
                if customer_name:
                    description += f" ({customer_name})"
            items.append({
                "timestamp": note.created_at,
                "description": description,
                "entity_ref": ticket_number,
                "ticket_id": str(ticket.id) if ticket else None,
                "actor": note.author.full_name if note.author_user_id and hasattr(note, 'author') and note.author else None,
                "action_type": note_type_icons.get(note.note_type, "other"),
            })
    except Exception:
        log.debug("TicketNote query also failed; returning empty activity list")

    return items


@core_bp.get("/")
@login_required
def dashboard():
    from app.services.workflow_service import detect_blockers, workshop_metrics

    active_tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()

    now = datetime.utcnow()
    today = now.date()
    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)

    # Phase 8I: workshop metrics
    metrics = workshop_metrics(active_tickets, now=now, sla_days=sla_days)

    stats = {
        "open_tickets": len([t for t in active_tickets if normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES]),
        "awaiting_diagnosis": metrics["in_diagnosis"],
        "awaiting_quote": metrics["awaiting_quote"],
        "awaiting_parts": metrics["awaiting_parts"],
        "in_repair": metrics["in_repair"] + metrics["in_testing"],
        "ready_for_collection": metrics["ready_for_collection"],
        "aging_tickets": sum(1 for t in active_tickets if ticket_age_days(t, now) >= 3 and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
        "overdue_tickets": metrics["overdue"],
        "new_today": sum(1 for t in active_tickets if t.created_at.date() == today),
    }

    recent_tickets = sorted(active_tickets, key=lambda t: t.created_at, reverse=True)[:6]

    # Phase 8G: Improved attention tickets using blocker detection
    attention_tickets = []
    for ticket in active_tickets:
        normalized = normalize_ticket_status(ticket.internal_status)
        if normalized in Ticket.CLOSED_STATUSES:
            continue
        blockers = detect_blockers(ticket, now=now, sla_days=sla_days)
        reasons = [b.label for b in blockers]
        age = ticket_age_days(ticket, now)
        if normalized == Ticket.STATUS_UNASSIGNED and age >= 1:
            reasons.append("Unassigned")
        if normalized == Ticket.STATUS_AWAITING_DIAGNOSTICS and age >= 2:
            reasons.append("Awaiting diagnosis 2+ days")
        if normalized == Ticket.STATUS_AWAITING_QUOTE_APPROVAL and age >= 3:
            reasons.append("Awaiting quote response")
        if normalized == Ticket.STATUS_AWAITING_PARTS and age >= 5:
            reasons.append("Waiting on parts 5+ days")
        if reasons:
            attention_tickets.append({"ticket": ticket, "reasons": reasons})
    # Sort by number of reasons (most blocked first), limit to 10
    attention_tickets.sort(key=lambda x: len(x["reasons"]), reverse=True)
    attention_tickets = attention_tickets[:10]

    # All overdue tickets for dedicated widget
    overdue_tickets = [
        t for t in active_tickets
        if normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES
        and is_ticket_overdue(t, now, sla_days=sla_days)
    ]
    overdue_tickets.sort(key=lambda t: t.sla_target_at or t.created_at)

    technician_workload = {
        "assigned": sum(1 for t in active_tickets if t.assigned_technician_id and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
        "unassigned": metrics["unassigned"],
    }

    activity_items = _fetch_activity_items(limit=12)

    # Today's bookings
    todays_bookings = []
    try:
        if sa_inspect(db.engine).has_table("bookings"):
            from app.models import Booking
            day_start = datetime.combine(today, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            todays_bookings = Booking.query.filter(
                Booking.start_time >= day_start,
                Booking.start_time < day_end,
                Booking.status.notin_(["cancelled"]),
            ).order_by(Booking.start_time).all()
    except Exception:
        pass

    return render_template(
        "core/dashboard.html",
        stats=stats,
        metrics=metrics,
        recent_tickets=recent_tickets,
        attention_tickets=attention_tickets,
        overdue_tickets=overdue_tickets,
        technician_workload=technician_workload,
        activity_items=activity_items,
        todays_bookings=todays_bookings,
    )
