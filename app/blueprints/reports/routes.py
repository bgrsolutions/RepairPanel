from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required

from app.models import PartOrder, StockReservation, Ticket


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.get("/")
@login_required
def kpi_dashboard():
    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
    statuses = {}
    by_branch = {}
    workload = {}

    for t in tickets:
        statuses[t.internal_status] = statuses.get(t.internal_status, 0) + 1
        branch_key = t.branch.code if t.branch else "UNKNOWN"
        by_branch[branch_key] = by_branch.get(branch_key, 0) + 1
        owner = t.assigned_technician.full_name if t.assigned_technician else "Unassigned"
        workload[owner] = workload.get(owner, 0) + 1

    now = datetime.utcnow()
    aging = [t for t in tickets if (now - t.created_at) > timedelta(days=7)]

    usage = {}
    for r in StockReservation.query.all():
        key = r.part.sku if r.part else str(r.part_id)
        usage[key] = usage.get(key, 0) + float(r.quantity)
    most_used = sorted(usage.items(), key=lambda item: item[1], reverse=True)[:5]

    awaiting_arrival = (
        PartOrder.query.filter(PartOrder.status.in_(["ordered", "shipped", "delayed", "partially_arrived"]))
        .order_by(PartOrder.created_at.desc())
        .all()
    )

    kpis = {
        "awaiting_diagnosis": statuses.get("Awaiting Diagnosis", 0),
        "awaiting_quote_approval": statuses.get("Awaiting Quote Approval", 0),
        "awaiting_parts": statuses.get("Awaiting Parts", 0),
        "in_repair": statuses.get("In Repair", 0),
        "ready_for_collection": statuses.get("Ready for Collection", 0),
        "overdue": len(aging),
        "quote_approval_rate_placeholder": "--",
        "average_turnaround_placeholder": "--",
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
