from datetime import datetime, timedelta

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from app.models import PartOrder, Quote, StockReservation, Ticket
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _label(status: str) -> str:
    return status.replace("_", " ").title()


@reports_bp.get("/")
@login_required
def kpi_dashboard():
    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
    statuses = {}
    by_branch = {}
    workload = {}

    for t in tickets:
        normalized = normalize_ticket_status(t.internal_status)
        statuses[_label(normalized)] = statuses.get(_label(normalized), 0) + 1
        branch_name = t.branch.name if t.branch else "Unknown"
        by_branch[branch_name] = by_branch.get(branch_name, 0) + 1
        owner = t.assigned_technician.full_name if t.assigned_technician else "Unassigned"
        workload[owner] = workload.get(owner, 0) + 1

    now = datetime.utcnow()
    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)
    overdue = [t for t in tickets if is_ticket_overdue(t, now, sla_days=sla_days)]

    usage = {}
    for r in StockReservation.query.all():
        key = r.part.sku if r.part else str(r.part_id)
        usage[key] = usage.get(key, 0) + float(r.quantity)
    most_used = sorted(usage.items(), key=lambda item: item[1], reverse=True)[:5]

    awaiting_arrival = (
        PartOrder.query.filter(PartOrder.status.in_(["ordered", "shipped", "partially_received"]))
        .order_by(PartOrder.created_at.desc())
        .all()
    )

    sent_quotes = Quote.query.filter(Quote.status.in_(["sent", "approved", "declined"]))
    sent_count = sent_quotes.count()
    approved_count = sent_quotes.filter(Quote.status == "approved").count()
    quote_approval_rate = (approved_count / sent_count * 100) if sent_count else 0.0

    finished = [t for t in tickets if normalize_ticket_status(t.internal_status) in {Ticket.STATUS_COMPLETED, Ticket.STATUS_READY_FOR_COLLECTION}]
    avg_turnaround_days = 0.0
    if finished:
        durations = []
        for t in finished:
            end_at = t.updated_at or t.created_at
            durations.append(max((end_at - t.created_at).total_seconds() / 86400, 0))
        avg_turnaround_days = sum(durations) / len(durations)

    kpis = {
        "awaiting_diagnosis": statuses.get("Awaiting Diagnostics", 0),
        "awaiting_quote_approval": statuses.get("Awaiting Quote Approval", 0),
        "awaiting_parts": statuses.get("Awaiting Parts", 0),
        "in_repair": statuses.get("In Repair", 0),
        "ready_for_collection": statuses.get("Ready For Collection", 0),
        "overdue": len(overdue),
        "quote_approval_rate": quote_approval_rate,
        "average_turnaround_days": avg_turnaround_days,
    }

    return render_template(
        "reports/dashboard.html",
        statuses=statuses,
        by_branch=by_branch,
        kpis=kpis,
        workload=workload,
        most_used=most_used,
        awaiting_arrival=awaiting_arrival,
    )
