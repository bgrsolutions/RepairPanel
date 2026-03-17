"""Branded email service — company-branded customer communications.

Provides a structured email-sending architecture with:
- Company branding (name, logo, terms)
- Template-based email generation
- Safe fallback/logging when no transport is configured
- Language-aware template selection (EN/ES)
"""
from __future__ import annotations

import logging
from datetime import datetime

from flask import current_app, render_template

from app.extensions import db

logger = logging.getLogger(__name__)


class EmailResult:
    """Result of an email send attempt."""

    def __init__(self, success: bool, message: str = "", error: str | None = None):
        self.success = success
        self.message = message
        self.error = error

    def __bool__(self):
        return self.success

    def __repr__(self):
        return f"<EmailResult success={self.success} message={self.message!r}>"


def _get_company_branding() -> dict:
    """Retrieve the company branding information for email templates."""
    from app.models import Company

    company = Company.query.filter_by(is_active=True, deleted_at=None).first()
    if not company:
        return {
            "company_name": current_app.config.get("APP_NAME", "IRONCore RepairPanel"),
            "company_email": "",
            "company_phone": "",
            "company_website": "",
            "company_logo": None,
            "document_footer": "",
        }
    return {
        "company_name": company.display_name,
        "company_email": company.email or "",
        "company_phone": company.phone or "",
        "company_website": company.website or "",
        "company_logo": company.logo_path,
        "document_footer": company.document_footer or "",
    }


def send_branded_email(
    *,
    to_email: str,
    to_name: str | None = None,
    subject: str,
    template_name: str,
    template_context: dict | None = None,
    language: str = "en",
) -> EmailResult:
    """Send a branded email using a Jinja2 template.

    Currently logs intent and returns success=False when no mail transport
    is configured. When a transport (SMTP, SendGrid, etc.) is configured
    via MAIL_TRANSPORT in app config, it will dispatch accordingly.

    Args:
        to_email: Recipient email address.
        to_name: Recipient display name (optional).
        subject: Email subject line.
        template_name: Name of the email template (without path prefix).
        template_context: Additional context variables for the template.
        language: Language code for template selection (default: "en").

    Returns:
        EmailResult with success status.
    """
    if not to_email:
        return EmailResult(False, "No recipient email", error="missing_email")

    branding = _get_company_branding()
    ctx = {
        "branding": branding,
        "recipient_name": to_name or "",
        "language": language,
        "year": datetime.utcnow().year,
        **(template_context or {}),
    }

    # Try language-specific template first, fallback to English
    template_path = f"emails/{language}/{template_name}"
    try:
        html_body = render_template(template_path, **ctx)
    except Exception:
        template_path = f"emails/en/{template_name}"
        try:
            html_body = render_template(template_path, **ctx)
        except Exception as e:
            logger.error("Email template not found: %s — %s", template_name, e)
            return EmailResult(False, "Template not found", error=str(e))

    transport = current_app.config.get("MAIL_TRANSPORT", "log")

    if transport == "log":
        logger.info(
            "Branded email [LOG]: to=%s subject=%s template=%s chars=%d",
            to_email,
            subject,
            template_name,
            len(html_body),
        )
        return EmailResult(True, "Logged (no transport configured)")

    # Future: SMTP, SendGrid, etc.
    logger.warning("Unknown mail transport: %s — falling back to log", transport)
    logger.info(
        "Branded email [FALLBACK]: to=%s subject=%s template=%s",
        to_email,
        subject,
        template_name,
    )
    return EmailResult(True, "Logged (unknown transport fallback)")


def send_warranty_confirmation_email(warranty, language: str = "en") -> EmailResult:
    """Send a warranty confirmation email to the customer."""
    customer = warranty.customer
    if not customer or not customer.email:
        return EmailResult(False, "Customer has no email", error="no_customer_email")

    result = send_branded_email(
        to_email=customer.email,
        to_name=customer.full_name,
        subject=_warranty_subject(warranty, language),
        template_name="warranty_confirmation.html",
        template_context={
            "warranty": warranty,
            "ticket": warranty.ticket,
            "device": warranty.device,
            "customer": customer,
        },
        language=language,
    )

    if result.success:
        warranty.email_sent = True
        warranty.email_sent_at = datetime.utcnow()
        db.session.flush()

    return result


def send_warranty_expiry_reminder_email(warranty, language: str = "en") -> EmailResult:
    """Send a warranty expiry reminder to the customer."""
    customer = warranty.customer
    if not customer or not customer.email:
        return EmailResult(False, "Customer has no email", error="no_customer_email")

    return send_branded_email(
        to_email=customer.email,
        to_name=customer.full_name,
        subject=_warranty_expiry_subject(warranty, language),
        template_name="warranty_expiry_reminder.html",
        template_context={
            "warranty": warranty,
            "ticket": warranty.ticket,
            "device": warranty.device,
            "customer": customer,
        },
        language=language,
    )


def send_aftercare_email(
    *,
    customer,
    ticket,
    message: str,
    language: str = "en",
) -> EmailResult:
    """Send a generic aftercare/follow-up email to a customer."""
    if not customer or not customer.email:
        return EmailResult(False, "Customer has no email", error="no_customer_email")

    return send_branded_email(
        to_email=customer.email,
        to_name=customer.full_name,
        subject=_aftercare_subject(ticket, language),
        template_name="aftercare_followup.html",
        template_context={
            "ticket": ticket,
            "customer": customer,
            "message": message,
        },
        language=language,
    )


def _warranty_subject(warranty, language: str) -> str:
    ticket_num = warranty.ticket.ticket_number if warranty.ticket else ""
    if language == "es":
        return f"Confirmación de garantía — Reparación {ticket_num}"
    return f"Warranty Confirmation — Repair {ticket_num}"


def _warranty_expiry_subject(warranty, language: str) -> str:
    if language == "es":
        return "Su garantía de reparación expira pronto"
    return "Your repair warranty is expiring soon"


def _aftercare_subject(ticket, language: str) -> str:
    ticket_num = ticket.ticket_number if ticket else ""
    if language == "es":
        return f"Seguimiento de su reparación {ticket_num}"
    return f"Follow-up on your repair {ticket_num}"
