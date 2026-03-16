"""Customer-facing status mapping service.

Maps internal workflow states to clear, non-technical customer-facing labels
and contextual messages. Used by the public repair status page.
"""
from __future__ import annotations

from app.models.ticket import Ticket


# ---------------------------------------------------------------------------
# Internal status → Customer-friendly label
# ---------------------------------------------------------------------------

CUSTOMER_STATUS_MAP: dict[str, str] = {
    Ticket.STATUS_UNASSIGNED: "Checked In",
    Ticket.STATUS_ASSIGNED: "Checked In",
    Ticket.STATUS_AWAITING_DIAGNOSTICS: "Awaiting Diagnosis",
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: "Awaiting Your Approval",
    Ticket.STATUS_AWAITING_PARTS: "Waiting for Parts",
    Ticket.STATUS_IN_REPAIR: "In Repair",
    Ticket.STATUS_TESTING_QA: "Quality Check",
    Ticket.STATUS_READY_FOR_COLLECTION: "Ready for Collection",
    Ticket.STATUS_COMPLETED: "Completed",
    Ticket.STATUS_CANCELLED: "Cancelled",
    Ticket.STATUS_ARCHIVED: "Completed",
}


def customer_friendly_status(internal_status: str) -> str:
    """Return a customer-friendly label for the given internal status."""
    return CUSTOMER_STATUS_MAP.get(internal_status, internal_status.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Progress step mapping (0-indexed)
# ---------------------------------------------------------------------------

PROGRESS_STEPS = ["Checked In", "Diagnosing", "Approved", "Repairing", "Quality Check", "Ready"]

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

_COMMUNICATION_MESSAGES: dict[str, str] = {
    Ticket.STATUS_UNASSIGNED: "Your device has been checked in and is awaiting assignment to a technician.",
    Ticket.STATUS_ASSIGNED: "Your device has been checked in and a technician has been assigned.",
    Ticket.STATUS_AWAITING_DIAGNOSTICS: "Our technician is diagnosing your device to determine what needs to be done.",
    Ticket.STATUS_AWAITING_QUOTE_APPROVAL: "We have prepared a repair quote for your approval. Please review and approve it so we can proceed.",
    Ticket.STATUS_AWAITING_PARTS: "We are waiting for parts needed for your repair. We'll update you when they arrive.",
    Ticket.STATUS_IN_REPAIR: "Your device is currently being repaired by our technician.",
    Ticket.STATUS_TESTING_QA: "The repair is complete and your device is undergoing quality checks.",
    Ticket.STATUS_READY_FOR_COLLECTION: "Great news — your device is ready! Please visit us during opening hours to collect it.",
    Ticket.STATUS_COMPLETED: "Your repair has been completed and collected. Thank you for choosing us!",
    Ticket.STATUS_CANCELLED: "This repair has been cancelled. Please contact us if you have any questions.",
    Ticket.STATUS_ARCHIVED: "This repair has been completed. Thank you for choosing us!",
}


def communication_summary(internal_status: str, *, has_pending_quote: bool = False, has_pending_parts: bool = False) -> str:
    """Return a contextual customer-facing summary message.

    The message is based on the internal status but can be enriched with
    additional context such as pending quotes or parts.
    """
    if has_pending_quote and internal_status == Ticket.STATUS_AWAITING_QUOTE_APPROVAL:
        return "We have prepared a repair quote for your approval. Please review it below and let us know if you'd like to proceed."

    if has_pending_parts and internal_status == Ticket.STATUS_AWAITING_PARTS:
        return "We are waiting for parts required for your repair. We will notify you as soon as they arrive and work can resume."

    return _COMMUNICATION_MESSAGES.get(internal_status, "Your repair is being processed. We'll keep you updated.")


# ---------------------------------------------------------------------------
# Customer-safe timeline events
# ---------------------------------------------------------------------------

# Note types that are safe to show to customers
CUSTOMER_SAFE_NOTE_TYPES = {"customer", "customer_update", "communication"}

# Internal status changes that are safe to show as timeline events
CUSTOMER_SAFE_STATUS_EVENTS = {
    "checked_in": "Device checked in",
    "diagnosis_started": "Diagnosis started",
    "quote_sent": "Quote sent for your approval",
    "quote_approved": "Quote approved",
    "parts_ordered": "Parts ordered",
    "repair_started": "Repair started",
    "quality_check": "Quality check in progress",
    "ready_for_collection": "Ready for collection",
    "completed": "Repair completed",
}
