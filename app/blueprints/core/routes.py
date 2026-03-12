from datetime import datetime

from flask import Blueprint, render_template
from flask_login import login_required

from app.models import Ticket
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status, ticket_age_days


core_bp = Blueprint("core", __name__)


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
        "overdue_tickets": sum(1 for t in active_tickets if is_ticket_overdue(t, now)),
        "new_today": sum(1 for t in active_tickets if t.created_at.date() == today),
    }

    recent_tickets = sorted(active_tickets, key=lambda t: t.created_at, reverse=True)[:6]
    attention_tickets = [
        t
        for t in active_tickets
        if t.priority in {"urgent", "high"} or is_ticket_overdue(t, now) or normalize_ticket_status(t.internal_status) in {Ticket.STATUS_UNASSIGNED, Ticket.STATUS_AWAITING_DIAGNOSTICS}
    ][:6]

    technician_workload = {
        "assigned": sum(1 for t in active_tickets if t.assigned_technician_id and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
        "unassigned": sum(1 for t in active_tickets if not t.assigned_technician_id and normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES),
    }

    return render_template(
        "core/dashboard.html",
        stats=stats,
        recent_tickets=recent_tickets,
        attention_tickets=attention_tickets,
        technician_workload=technician_workload,
    )
