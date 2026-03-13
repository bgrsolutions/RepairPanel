from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_customer_update_email(*, customer_email: str, customer_name: str | None, ticket_number: str, message: str) -> bool:
    """Foundation hook for outbound customer-update emails.

    Returns True when the request is accepted/queued by the configured transport.
    Currently logs intent only and returns False so workflows remain safe when no
    mail transport is configured.
    """

    logger.info(
        "Customer update email intent: to=%s customer=%s ticket=%s chars=%s",
        customer_email,
        customer_name or "",
        ticket_number,
        len(message or ""),
    )
    return False
