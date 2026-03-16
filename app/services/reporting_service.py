"""Phase 14 — Reporting, KPIs & Management Dashboards service.

Centralised query/aggregation layer for all management reporting.
Keeps route handlers thin and logic testable.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.extensions import db
from app.models import (
    AuditLog, Branch, PartOrder, PortalToken, Quote, StockReservation, Ticket, User,
)
from app.models.ticket import Ticket
from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status


# ---------------------------------------------------------------------------
# Date-range helpers
# ---------------------------------------------------------------------------

def _parse_date_range(date_range: str | None, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    """Return (start, end) datetimes from a named range string."""
    current = now or datetime.utcnow()
    if not date_range:
        return None, None
    if date_range == "today":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, current
    if date_range == "last_7_days":
        return current - timedelta(days=7), current
    if date_range == "last_30_days":
        return current - timedelta(days=30), current
    if date_range == "this_month":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, current
    if date_range == "last_month":
        first_this = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_this - timedelta(seconds=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end
    return None, None


def _apply_ticket_filters(
    tickets: list[Ticket],
    *,
    branch_id: str | None = None,
    technician_id: str | None = None,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
) -> list[Ticket]:
    """Filter a ticket list in-memory by branch, technician, and date range."""
    result = tickets
    if branch_id:
        result = [t for t in result if str(t.branch_id) == branch_id]
    if technician_id:
        result = [t for t in result if str(t.assigned_technician_id or "") == technician_id]
    if date_start:
        result = [t for t in result if t.created_at >= date_start]
    if date_end:
        result = [t for t in result if t.created_at <= date_end]
    return result


# ---------------------------------------------------------------------------
# Feature 1: Management Overview Metrics
# ---------------------------------------------------------------------------

def management_overview(
    tickets: list[Ticket],
    *,
    now: datetime | None = None,
    sla_days: int = 5,
) -> dict[str, Any]:
    """Top-level management tiles: open, overdue, created/completed today, etc."""
    current = now or datetime.utcnow()
    today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)

    open_tickets = [t for t in tickets if normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES]
    overdue = [t for t in open_tickets if is_ticket_overdue(t, current, sla_days=sla_days)]
    created_today = [t for t in tickets if t.created_at >= today_start]
    completed_today = [
        t for t in tickets
        if normalize_ticket_status(t.internal_status) == Ticket.STATUS_COMPLETED
        and t.updated_at and t.updated_at >= today_start
    ]
    unassigned = [
        t for t in open_tickets
        if normalize_ticket_status(t.internal_status) == Ticket.STATUS_UNASSIGNED
    ]

    return {
        "total_open": len(open_tickets),
        "overdue": len(overdue),
        "created_today": len(created_today),
        "completed_today": len(completed_today),
        "unassigned": len(unassigned),
    }


# ---------------------------------------------------------------------------
# Feature 2: Technician Workload
# ---------------------------------------------------------------------------

def technician_workload(
    tickets: list[Ticket],
    *,
    now: datetime | None = None,
    sla_days: int = 5,
) -> list[dict[str, Any]]:
    """Per-technician breakdown: assigned, in-repair, overdue, completed."""
    current = now or datetime.utcnow()
    by_tech: dict[str, dict[str, Any]] = {}

    for t in tickets:
        status = normalize_ticket_status(t.internal_status)
        tech_name = t.assigned_technician.full_name if t.assigned_technician else "Unassigned"
        tech_id = str(t.assigned_technician_id) if t.assigned_technician_id else None

        if tech_name not in by_tech:
            by_tech[tech_name] = {
                "technician_name": tech_name,
                "technician_id": tech_id,
                "assigned": 0,
                "in_repair": 0,
                "overdue": 0,
                "completed": 0,
                "total": 0,
            }
        entry = by_tech[tech_name]
        entry["total"] += 1

        if status in Ticket.ACTIVE_STATUSES:
            entry["assigned"] += 1
        if status == Ticket.STATUS_IN_REPAIR:
            entry["in_repair"] += 1
        if status == Ticket.STATUS_COMPLETED:
            entry["completed"] += 1
        if status not in Ticket.CLOSED_STATUSES and is_ticket_overdue(t, current, sla_days=sla_days):
            entry["overdue"] += 1

    return sorted(by_tech.values(), key=lambda x: x["assigned"], reverse=True)


# ---------------------------------------------------------------------------
# Feature 3: Ticket Throughput / Lifecycle KPIs
# ---------------------------------------------------------------------------

def ticket_throughput(
    tickets: list[Ticket],
    *,
    now: datetime | None = None,
    sla_days: int = 5,
) -> dict[str, Any]:
    """Ticket lifecycle metrics: avg age, throughput, stalled count."""
    current = now or datetime.utcnow()
    today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = current - timedelta(days=7)

    open_tickets = [t for t in tickets if normalize_ticket_status(t.internal_status) not in Ticket.CLOSED_STATUSES]

    # Average age of open tickets (days)
    ages = [max((current - t.created_at).total_seconds() / 86400, 0) for t in open_tickets]
    avg_age_days = sum(ages) / len(ages) if ages else 0.0

    # Created / completed counts
    created_today = len([t for t in tickets if t.created_at >= today_start])
    created_this_week = len([t for t in tickets if t.created_at >= week_start])
    completed_tickets = [
        t for t in tickets
        if normalize_ticket_status(t.internal_status) in {Ticket.STATUS_COMPLETED, Ticket.STATUS_READY_FOR_COLLECTION}
    ]
    completed_this_week = len([
        t for t in completed_tickets
        if t.updated_at and t.updated_at >= week_start
    ])

    # Average turnaround (completed only)
    turnaround_days = []
    for t in completed_tickets:
        end_at = t.updated_at or t.created_at
        turnaround_days.append(max((end_at - t.created_at).total_seconds() / 86400, 0))
    avg_turnaround = sum(turnaround_days) / len(turnaround_days) if turnaround_days else 0.0

    # Stalled: open tickets with no update in 3+ days
    stalled = [
        t for t in open_tickets
        if t.updated_at and (current - t.updated_at).total_seconds() > 3 * 86400
    ]

    # Status breakdown
    status_counts: dict[str, int] = {}
    for t in tickets:
        s = normalize_ticket_status(t.internal_status)
        label = s.replace("_", " ").title()
        status_counts[label] = status_counts.get(label, 0) + 1

    return {
        "avg_age_days": avg_age_days,
        "avg_turnaround_days": avg_turnaround,
        "created_today": created_today,
        "created_this_week": created_this_week,
        "completed_this_week": completed_this_week,
        "stalled_count": len(stalled),
        "status_counts": status_counts,
    }


# ---------------------------------------------------------------------------
# Feature 4: Quotes & Approval Reporting
# ---------------------------------------------------------------------------

def quote_report(
    *,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
) -> dict[str, Any]:
    """Quote pipeline health: counts by status, approval rate, avg time-to-approve."""
    q = Quote.query
    if date_start:
        q = q.filter(Quote.created_at >= date_start)
    if date_end:
        q = q.filter(Quote.created_at <= date_end)
    quotes = q.all()

    by_status: dict[str, int] = {}
    approved_count = 0
    sent_or_decided = 0
    time_to_approve_days: list[float] = []

    for quote in quotes:
        by_status[quote.status] = by_status.get(quote.status, 0) + 1
        if quote.status in ("sent", "approved", "declined"):
            sent_or_decided += 1
        if quote.status == "approved":
            approved_count += 1
            # Measure time from sent to approval
            for approval in (quote.approvals or []):
                if approval.status == "approved" and approval.approved_at and quote.sent_at:
                    delta = (approval.approved_at - quote.sent_at).total_seconds() / 86400
                    time_to_approve_days.append(max(delta, 0))

    approval_rate = (approved_count / sent_or_decided * 100) if sent_or_decided else 0.0
    avg_time_to_approve = sum(time_to_approve_days) / len(time_to_approve_days) if time_to_approve_days else 0.0

    return {
        "total_quotes": len(quotes),
        "by_status": by_status,
        "approval_rate": approval_rate,
        "avg_time_to_approve_days": avg_time_to_approve,
    }


# ---------------------------------------------------------------------------
# Feature 5: Inventory / Parts Usage
# ---------------------------------------------------------------------------

def inventory_report(
    *,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
) -> dict[str, Any]:
    """Parts usage, reservations, low-stock, pending orders."""
    from app.models import Part, StockLevel

    # Most-used parts (by reservation quantity)
    res_q = StockReservation.query
    if date_start:
        res_q = res_q.filter(StockReservation.created_at >= date_start)
    if date_end:
        res_q = res_q.filter(StockReservation.created_at <= date_end)
    reservations = res_q.all()

    usage: dict[str, float] = {}
    usage_names: dict[str, str] = {}
    consumed_count = 0
    reserved_count = 0
    for r in reservations:
        key = r.part.sku if r.part else str(r.part_id)
        name = r.part.name if r.part else key
        usage[key] = usage.get(key, 0) + float(r.quantity)
        usage_names[key] = name
        if r.status == "consumed":
            consumed_count += 1
        elif r.status == "reserved":
            reserved_count += 1

    most_used = [
        {"sku": sku, "name": usage_names.get(sku, sku), "quantity": qty}
        for sku, qty in sorted(usage.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    # Low stock parts
    low_stock_parts = []
    try:
        parts = Part.query.filter(Part.deleted_at.is_(None), Part.is_active.is_(True)).all()
        for part in parts:
            threshold = part.low_stock_threshold or 3
            levels = StockLevel.query.filter_by(part_id=part.id).all()
            total_on_hand = sum(float(sl.on_hand_qty) for sl in levels)
            if total_on_hand <= threshold:
                low_stock_parts.append({
                    "sku": part.sku,
                    "name": part.name,
                    "on_hand": total_on_hand,
                    "threshold": threshold,
                })
    except Exception:
        pass

    # Pending orders
    pending_orders = PartOrder.query.filter(
        PartOrder.status.in_(["ordered", "shipped", "partially_received"])
    ).count()

    return {
        "most_used": most_used,
        "consumed_count": consumed_count,
        "reserved_count": reserved_count,
        "low_stock_parts": low_stock_parts[:10],
        "pending_orders": pending_orders,
    }


# ---------------------------------------------------------------------------
# Feature 6: Customer Communication / Portal
# ---------------------------------------------------------------------------

def communication_report(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Portal token and communication activity metrics."""
    current = now or datetime.utcnow()

    active_tokens = 0
    total_tokens = 0
    expired_tokens = 0
    comm_actions = 0

    try:
        active_tokens = PortalToken.query.filter(
            PortalToken.used_at.is_(None),
            db.or_(
                PortalToken.expires_at.is_(None),
                PortalToken.expires_at > current,
            ),
        ).count()
        total_tokens = PortalToken.query.count()
        expired_tokens = PortalToken.query.filter(
            PortalToken.expires_at.isnot(None),
            PortalToken.expires_at <= current,
        ).count()
    except Exception:
        pass

    try:
        thirty_days_ago = current - timedelta(days=30)
        comm_actions = AuditLog.query.filter(
            AuditLog.action.in_(["customer_message_generated", "communication_logged", "portal_token_regenerated", "portal_token_revoked"]),
            AuditLog.created_at >= thirty_days_ago,
        ).count()
    except Exception:
        pass

    return {
        "active_tokens": active_tokens,
        "total_tokens": total_tokens,
        "expired_tokens": expired_tokens,
        "communication_actions_30d": comm_actions,
    }


# ---------------------------------------------------------------------------
# Convenience: collect all filter options
# ---------------------------------------------------------------------------

def get_filter_options() -> dict[str, Any]:
    """Return branches and technicians for filter dropdowns."""
    branches = Branch.query.order_by(Branch.name).all()
    technicians = User.query.filter(User.is_active.is_(True)).order_by(User.full_name).all()
    return {
        "branches": branches,
        "technicians": technicians,
    }
