"""Customer-facing status mapping service.

Maps internal workflow states to clear, non-technical customer-facing labels
and contextual messages. Used by the public repair status page.

All customer-facing strings are wrapped with gettext so they resolve in the
active locale (session-based for public pages, or forced via
``force_locale`` for generated messages).
"""
from __future__ import annotations

from flask_babel import gettext as _, lazy_gettext as _l

from app.models.ticket import Ticket


# ---------------------------------------------------------------------------
# Internal status → Customer-friendly label
# ---------------------------------------------------------------------------

# Backward-compatible module-level constant (lazy strings resolve at access time)
CUSTOMER_STATUS_MAP: dict[str, str] = {
    Ticket.STATUS_UNASSIGNED: _l("Checked In"),
    Ticket.STATUS_ASSIGNED: _l("Checked In"),
    Ticket.STATUS_AWAITING_DIAGNOSTICS: _l("Awaiting Diagnosis"),
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: _l("Awaiting Your Approval"),
    Ticket.STATUS_AWAITING_PARTS: _l("Waiting for Parts"),
    Ticket.STATUS_IN_REPAIR: _l("In Repair"),
    Ticket.STATUS_TESTING_QA: _l("Quality Check"),
    Ticket.STATUS_READY_FOR_COLLECTION: _l("Ready for Collection"),
    Ticket.STATUS_COMPLETED: _l("Completed"),
    Ticket.STATUS_CANCELLED: _l("Cancelled"),
    Ticket.STATUS_ARCHIVED: _l("Completed"),
}


def _customer_status_map() -> dict[str, str]:
    """Build the map at call-time so gettext resolves in the active locale."""
    return {
        Ticket.STATUS_UNASSIGNED: _("Checked In"),
        Ticket.STATUS_ASSIGNED: _("Checked In"),
        Ticket.STATUS_AWAITING_DIAGNOSTICS: _("Awaiting Diagnosis"),
        Ticket.STATUS_AWAITING_QUOTE_APPROVAL: _("Awaiting Your Approval"),
        Ticket.STATUS_AWAITING_PARTS: _("Waiting for Parts"),
        Ticket.STATUS_IN_REPAIR: _("In Repair"),
        Ticket.STATUS_TESTING_QA: _("Quality Check"),
        Ticket.STATUS_READY_FOR_COLLECTION: _("Ready for Collection"),
        Ticket.STATUS_COMPLETED: _("Completed"),
        Ticket.STATUS_CANCELLED: _("Cancelled"),
        Ticket.STATUS_ARCHIVED: _("Completed"),
    }


def customer_friendly_status(internal_status: str) -> str:
    """Return a customer-friendly label for the given internal status."""
    return _customer_status_map().get(internal_status, internal_status.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Progress step mapping (0-indexed)
# ---------------------------------------------------------------------------

def progress_steps() -> list[str]:
    """Return progress step labels resolved in the active locale."""
    return [_("Checked In"), _("Diagnosing"), _("Approved"), _("Repairing"), _("Quality Check"), _("Ready")]


# Keep the constant for backward compatibility — lazy so it resolves later
PROGRESS_STEPS = [_l("Checked In"), _l("Diagnosing"), _l("Approved"), _l("Repairing"), _l("Quality Check"), _l("Ready")]

STEP_INDEX_MAP: dict[str, int] = {
    Ticket.STATUS_UNASSIGNED: 0,
    Ticket.STATUS_ASSIGNED: 0,
    Ticket.STATUS_AWAITING_DIAGNOSTICS: 1,
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: 1,
    Ticket.STATUS_AWAITING_PARTS: 3,
    Ticket.STATUS_IN_REPAIR: 3,
    Ticket.STATUS_TESTING_QA: 4,
    Ticket.STATUS_READY_FOR_COLLECTION: 5,
    Ticket.STATUS_COMPLETED: 5,
    Ticket.STATUS_CANCELLED: -1,
    Ticket.STATUS_ARCHIVED: -1,
}


def progress_step_index(internal_status: str) -> int:
    """Return the progress step index (0-based) for the given status. -1 = hidden."""
    return STEP_INDEX_MAP.get(internal_status, 0)


# ---------------------------------------------------------------------------
# Contextual communication summary
# ---------------------------------------------------------------------------

def _communication_messages() -> dict[str, str]:
    """Build communication messages at call-time for locale resolution."""
    return {
        Ticket.STATUS_UNASSIGNED: _("Your device has been checked in and is awaiting assignment to a technician."),
        Ticket.STATUS_ASSIGNED: _("Your device has been checked in and a technician has been assigned."),
        Ticket.STATUS_AWAITING_DIAGNOSTICS: _("Our technician is diagnosing your device to determine what needs to be done."),
        Ticket.STATUS_AWAITING_QUOTE_APPROVAL: _("We have prepared a repair quote for your approval. Please review and approve it so we can proceed."),
        Ticket.STATUS_AWAITING_PARTS: _("We are waiting for parts needed for your repair. We'll update you when they arrive."),
        Ticket.STATUS_IN_REPAIR: _("Your device is currently being repaired by our technician."),
        Ticket.STATUS_TESTING_QA: _("The repair is complete and your device is undergoing quality checks."),
        Ticket.STATUS_READY_FOR_COLLECTION: _("Great news — your device is ready! Please visit us during opening hours to collect it."),
        Ticket.STATUS_COMPLETED: _("Your repair has been completed and collected. Thank you for choosing us!"),
        Ticket.STATUS_CANCELLED: _("This repair has been cancelled. Please contact us if you have any questions."),
        Ticket.STATUS_ARCHIVED: _("This repair has been completed. Thank you for choosing us!"),
    }


def communication_summary(internal_status: str, *, has_pending_quote: bool = False, has_pending_parts: bool = False) -> str:
    """Return a contextual customer-facing summary message.

    The message is based on the internal status but can be enriched with
    additional context such as pending quotes or parts.
    """
    if has_pending_quote and internal_status == Ticket.STATUS_AWAITING_QUOTE_APPROVAL:
        return _("We have prepared a repair quote for your approval. Please review it below and let us know if you'd like to proceed.")

    if has_pending_parts and internal_status == Ticket.STATUS_AWAITING_PARTS:
        return _("We are waiting for parts required for your repair. We will notify you as soon as they arrive and work can resume.")

    return _communication_messages().get(internal_status, _("Your repair is being processed. We'll keep you updated."))


# ---------------------------------------------------------------------------
# Customer-safe timeline events
# ---------------------------------------------------------------------------

# Note types that are safe to show to customers
CUSTOMER_SAFE_NOTE_TYPES = {"customer", "customer_update", "communication"}

# Internal status changes that are safe to show as timeline events
def customer_safe_status_events() -> dict[str, str]:
    """Build status event labels at call-time for locale resolution."""
    return {
        "checked_in": _("Device checked in"),
        "diagnosis_started": _("Diagnosis started"),
        "quote_sent": _("Quote sent for your approval"),
        "quote_approved": _("Quote approved"),
        "parts_ordered": _("Parts ordered"),
        "repair_started": _("Repair started"),
        "quality_check": _("Quality check in progress"),
        "ready_for_collection": _("Ready for collection"),
        "completed": _("Repair completed"),
    }


# Keep backward-compatible constant
CUSTOMER_SAFE_STATUS_EVENTS = {
    "checked_in": _l("Device checked in"),
    "diagnosis_started": _l("Diagnosis started"),
    "quote_sent": _l("Quote sent for your approval"),
    "quote_approved": _l("Quote approved"),
    "parts_ordered": _l("Parts ordered"),
    "repair_started": _l("Repair started"),
    "quality_check": _l("Quality check in progress"),
    "ready_for_collection": _l("Ready for collection"),
    "completed": _l("Repair completed"),
}
