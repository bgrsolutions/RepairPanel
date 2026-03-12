from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required

from app.models import Ticket


core_bp = Blueprint("core", __name__)


@core_bp.get("/")
@login_required
def dashboard():
    active_tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()

    now = datetime.utcnow()
    today = now.date()

    def is_overdue(ticket):
        return (now - ticket.created_at) > timedelta(days=5)

    stats = {
        "open_tickets": len(active_tickets),
        "awaiting_diagnosis": sum(1 for t in active_tickets if t.internal_status == "Awaiting Diagnosis"),
        "in_repair": sum(1 for t in active_tickets if t.internal_status == "In Repair"),
        "ready_for_collection": sum(1 for t in active_tickets if t.internal_status == "Ready for Collection"),
        "aging_tickets": sum(1 for t in active_tickets if is_overdue(t)),
        "new_today": sum(1 for t in active_tickets if t.created_at.date() == today),
    }

    recent_tickets = sorted(active_tickets, key=lambda t: t.created_at, reverse=True)[:6]
    attention_tickets = [
        t for t in active_tickets if t.priority in {"urgent", "high"} or t.internal_status in {"Awaiting Diagnosis", "On Hold"}
    ][:6]

    # Placeholder visual metric for Phase 2+ planning.
    technician_workload = {
        "assigned": sum(1 for t in active_tickets if t.assigned_technician_id),
        "unassigned": sum(1 for t in active_tickets if not t.assigned_technician_id),
    }

    return render_template(
        "core/dashboard.html",
        stats=stats,
        recent_tickets=recent_tickets,
        attention_tickets=attention_tickets,
        technician_workload=technician_workload,
    )
