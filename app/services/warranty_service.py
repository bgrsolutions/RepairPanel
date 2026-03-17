"""Warranty service — creation, evaluation, claim, and void logic.

Handles warranty lifecycle:
- Auto-creation on ticket completion with type/coverage selection
- Evaluation of warranty status for a device/ticket
- Claim recording
- Voiding with reason
- History lookups for customer/device
- Parts history awareness
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta

from app.extensions import db
from app.models.warranty import TicketWarranty


def _to_uuid(value):
    """Convert a value to UUID if it's a string."""
    if isinstance(value, str):
        return _uuid.UUID(value)
    return value

logger = logging.getLogger(__name__)


def create_warranty(
    *,
    ticket,
    warranty_type: str = TicketWarranty.TYPE_STANDARD,
    warranty_days: int = 90,
    covers_labour: bool = True,
    covers_parts: bool = True,
    terms: str | None = None,
    repair_summary: str | None = None,
    parts_used: str | None = None,
    created_by_id: str | None = None,
) -> TicketWarranty:
    """Create a warranty record for a completed ticket.

    If a warranty already exists for this ticket, returns the existing one.
    """
    existing = TicketWarranty.query.filter_by(
        ticket_id=ticket.id, deleted_at=None
    ).first()
    if existing:
        logger.info("Warranty already exists for ticket %s", ticket.ticket_number)
        return existing

    now = datetime.utcnow()

    # For no_warranty type, set minimal defaults
    if warranty_type == TicketWarranty.TYPE_NO_WARRANTY:
        warranty_days = 0
        covers_labour = False
        covers_parts = False

    warranty = TicketWarranty(
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        device_id=ticket.device_id,
        branch_id=ticket.branch_id,
        warranty_type=warranty_type,
        warranty_days=warranty_days,
        starts_at=now,
        expires_at=now + timedelta(days=warranty_days),
        covers_labour=covers_labour,
        covers_parts=covers_parts,
        terms=terms,
        repair_summary=repair_summary,
        parts_used=parts_used,
        created_by_id=_to_uuid(created_by_id) if created_by_id else None,
    )
    db.session.add(warranty)
    db.session.flush()
    logger.info(
        "Created %s warranty for ticket %s (%d days)",
        warranty_type, ticket.ticket_number, warranty_days,
    )
    return warranty


def evaluate_warranty(ticket) -> dict:
    """Evaluate warranty status for a ticket.

    Returns a dict with:
    - has_warranty: bool (True even for no_warranty type, to indicate it was recorded)
    - warranty: TicketWarranty | None
    - is_active: bool
    - days_remaining: int
    - prior_repairs: list of prior warranty records for same device
    - fitted_parts: summary of parts used in warranted repairs
    """
    warranty = TicketWarranty.query.filter_by(
        ticket_id=ticket.id, deleted_at=None
    ).first()

    prior_repairs = []
    if ticket.device_id:
        prior_repairs = (
            TicketWarranty.query
            .filter(
                TicketWarranty.device_id == ticket.device_id,
                TicketWarranty.ticket_id != ticket.id,
                TicketWarranty.deleted_at.is_(None),
            )
            .order_by(TicketWarranty.created_at.desc())
            .all()
        )

    if not warranty:
        return {
            "has_warranty": False,
            "warranty": None,
            "is_active": False,
            "days_remaining": 0,
            "prior_repairs": prior_repairs,
        }

    return {
        "has_warranty": True,
        "warranty": warranty,
        "is_active": warranty.is_active,
        "days_remaining": warranty.days_remaining,
        "prior_repairs": prior_repairs,
    }


def get_device_warranty_history(device_id) -> list[TicketWarranty]:
    """Get all warranty records for a device, newest first."""
    return (
        TicketWarranty.query
        .filter_by(device_id=_to_uuid(device_id), deleted_at=None)
        .order_by(TicketWarranty.created_at.desc())
        .all()
    )


def get_customer_warranties(customer_id) -> list[TicketWarranty]:
    """Get all warranty records for a customer, newest first."""
    return (
        TicketWarranty.query
        .filter_by(customer_id=_to_uuid(customer_id), deleted_at=None)
        .order_by(TicketWarranty.created_at.desc())
        .all()
    )


def get_active_warranties(branch_id=None) -> list[TicketWarranty]:
    """Get all currently active warranties, optionally filtered by branch."""
    now = datetime.utcnow()
    query = TicketWarranty.query.filter(
        TicketWarranty.status == TicketWarranty.STATUS_ACTIVE,
        TicketWarranty.warranty_type != TicketWarranty.TYPE_NO_WARRANTY,
        TicketWarranty.expires_at > now,
        TicketWarranty.deleted_at.is_(None),
    )
    if branch_id:
        query = query.filter(TicketWarranty.branch_id == _to_uuid(branch_id))
    return query.order_by(TicketWarranty.expires_at.asc()).all()


def record_claim(warranty: TicketWarranty, notes: str | None = None) -> TicketWarranty:
    """Record a warranty claim."""
    now = datetime.utcnow()
    warranty.claim_count += 1
    warranty.last_claim_at = now
    warranty.status = TicketWarranty.STATUS_CLAIMED
    if notes:
        existing = warranty.claim_notes or ""
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        warranty.claim_notes = f"{existing}\n[{timestamp}] {notes}".strip()
    db.session.flush()
    logger.info("Recorded claim #%d on warranty %s", warranty.claim_count, warranty.id)
    return warranty


def void_warranty(
    warranty: TicketWarranty, reason: str, voided_by_id: str | None = None
) -> TicketWarranty:
    """Void a warranty with a reason."""
    now = datetime.utcnow()
    warranty.status = TicketWarranty.STATUS_VOIDED
    warranty.voided_reason = reason
    warranty.voided_at = now
    warranty.voided_by_id = _to_uuid(voided_by_id) if voided_by_id else None
    db.session.flush()
    logger.info("Voided warranty %s: %s", warranty.id, reason)
    return warranty


def check_device_under_warranty(device_id) -> TicketWarranty | None:
    """Check if a device currently has an active warranty.

    Returns the active warranty if found, otherwise None.
    Useful when creating new tickets to flag warranty-covered devices.
    """
    now = datetime.utcnow()
    return (
        TicketWarranty.query
        .filter(
            TicketWarranty.device_id == _to_uuid(device_id),
            TicketWarranty.status == TicketWarranty.STATUS_ACTIVE,
            TicketWarranty.warranty_type != TicketWarranty.TYPE_NO_WARRANTY,
            TicketWarranty.expires_at > now,
            TicketWarranty.deleted_at.is_(None),
        )
        .order_by(TicketWarranty.expires_at.desc())
        .first()
    )


def expire_warranties() -> int:
    """Batch-expire warranties past their expiration date.

    Returns the count of newly expired warranties.
    """
    now = datetime.utcnow()
    expired = TicketWarranty.query.filter(
        TicketWarranty.status == TicketWarranty.STATUS_ACTIVE,
        TicketWarranty.warranty_type != TicketWarranty.TYPE_NO_WARRANTY,
        TicketWarranty.expires_at <= now,
        TicketWarranty.deleted_at.is_(None),
    ).all()
    for w in expired:
        w.status = TicketWarranty.STATUS_EXPIRED
    db.session.flush()
    if expired:
        logger.info("Expired %d warranties", len(expired))
    return len(expired)


def get_ticket_parts_summary(ticket) -> str:
    """Build a human-readable summary of parts used on a ticket.

    Uses the existing stock reservation / consumption data.
    """
    from app.models import StockReservation
    reservations = StockReservation.query.filter_by(ticket_id=ticket.id).all()
    if not reservations:
        return ""
    parts_lines = []
    for r in reservations:
        part = r.part
        line = f"{part.name} x{r.quantity}" if part else f"Part #{r.part_id} x{r.quantity}"
        if r.status == "consumed":
            line += " (installed)"
        parts_lines.append(line)
    return "; ".join(parts_lines)
