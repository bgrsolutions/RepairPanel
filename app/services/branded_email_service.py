"""Branded email service — company-branded customer communications.

Provides a structured email-sending architecture with:
- Company branding (name, logo, terms)
- Template-based email generation
- Log transport for development/testing
- SMTP transport for production delivery
- Language-aware template selection (EN/ES)
- Delivery result tracking
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from flask import current_app, render_template

from app.extensions import db

logger = logging.getLogger(__name__)


class EmailResult:
    """Result of an email send attempt."""

    def __init__(self, success: bool, message: str = "", error: str | None = None,
                 transport: str = "unknown"):
        self.success = success
        self.message = message
        self.error = error
        self.transport = transport

    def __bool__(self):
        return self.success

    def __repr__(self):
        return f"<EmailResult success={self.success} transport={self.transport!r} message={self.message!r}>"


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


def _get_sender_info() -> tuple[str, str, str]:
    """Return (sender_email, sender_name, reply_to) from config/company.

    Priority: config env vars > company record > fallback defaults.
    """
    branding = _get_company_branding()
    sender_email = (
        current_app.config.get("MAIL_DEFAULT_SENDER_EMAIL")
        or branding.get("company_email")
        or "noreply@example.com"
    )
    sender_name = (
        current_app.config.get("MAIL_DEFAULT_SENDER_NAME")
        or branding.get("company_name")
        or "IRONCore RepairPanel"
    )
    reply_to = (
        current_app.config.get("MAIL_DEFAULT_REPLY_TO")
        or sender_email
    )
    return sender_email, sender_name, reply_to


def _send_via_smtp(
    *,
    to_email: str,
    to_name: str | None,
    subject: str,
    html_body: str,
) -> EmailResult:
    """Send an email via SMTP.

    Reads SMTP configuration from Flask app config. Fails gracefully on
    connection or authentication errors — never raises.
    """
    host = current_app.config.get("MAIL_SMTP_HOST", "localhost")
    port = current_app.config.get("MAIL_SMTP_PORT", 587)
    username = current_app.config.get("MAIL_SMTP_USERNAME", "")
    password = current_app.config.get("MAIL_SMTP_PASSWORD", "")
    use_tls = current_app.config.get("MAIL_SMTP_USE_TLS", True)
    use_ssl = current_app.config.get("MAIL_SMTP_USE_SSL", False)
    timeout = current_app.config.get("MAIL_SMTP_TIMEOUT", 10)

    sender_email, sender_name, reply_to = _get_sender_info()

    if not sender_email or sender_email == "noreply@example.com":
        return EmailResult(
            False,
            "SMTP sender email not configured",
            error="missing_sender",
            transport="smtp",
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender_email))
    msg["To"] = formataddr((to_name or "", to_email))
    if reply_to and reply_to != sender_email:
        msg["Reply-To"] = reply_to

    # Attach plain-text fallback (stripped HTML) and HTML body
    from html import unescape
    import re
    plain_text = unescape(re.sub(r"<[^>]+>", "", html_body))
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            if use_tls and not use_ssl:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.sendmail(sender_email, [to_email], msg.as_string())

        logger.info(
            "Branded email [SMTP]: to=%s subject=%s sender=%s",
            to_email, subject, sender_email,
        )
        return EmailResult(True, "Sent via SMTP", transport="smtp")

    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP authentication failed: {e}"
        logger.error("Branded email SMTP auth error: %s", error_msg)
        return EmailResult(False, "SMTP authentication failed", error=error_msg, transport="smtp")
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {e}"
        logger.error("Branded email SMTP error: %s", error_msg)
        return EmailResult(False, "SMTP delivery failed", error=error_msg, transport="smtp")
    except OSError as e:
        error_msg = f"SMTP connection error: {e}"
        logger.error("Branded email SMTP connection error: %s", error_msg)
        return EmailResult(False, "SMTP connection failed", error=error_msg, transport="smtp")


def send_branded_email(
    *,
    to_email: str,
    to_name: str | None = None,
    subject: str,
    template_name: str,
    template_context: dict | None = None,
    language: str = "en",
    event_type: str | None = None,
) -> EmailResult:
    """Send a branded email using a Jinja2 template.

    Dispatches to the configured transport (log or smtp).

    Args:
        to_email: Recipient email address.
        to_name: Recipient display name (optional).
        subject: Email subject line.
        template_name: Name of the email template (without path prefix).
        template_context: Additional context variables for the template.
        language: Language code for template selection (default: "en").
        event_type: Optional label for delivery logging (e.g. "warranty_confirmation").

    Returns:
        EmailResult with success status and transport used.
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

    if transport == "smtp":
        result = _send_via_smtp(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_body=html_body,
        )
    elif transport == "log":
        logger.info(
            "Branded email [LOG]: to=%s subject=%s template=%s chars=%d",
            to_email,
            subject,
            template_name,
            len(html_body),
        )
        result = EmailResult(True, "Logged (dev mode)", transport="log")
    else:
        logger.warning("Unknown mail transport: %s — falling back to log", transport)
        logger.info(
            "Branded email [FALLBACK]: to=%s subject=%s template=%s",
            to_email,
            subject,
            template_name,
        )
        result = EmailResult(True, "Logged (unknown transport fallback)", transport="log")

    # Delivery logging
    _log_delivery(
        to_email=to_email,
        subject=subject,
        template_name=template_name,
        event_type=event_type,
        transport=result.transport,
        success=result.success,
        error=result.error,
    )

    return result


def _log_delivery(
    *,
    to_email: str,
    subject: str,
    template_name: str,
    event_type: str | None,
    transport: str,
    success: bool,
    error: str | None,
) -> None:
    """Log email delivery attempt for audit trail."""
    status = "success" if success else "failed"
    logger.info(
        "EMAIL_DELIVERY: status=%s transport=%s to=%s subject=%s "
        "template=%s event=%s error=%s",
        status, transport, to_email, subject,
        template_name, event_type or "-", error or "-",
    )


def send_test_email(to_email: str) -> EmailResult:
    """Send a test email to verify transport configuration.

    Uses a minimal built-in template that does not require any ticket/customer
    context, making it safe to send from the settings page.
    """
    return send_branded_email(
        to_email=to_email,
        to_name="",
        subject="IRONCore RepairPanel — Test Email",
        template_name="test_email.html",
        template_context={
            "transport": current_app.config.get("MAIL_TRANSPORT", "log"),
        },
        language="en",
        event_type="test_email",
    )


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
        event_type="warranty_confirmation",
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
        event_type="warranty_expiry_reminder",
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
        event_type="aftercare_followup",
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
