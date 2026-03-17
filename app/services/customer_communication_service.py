"""Customer communication service — message templates and token lifecycle.

Generates customer-safe messages for common repair states, manages portal
token regeneration/revocation, and provides helpers for building
communication shortcuts on the ticket detail page.

All customer-facing message strings are resolved via Flask-Babel so they
automatically render in the active locale.  When generating messages for
a specific customer, callers should use ``force_locale(lang)`` from
Flask-Babel to temporarily switch locale.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from flask_babel import gettext as _, force_locale

from app.extensions import db
from app.models.intake import PortalToken
from app.models.ticket import Ticket


# ---------------------------------------------------------------------------
# Message templates keyed by internal status
# ---------------------------------------------------------------------------

def _build_templates() -> dict[str, dict]:
    """Build localised message templates.

    Called at render-time so gettext resolves in the active locale.
    """
    return {
        "checked_in": {
            "label": _("Checked In / Received"),
            "subject": _("Your device has been checked in"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("Your %(device_summary)s has been checked in for repair (Ref: %(ticket_number)s).") + "\n\n"
                + _("You can track the status of your repair at any time here:") + "\n"
                "{portal_url}\n\n"
                + _("We'll keep you updated as things progress.") + "\n\n"
                + _("Thank you for choosing us!")
            ),
            "statuses": {"unassigned", "assigned"},
        },
        "awaiting_diagnosis": {
            "label": _("Awaiting Diagnosis"),
            "subject": _("Your device is being diagnosed"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("Our technician is now diagnosing your %(device_summary)s (Ref: %(ticket_number)s).") + "\n\n"
                + _("We'll let you know the findings and next steps shortly.") + "\n\n"
                + _("Track your repair status:") + "\n{portal_url}"
            ),
            "statuses": {"awaiting_diagnostics"},
        },
        "quote_ready": {
            "label": _("Quote Ready for Approval"),
            "subject": _("Your repair quote is ready for review"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("We've completed the diagnosis of your %(device_summary)s (Ref: %(ticket_number)s) and prepared a repair quote for you.") + "\n\n"
                + _("Please review and approve the quote here:") + "\n"
                "{quote_approval_url}\n\n"
                + _("Or check the full repair status:") + "\n{portal_url}\n\n"
                + _("If you have any questions, don't hesitate to contact us.")
            ),
            "statuses": {"awaiting_quote_approval"},
        },
        "waiting_for_parts": {
            "label": _("Waiting for Parts"),
            "subject": _("Parts on order for your repair"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("We are currently waiting for parts needed to repair your %(device_summary)s (Ref: %(ticket_number)s).") + "\n\n"
                + _("We'll notify you as soon as the parts arrive and work resumes.") + "\n\n"
                + _("Track your repair status:") + "\n{portal_url}"
            ),
            "statuses": {"awaiting_parts"},
        },
        "in_repair": {
            "label": _("In Repair"),
            "subject": _("Your device is being repaired"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("Great news — your %(device_summary)s (Ref: %(ticket_number)s) is now being repaired by our technician.") + "\n\n"
                + _("We'll let you know once it's ready for collection.") + "\n\n"
                + _("Track your repair status:") + "\n{portal_url}"
            ),
            "statuses": {"in_repair"},
        },
        "ready_for_collection": {
            "label": _("Ready for Collection"),
            "subject": _("Your device is ready for collection!"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("Your %(device_summary)s (Ref: %(ticket_number)s) is ready for collection!") + "\n\n"
                "{opening_hours}"
                + _("Please bring a valid ID when collecting your device.") + "\n\n"
                + _("View your repair summary:") + "\n{portal_url}\n\n"
                + _("Thank you for your patience!")
            ),
            "statuses": {"ready_for_collection"},
        },
        "completed": {
            "label": _("Completed / Collected"),
            "subject": _("Your repair is complete"),
            "body": (
                _("Hi%(customer_name)s,") + "\n\n"
                + _("Your %(device_summary)s (Ref: %(ticket_number)s) repair has been completed. Thank you for choosing us!") + "\n\n"
                + _("You can review your repair summary:") + "\n{portal_url}\n\n"
                + _("If you experience any issues, please don't hesitate to contact us.")
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
    templates = _build_templates()
    return [
        {"key": k, "label": templates[k]["label"]}
        for k in TEMPLATE_KEYS_ORDERED
    ]


def suggested_template_key(internal_status: str) -> str:
    """Return the best-matching template key for the given status."""
    templates = _build_templates()
    for key in TEMPLATE_KEYS_ORDERED:
        tpl = templates[key]
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
    language: str | None = None,
) -> dict:
    """Render a customer communication message from a template.

    If *language* is provided the message is rendered in that locale;
    otherwise the current request locale is used.

    Returns dict with 'subject', 'body', and 'label'.
    """
    def _render():
        templates = _build_templates()
        tpl = templates.get(template_key) or templates["checked_in"]

        name_part = f" {customer_name}" if customer_name else ""
        hours_text = (_("Opening hours: %(hours)s", hours=opening_hours) + "\n\n") if opening_hours else ""

        body = tpl["body"].format(
            portal_url=portal_url or _("(portal link not available)"),
            quote_approval_url=quote_approval_url or _("(no quote approval link available)"),
            opening_hours=hours_text,
        ) % {
            "customer_name": name_part,
            "device_summary": device_summary,
            "ticket_number": ticket_number,
        }
        subject = tpl["subject"] % {
            "customer_name": name_part,
            "device_summary": device_summary,
            "ticket_number": ticket_number,
        } if "%" in tpl["subject"] else tpl["subject"]

        return {"subject": subject, "body": body, "label": tpl["label"]}

    if language:
        with force_locale(language):
            return _render()
    return _render()


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
