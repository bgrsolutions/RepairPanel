"""Phase 8 — Workshop workflow service.

Provides:
- Formal status transition validation
- Blocker detection (quote, parts, checklist, SLA)
- Next-step recommendation engine
- Workshop metrics helpers
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.ticket import Ticket

# ---------------------------------------------------------------------------
# Allowed transitions map
# Each key is a *from* status, value is the set of valid *to* statuses.
# ---------------------------------------------------------------------------
VALID_TRANSITIONS: dict[str, set[str]] = {
    Ticket.STATUS_UNASSIGNED: {
        Ticket.STATUS_ASSIGNED,
        Ticket.STATUS_AWAITING_DIAGNOSTICS,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_ASSIGNED: {
        Ticket.STATUS_UNASSIGNED,
        Ticket.STATUS_AWAITING_DIAGNOSTICS,
        Ticket.STATUS_IN_REPAIR,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_AWAITING_DIAGNOSTICS: {
        Ticket.STATUS_AWAITING_QUOTE_APPROVAL,
        Ticket.STATUS_IN_REPAIR,
        Ticket.STATUS_AWAITING_PARTS,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: {
        Ticket.STATUS_AWAITING_PARTS,
        Ticket.STATUS_IN_REPAIR,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_AWAITING_PARTS: {
        Ticket.STATUS_IN_REPAIR,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_IN_REPAIR: {
        Ticket.STATUS_TESTING_QA,
        Ticket.STATUS_AWAITING_PARTS,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_TESTING_QA: {
        Ticket.STATUS_IN_REPAIR,
        Ticket.STATUS_READY_FOR_COLLECTION,
        Ticket.STATUS_CANCELLED,
    },
    Ticket.STATUS_READY_FOR_COLLECTION: {
        Ticket.STATUS_COMPLETED,
        Ticket.STATUS_IN_REPAIR,
    },
    Ticket.STATUS_COMPLETED: {
        Ticket.STATUS_ARCHIVED,
    },
    Ticket.STATUS_CANCELLED: {
        Ticket.STATUS_ARCHIVED,
    },
    Ticket.STATUS_ARCHIVED: set(),
}

# ---------------------------------------------------------------------------
# Transition validation
# ---------------------------------------------------------------------------

def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Return True if the transition is permitted."""
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def allowed_transitions(from_status: str) -> list[str]:
    """Return the list of statuses reachable from *from_status*."""
    return sorted(VALID_TRANSITIONS.get(from_status, set()))


# ---------------------------------------------------------------------------
# Blocker detection
# ---------------------------------------------------------------------------

class Blocker:
    """Represents a single blocker on a ticket."""

    __slots__ = ("kind", "label", "detail")

    def __init__(self, kind: str, label: str, detail: str = ""):
        self.kind = kind      # quote | parts | checklist | sla
        self.label = label    # short badge text
        self.detail = detail  # longer explanation

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "label": self.label, "detail": self.detail}


def detect_blockers(
    ticket: Ticket,
    *,
    now: datetime | None = None,
    sla_days: int = 5,
) -> list[Blocker]:
    """Detect all blockers on *ticket*.

    This function is safe to call from templates and services.  It avoids
    lazy-load issues by importing models inside and running queries only
    when the ticket is in a state where the check is relevant.
    """
    from app.models import PartOrder, Quote, RepairChecklist
    from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status

    current = now or datetime.utcnow()
    status = normalize_ticket_status(ticket.internal_status)
    blockers: list[Blocker] = []

    if status in Ticket.CLOSED_STATUSES:
        return blockers

    # --- Quote blocker: unapproved quote exists ---
    try:
        quotes = Quote.query.filter_by(ticket_id=ticket.id).all()
        has_sent_or_draft = any(q.status in ("draft", "sent") for q in quotes)
        has_approved = any(q.status == "approved" for q in quotes)
        if has_sent_or_draft and not has_approved:
            pending = [q for q in quotes if q.status == "sent"]
            if pending:
                blockers.append(Blocker(
                    "quote", "WAITING QUOTE",
                    f"Quote v{pending[0].version} sent but not yet approved",
                ))
            elif any(q.status == "draft" for q in quotes):
                blockers.append(Blocker(
                    "quote", "QUOTE DRAFT",
                    "Draft quote exists but has not been sent to customer",
                ))
    except Exception:
        pass

    # --- Parts blocker: open part orders not yet received ---
    try:
        orders = PartOrder.query.filter(
            PartOrder.ticket_id == ticket.id,
            PartOrder.status.notin_(["received", "cancelled"]),
        ).all()
        if orders:
            overdue_orders = [
                o for o in orders
                if o.estimated_arrival_at and o.estimated_arrival_at < current
            ]
            if overdue_orders:
                ref = overdue_orders[0].reference or str(overdue_orders[0].id)[:8]
                blockers.append(Blocker(
                    "parts", "PARTS OVERDUE",
                    f"Part order {ref} past estimated arrival",
                ))
            else:
                ref = orders[0].reference or str(orders[0].id)[:8]
                eta_str = ""
                etas = [o.estimated_arrival_at for o in orders if o.estimated_arrival_at]
                if etas:
                    eta_str = f" (ETA: {min(etas).strftime('%Y-%m-%d')})"
                blockers.append(Blocker(
                    "parts", "WAITING PARTS",
                    f"Part order {ref} not yet received{eta_str}",
                ))
    except Exception:
        pass

    # --- Checklist blocker: post-repair checklist incomplete ---
    try:
        post_checklists = RepairChecklist.query.filter_by(
            ticket_id=ticket.id, checklist_type="post_repair"
        ).all()
        if status in (Ticket.STATUS_TESTING_QA, Ticket.STATUS_READY_FOR_COLLECTION):
            if not post_checklists or not any(cl.is_complete for cl in post_checklists):
                blockers.append(Blocker(
                    "checklist", "CHECKLIST INCOMPLETE",
                    "Post-repair checklist must be completed before collection",
                ))
    except Exception:
        pass

    # --- SLA blocker ---
    if is_ticket_overdue(ticket, current, sla_days=sla_days):
        blockers.append(Blocker(
            "sla", "OVERDUE",
            "Past SLA target date",
        ))

    return blockers


# ---------------------------------------------------------------------------
# Next recommended action
# ---------------------------------------------------------------------------

_NEXT_ACTION: dict[str, str] = {
    Ticket.STATUS_UNASSIGNED: "Assign a technician to begin work",
    Ticket.STATUS_ASSIGNED: "Start diagnosis or begin repair",
    Ticket.STATUS_AWAITING_DIAGNOSTICS: "Complete device diagnosis and create quote",
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: "Follow up with customer on quote approval",
    Ticket.STATUS_AWAITING_PARTS: "Check part order status and receive parts",
    Ticket.STATUS_IN_REPAIR: "Complete repair and run post-repair checklist",
    Ticket.STATUS_TESTING_QA: "Finish QA testing and mark ready for collection",
    Ticket.STATUS_READY_FOR_COLLECTION: "Contact customer for device pickup",
    Ticket.STATUS_COMPLETED: "Archive ticket when paperwork is finalised",
    Ticket.STATUS_CANCELLED: "Archive ticket",
}


def next_recommended_action(ticket: Ticket, blockers: list[Blocker] | None = None) -> str:
    """Return a human-friendly string describing the next step for *ticket*."""
    from app.utils.ticketing import normalize_ticket_status

    status = normalize_ticket_status(ticket.internal_status)

    # If there are blockers, the most important blocker drives the recommendation
    if blockers:
        for b in blockers:
            if b.kind == "parts":
                return f"Receive outstanding parts — {b.detail}"
            if b.kind == "quote":
                return f"Resolve quote — {b.detail}"
            if b.kind == "checklist":
                return "Complete the post-repair checklist"
            if b.kind == "sla":
                return "Ticket is overdue — escalate or expedite"

    return _NEXT_ACTION.get(status, "Review ticket and take next appropriate action")


# ---------------------------------------------------------------------------
# Workshop metrics (counts)
# ---------------------------------------------------------------------------

def workshop_metrics(
    tickets: list[Ticket],
    *,
    now: datetime | None = None,
    sla_days: int = 5,
) -> dict[str, int]:
    """Compute operational metrics from a list of active tickets."""
    from app.utils.ticketing import is_ticket_overdue, normalize_ticket_status

    current = now or datetime.utcnow()
    m: dict[str, int] = {
        "in_diagnosis": 0,
        "awaiting_quote": 0,
        "awaiting_parts": 0,
        "in_repair": 0,
        "in_testing": 0,
        "ready_for_collection": 0,
        "overdue": 0,
        "unassigned": 0,
    }
    for t in tickets:
        s = normalize_ticket_status(t.internal_status)
        if s in Ticket.CLOSED_STATUSES:
            continue
        if s == Ticket.STATUS_AWAITING_DIAGNOSTICS:
            m["in_diagnosis"] += 1
        elif s == Ticket.STATUS_AWAITING_QUOTE_APPROVAL:
            m["awaiting_quote"] += 1
        elif s == Ticket.STATUS_AWAITING_PARTS:
            m["awaiting_parts"] += 1
        elif s == Ticket.STATUS_IN_REPAIR:
            m["in_repair"] += 1
        elif s == Ticket.STATUS_TESTING_QA:
            m["in_testing"] += 1
        elif s == Ticket.STATUS_READY_FOR_COLLECTION:
            m["ready_for_collection"] += 1
        if s in (Ticket.STATUS_UNASSIGNED,):
            m["unassigned"] += 1
        if is_ticket_overdue(t, current, sla_days=sla_days):
            m["overdue"] += 1
    return m
