"""Phase 14 — Reporting, KPIs & Management Dashboards routes.

All routes require login + can_view_reports (Management roles only).
"""
from datetime import datetime

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from app.models import Branch, PartOrder, Ticket, User
from app.services.permission_service import can_view_reports
from app.services.reporting_service import (
    _apply_ticket_filters,
    _parse_date_range,
    communication_report,
    get_filter_options,
    inventory_report,
    management_overview,
    quote_report,
    technician_workload,
    ticket_throughput,
)
from app.utils.permissions import permission_required
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _get_filters():
    """Extract common filter params from request args."""
    date_range = request.args.get("date_range", "")
    branch_id = request.args.get("branch_id", "")
    technician_id = request.args.get("technician_id", "")
    now = datetime.utcnow()
    date_start, date_end = _parse_date_range(date_range or None, now)
    return {
        "date_range": date_range,
        "branch_id": branch_id,
        "technician_id": technician_id,
        "date_start": date_start,
        "date_end": date_end,
        "now": now,
    }


def _label(status: str) -> str:
    return status.replace("_", " ").title()


@reports_bp.get("/")
@login_required
@permission_required(can_view_reports)
def kpi_dashboard():
    """Management dashboard — comprehensive KPI overview."""
    f = _get_filters()
    now = f["now"]
    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)

    tickets = Ticket.query.filter(
        Ticket.deleted_at.is_(None),
        Ticket.internal_status != Ticket.STATUS_ARCHIVED,
    ).all()
    tickets = _apply_ticket_filters(
        tickets,
        branch_id=f["branch_id"] or None,
        technician_id=f["technician_id"] or None,
        date_start=f["date_start"],
        date_end=f["date_end"],
    )

    overview = management_overview(tickets, now=now, sla_days=sla_days)
    throughput = ticket_throughput(tickets, now=now, sla_days=sla_days)
    workload = technician_workload(tickets, now=now, sla_days=sla_days)
    quotes = quote_report(date_start=f["date_start"], date_end=f["date_end"])
    inventory = inventory_report(date_start=f["date_start"], date_end=f["date_end"])
    comms = communication_report(now=now)

    # Awaiting arrival orders (for existing section)
    awaiting_arrival = (
        PartOrder.query.filter(PartOrder.status.in_(["ordered", "shipped", "partially_received"]))
        .order_by(PartOrder.created_at.desc())
        .limit(10)
        .all()
    )

    filter_options = get_filter_options()

    return render_template(
        "reports/dashboard.html",
        overview=overview,
        throughput=throughput,
        workload=workload,
        quotes=quotes,
        inventory=inventory,
        comms=comms,
        awaiting_arrival=awaiting_arrival,
        filters=f,
        branches=filter_options["branches"],
        technicians=filter_options["technicians"],
    )


@reports_bp.get("/technician-workload")
@login_required
@permission_required(can_view_reports)
def technician_workload_detail():
    """Detailed technician workload breakdown."""
    f = _get_filters()
    now = f["now"]
    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)

    tickets = Ticket.query.filter(
        Ticket.deleted_at.is_(None),
        Ticket.internal_status != Ticket.STATUS_ARCHIVED,
    ).all()
    tickets = _apply_ticket_filters(
        tickets,
        branch_id=f["branch_id"] or None,
        technician_id=f["technician_id"] or None,
        date_start=f["date_start"],
        date_end=f["date_end"],
    )

    workload = technician_workload(tickets, now=now, sla_days=sla_days)
    filter_options = get_filter_options()

    return render_template(
        "reports/technician_workload.html",
        workload=workload,
        filters=f,
        branches=filter_options["branches"],
        technicians=filter_options["technicians"],
    )


@reports_bp.get("/quotes")
@login_required
@permission_required(can_view_reports)
def quote_reporting():
    """Quote pipeline health reporting."""
    f = _get_filters()
    quotes = quote_report(date_start=f["date_start"], date_end=f["date_end"])
    filter_options = get_filter_options()

    return render_template(
        "reports/quotes.html",
        quotes=quotes,
        filters=f,
        branches=filter_options["branches"],
        technicians=filter_options["technicians"],
    )


@reports_bp.get("/inventory")
@login_required
@permission_required(can_view_reports)
def inventory_reporting():
    """Inventory and parts usage reporting."""
    f = _get_filters()
    inventory = inventory_report(date_start=f["date_start"], date_end=f["date_end"])

    awaiting_arrival = (
        PartOrder.query.filter(PartOrder.status.in_(["ordered", "shipped", "partially_received"]))
        .order_by(PartOrder.created_at.desc())
        .limit(10)
        .all()
    )

    filter_options = get_filter_options()

    return render_template(
        "reports/inventory.html",
        inventory=inventory,
        awaiting_arrival=awaiting_arrival,
        filters=f,
        branches=filter_options["branches"],
        technicians=filter_options["technicians"],
    )
