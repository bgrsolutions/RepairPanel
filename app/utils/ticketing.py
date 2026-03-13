from datetime import datetime, timedelta

from app.models.ticket import Ticket


STATUS_LABELS = {
    Ticket.STATUS_UNASSIGNED: "Unassigned",
    Ticket.STATUS_ASSIGNED: "Assigned",
    Ticket.STATUS_AWAITING_DIAGNOSTICS: "Awaiting Diagnostics",
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: "Awaiting Quote Approval",
    Ticket.STATUS_AWAITING_PARTS: "Awaiting Parts",
    Ticket.STATUS_IN_REPAIR: "In Repair",
    Ticket.STATUS_TESTING_QA: "Testing / QA",
    Ticket.STATUS_READY_FOR_COLLECTION: "Ready for Collection",
    Ticket.STATUS_COMPLETED: "Completed",
    Ticket.STATUS_CANCELLED: "Cancelled",
}

LEGACY_STATUS_MAP = {
    "new": Ticket.STATUS_UNASSIGNED,
    "awaiting diagnosis": Ticket.STATUS_AWAITING_DIAGNOSTICS,
    "awaiting quote approval": Ticket.STATUS_AWAITING_QUOTE_APPROVAL,
    "awaiting parts": Ticket.STATUS_AWAITING_PARTS,
    "in repair": Ticket.STATUS_IN_REPAIR,
    "testing / qa": Ticket.STATUS_TESTING_QA,
    "testing": Ticket.STATUS_TESTING_QA,
    "qa": Ticket.STATUS_TESTING_QA,
    "ready for collection": Ticket.STATUS_READY_FOR_COLLECTION,
    "collected": Ticket.STATUS_COMPLETED,
    "cancelled": Ticket.STATUS_CANCELLED,
}


def generate_ticket_number(branch_code: str, sequence: int) -> str:
    date_part = datetime.utcnow().strftime("%Y%m%d")
    return f"{branch_code}-{date_part}-{sequence:05d}"


def normalize_ticket_status(status: str | None) -> str:
    if not status:
        return Ticket.STATUS_UNASSIGNED
    cleaned = status.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in STATUS_LABELS:
        return cleaned
    return LEGACY_STATUS_MAP.get(status.strip().lower(), Ticket.STATUS_UNASSIGNED)


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(normalize_ticket_status(status), "Unassigned")


def is_ticket_overdue(ticket: Ticket, now: datetime | None = None) -> bool:
    current = now or datetime.utcnow()
    normalized = normalize_ticket_status(ticket.internal_status)
    if normalized in Ticket.CLOSED_STATUSES or not ticket.sla_target_at:
        return False
    return ticket.sla_target_at < current


def ticket_age_days(ticket: Ticket, now: datetime | None = None) -> int:
    current = now or datetime.utcnow()
    return max((current - ticket.created_at).days, 0)


def default_sla_target(created_at: datetime | None, sla_days: int) -> datetime:
    created = created_at or datetime.utcnow()
    return created + timedelta(days=max(sla_days, 1))
