"""Booking service — lifecycle management and operational helpers.

Centralizes booking status transitions, intake queue queries,
and the assisted conversion-to-ticket flow.
"""
from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import datetime, timedelta

from flask_babel import gettext as _

from app.extensions import db
from app.models import Booking, Branch, Customer, Device, Ticket, TicketNote, PortalToken, RepairService
from app.services.audit_service import log_action


# ---------------------------------------------------------------------------
# Status transition labels (for display)
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    Booking.STATUS_NEW: "New",
    Booking.STATUS_CONFIRMED: "Confirmed",
    Booking.STATUS_ARRIVED: "Arrived",
    Booking.STATUS_NO_SHOW: "No Show",
    Booking.STATUS_CONVERTED: "Converted",
    Booking.STATUS_CANCELLED: "Cancelled",
}


def status_label(status: str) -> str:
    """Return a translatable display label for a booking status."""
    labels = {
        Booking.STATUS_NEW: _("New"),
        Booking.STATUS_CONFIRMED: _("Confirmed"),
        Booking.STATUS_ARRIVED: _("Arrived"),
        Booking.STATUS_NO_SHOW: _("No Show"),
        Booking.STATUS_CONVERTED: _("Converted"),
        Booking.STATUS_CANCELLED: _("Cancelled"),
        # Legacy
        Booking.STATUS_SCHEDULED: _("Scheduled"),
        Booking.STATUS_IN_PROGRESS: _("In Progress"),
        Booking.STATUS_COMPLETED: _("Completed"),
    }
    return labels.get(status, status.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """Raised when a booking status transition is not allowed."""
    pass


def transition_status(booking: Booking, new_status: str, user_id: str | None = None) -> Booking:
    """Transition a booking to a new status, with validation.

    Raises InvalidTransitionError if the transition is not allowed.
    """
    if not booking.can_transition_to(new_status):
        raise InvalidTransitionError(
            f"Cannot transition from '{booking.status}' to '{new_status}'"
        )
    old_status = booking.status
    booking.status = new_status
    db.session.flush()
    try:
        log_action(
            "booking.status_change",
            "Booking",
            str(booking.id),
            details={"old_status": old_status, "new_status": new_status},
        )
    except Exception:
        pass  # audit logging should not break business logic
    return booking


# ---------------------------------------------------------------------------
# Intake queue queries
# ---------------------------------------------------------------------------

def _to_uuid(value):
    """Convert a string to UUID if needed."""
    if value is None:
        return None
    if isinstance(value, _uuid.UUID):
        return value
    return _uuid.UUID(str(value))


def get_todays_bookings(location_id: str | None = None) -> list[Booking]:
    """Return today's bookings ordered by start_time."""
    today = datetime.utcnow().date()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    q = Booking.query.filter(
        Booking.start_time >= day_start,
        Booking.start_time < day_end,
    )
    if location_id:
        q = q.filter(Booking.location_id == _to_uuid(location_id))
    return q.order_by(Booking.start_time).all()


def get_upcoming_bookings(days: int = 7, location_id: str | None = None) -> list[Booking]:
    """Return upcoming bookings for the next N days (excluding today)."""
    today = datetime.utcnow().date()
    tomorrow_start = datetime.combine(today + timedelta(days=1), datetime.min.time())
    end_date = datetime.combine(today + timedelta(days=days + 1), datetime.min.time())
    q = Booking.query.filter(
        Booking.start_time >= tomorrow_start,
        Booking.start_time < end_date,
    )
    if location_id:
        q = q.filter(Booking.location_id == _to_uuid(location_id))
    return q.order_by(Booking.start_time).all()


def get_overdue_bookings(location_id: str | None = None) -> list[Booking]:
    """Return past bookings that are still in active (non-terminal) statuses."""
    today = datetime.utcnow().date()
    day_start = datetime.combine(today, datetime.min.time())
    q = Booking.query.filter(
        Booking.start_time < day_start,
        Booking.status.in_(list(Booking.ACTIVE_STATUSES)),
    )
    if location_id:
        q = q.filter(Booking.location_id == _to_uuid(location_id))
    return q.order_by(Booking.start_time.desc()).all()


def get_intake_queue(
    location_id: str | None = None,
    status_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Build the intake queue data: today, upcoming, overdue bookings."""
    result = {
        "today": get_todays_bookings(location_id),
        "upcoming": get_upcoming_bookings(7, location_id),
        "overdue": get_overdue_bookings(location_id),
    }
    if status_filter:
        for key in result:
            result[key] = [b for b in result[key] if b.status == status_filter]
    return result


# ---------------------------------------------------------------------------
# Booking count for reporting/dashboard compatibility
# ---------------------------------------------------------------------------

def get_booking_counts() -> dict:
    """Return booking counts for dashboard/reporting."""
    today = datetime.utcnow().date()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    today_total = Booking.query.filter(
        Booking.start_time >= day_start, Booking.start_time < day_end
    ).count()
    today_arrived = Booking.query.filter(
        Booking.start_time >= day_start, Booking.start_time < day_end,
        Booking.status == Booking.STATUS_ARRIVED,
    ).count()
    overdue = Booking.query.filter(
        Booking.start_time < day_start,
        Booking.status.in_(list(Booking.ACTIVE_STATUSES)),
    ).count()

    return {
        "today_total": today_total,
        "today_arrived": today_arrived,
        "overdue": overdue,
    }


# ---------------------------------------------------------------------------
# Assisted conversion: Booking → Ticket
# ---------------------------------------------------------------------------

def convert_booking_to_ticket(
    booking: Booking,
    branch_code: str,
    user_id: str,
    ticket_number: str,
    issue_summary: str | None = None,
    device_condition: str | None = None,
    accessories: str | None = None,
) -> Ticket:
    """Convert a booking into a repair ticket.

    This is a transaction-safe operation:
    - Creates the ticket from booking data
    - Sets booking status to converted
    - Links the ticket back to the booking

    Raises InvalidTransitionError if booking cannot be converted.
    Raises ValueError if booking has already been converted.
    """
    if booking.converted_ticket_id is not None:
        raise ValueError("Booking has already been converted to a ticket")

    if not booking.can_transition_to(Booking.STATUS_CONVERTED):
        raise InvalidTransitionError(
            f"Cannot convert booking in '{booking.status}' status"
        )

    if not booking.customer_id:
        raise ValueError("Booking must have a customer to convert to a ticket")

    # Create ticket
    ticket = Ticket(
        ticket_number=ticket_number,
        branch_id=booking.location_id,
        customer_id=booking.customer_id,
        device_id=booking.device_id if booking.device_id else _ensure_device(booking),
        priority="normal",
        internal_status=Ticket.STATUS_UNASSIGNED,
        customer_status="Received",
        issue_summary=issue_summary or booking.notes or "",
    )
    db.session.add(ticket)
    db.session.flush()

    # Create intake note
    intake_parts = []
    if issue_summary:
        intake_parts.append(f"Issue: {issue_summary}")
    elif booking.notes:
        intake_parts.append(f"Issue: {booking.notes}")
    if device_condition:
        intake_parts.append(f"Device condition: {device_condition}")
    if accessories:
        intake_parts.append(f"Accessories: {accessories}")
    if booking.repair_service:
        intake_parts.append(f"Service: {booking.repair_service.name}")
    intake_parts.append(f"Converted from booking on {booking.start_time.strftime('%Y-%m-%d %H:%M')}")

    if intake_parts:
        db.session.add(TicketNote(
            ticket_id=ticket.id,
            author_user_id=_uuid.UUID(str(user_id)) if user_id else None,
            note_type="internal",
            content="\n".join(intake_parts),
        ))

    # Create portal token
    try:
        db.session.add(PortalToken(
            token=secrets.token_urlsafe(24),
            token_type="public_status_lookup",
            ticket_id=ticket.id,
        ))
    except Exception:
        pass  # portal token failure should not block conversion

    # Mark booking as converted
    booking.status = Booking.STATUS_CONVERTED
    booking.converted_ticket_id = ticket.id
    booking.linked_ticket_id = ticket.id

    db.session.flush()

    try:
        log_action(
            "booking.convert",
            "Booking",
            str(booking.id),
            details={
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
            },
        )
    except Exception:
        pass

    return ticket


def _ensure_device(booking: Booking) -> _uuid.UUID | None:
    """If booking has a customer but no device, return None (device is required by Ticket).

    The caller should ensure a device is selected before conversion.
    """
    if booking.customer and booking.customer.devices:
        return booking.customer.devices[0].id
    return None
