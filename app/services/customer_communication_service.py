"""Customer communication service — message templates and token lifecycle.

Generates customer-safe messages for common repair states, manages portal
token regeneration/revocation, and provides helpers for building
communication shortcuts on the ticket detail page.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from app.extensions import db
from app.models.intake import PortalToken
from app.models.ticket import Ticket


# ---------------------------------------------------------------------------
# Message templates keyed by internal status
# ---------------------------------------------------------------------------

_MESSAGE_TEMPLATES: dict[str, dict] = {
    "checked_in": {
        "label": "Checked In / Received",
        "subject": "Your device has been checked in",
        "body": (
            "Hi{customer_name},\n\n"
            "Your {device_summary} has been checked in for repair "
            "(Ref: {ticket_number}).\n\n"
            "You can track the status of your repair at any time here:\n"
            "{portal_url}\n\n"
            "We'll keep you updated as things progress.\n\n"
            "Thank you for choosing us!"
        ),
        "statuses": {"unassigned", "assigned"},
    },
    "awaiting_diagnosis": {
        "label": "Awaiting Diagnosis",
        "subject": "Your device is being diagnosed",
        "body": (
            "Hi{customer_name},\n\n"
            "Our technician is now diagnosing your {device_summary} "
            "(Ref: {ticket_number}).\n\n"
            "We'll let you know the findings and next steps shortly.\n\n"
            "Track your repair status:\n{portal_url}"
        ),
        "statuses": {"awaiting_diagnostics"},
    },
    "quote_ready": {
        "label": "Quote Ready for Approval",
        "subject": "Your repair quote is ready for review",
        "body": (
            "Hi{customer_name},\n\n"
            "We've completed the diagnosis of your {device_summary} "
            "(Ref: {ticket_number}) and prepared a repair quote for you.\n\n"
            "Please review and approve the quote here:\n"
            "{quote_approval_url}\n\n"
            "Or check the full repair status:\n{portal_url}\n\n"
            "If you have any questions, don't hesitate to contact us."
        ),
        "statuses": {"awaiting_quote_approval"},
    },
    "waiting_for_parts": {
        "label": "Waiting for Parts",
        "subject": "Parts on order for your repair",
        "body": (
            "Hi{customer_name},\n\n"
            "We are currently waiting for parts needed to repair your "
            "{device_summary} (Ref: {ticket_number}).\n\n"
            "We'll notify you as soon as the parts arrive and work resumes.\n\n"
            "Track your repair status:\n{portal_url}"
        ),
        "statuses": {"awaiting_parts"},
    },
    "in_repair": {
        "label": "In Repair",
        "subject": "Your device is being repaired",
        "body": (
            "Hi{customer_name},\n\n"
            "Great news — your {device_summary} (Ref: {ticket_number}) "
            "is now being repaired by our technician.\n\n"
            "We'll let you know once it's ready for collection.\n\n"
            "Track your repair status:\n{portal_url}"
        ),
        "statuses": {"in_repair"},
    },
    "ready_for_collection": {
        "label": "Ready for Collection",
        "subject": "Your device is ready for collection!",
        "body": (
            "Hi{customer_name},\n\n"
            "Your {device_summary} (Ref: {ticket_number}) is ready "
            "for collection!\n\n"
            "{opening_hours}"
            "Please bring a valid ID when collecting your device.\n\n"
            "View your repair summary:\n{portal_url}\n\n"
            "Thank you for your patience!"
        ),
        "statuses": {"ready_for_collection"},
    },
    "completed": {
        "label": "Completed / Collected",
        "subject": "Your repair is complete",
        "body": (
            "Hi{customer_name},\n\n"
            "Your {device_summary} (Ref: {ticket_number}) repair has "
            "been completed. Thank you for choosing us!\n\n"
            "You can review your repair summary:\n{portal_url}\n\n"
            "If you experience any issues, please don't hesitate to "
            "contact us."
        ),
        "statuses": {"completed", "archived"},
    },
}

# Flat list sorted logically for UI display
TEMPLATE_KEYS_ORDERED = [
    "checked_in",
    "awaiting_diagnosis",
    "quote_ready",
    "waiting_for_parts",
    "in_repair",
    "ready_for_collection",
    "completed",
]


def available_templates() -> list[dict]:
    """Return all template metadata (key, label) in display order."""
    return [
        {"key": k, "label": _MESSAGE_TEMPLATES[k]["label"]}
        for k in TEMPLATE_KEYS_ORDERED
    ]


def suggested_template_key(internal_status: str) -> str:
    """Return the best-matching template key for the given status."""
    for key in TEMPLATE_KEYS_ORDERED:
        tpl = _MESSAGE_TEMPLATES[key]
        if internal_status in tpl["statuses"]:
            return key
    return "checked_in"


def generate_message(
    template_key: str,
    *,
    ticket_number: str,
    device_summary: str,
    customer_name: str | None = None,
    portal_url: str | None = None,
    quote_approval_url: str | None = None,
    opening_hours: str | None = None,
) -> dict:
    """Render a customer communication message from a template.

    Returns dict with 'subject', 'body', and 'label'.
    """
    tpl = _MESSAGE_TEMPLATES.get(template_key)
    if not tpl:
        tpl = _MESSAGE_TEMPLATES["checked_in"]

    name_part = f" {customer_name}" if customer_name else ""
    hours_text = f"Opening hours: {opening_hours}\n\n" if opening_hours else ""

    body = tpl["body"].format(
        customer_name=name_part,
        device_summary=device_summary,
        ticket_number=ticket_number,
        portal_url=portal_url or "(portal link not available)",
        quote_approval_url=quote_approval_url or "(no quote approval link available)",
        opening_hours=hours_text,
    )
    subject = tpl["subject"]

    return {"subject": subject, "body": body, "label": tpl["label"]}


# ---------------------------------------------------------------------------
# Portal token lifecycle
# ---------------------------------------------------------------------------


def regenerate_portal_token(ticket_id) -> str:
    """Invalidate any existing public_status_lookup token and create a new one.

    Returns the new token string.
    """
    # Delete all existing status tokens for this ticket
    PortalToken.query.filter_by(
        ticket_id=ticket_id, token_type="public_status_lookup"
    ).delete()
    db.session.flush()

    new_token = secrets.token_urlsafe(24)
    db.session.add(
        PortalToken(
            token=new_token,
            token_type="public_status_lookup",
            ticket_id=ticket_id,
        )
    )
    db.session.flush()
    return new_token


def revoke_portal_token(ticket_id) -> int:
    """Revoke (delete) all public_status_lookup tokens for a ticket.

    Returns number of tokens deleted.
    """
    count = PortalToken.query.filter_by(
        ticket_id=ticket_id, token_type="public_status_lookup"
    ).delete()
    db.session.flush()
    return count


def get_portal_token(ticket_id) -> PortalToken | None:
    """Get the active public_status_lookup token for a ticket."""
    return PortalToken.query.filter_by(
        ticket_id=ticket_id, token_type="public_status_lookup"
    ).first()


def get_quote_approval_url_for_ticket(ticket) -> str | None:
    """Return the public quote approval URL if a pending quote exists.

    Requires flask request context for url_for.
    """
    from flask import url_for
    from app.models.quote import Quote, QuoteApproval

    quote = (
        Quote.query.filter(
            Quote.ticket_id == ticket.id,
            Quote.status.in_(("draft", "sent")),
        )
        .order_by(Quote.version.desc(), Quote.created_at.desc())
        .first()
    )
    if not quote:
        return None

    approval = (
        QuoteApproval.query.filter_by(quote_id=quote.id, status="pending")
        .order_by(QuoteApproval.created_at.desc())
        .first()
    )
    if not approval:
        return None

    return url_for(
        "public_portal.public_quote_approval",
        token=approval.token,
        _external=True,
    )
