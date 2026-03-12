import uuid
from decimal import Decimal

from app.extensions import db
from app.models import StockLevel, StockMovement, StockReservation


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _as_uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def get_or_create_stock_level(part_id, branch_id, location_id):
    part_id = _as_uuid(part_id)
    branch_id = _as_uuid(branch_id)
    location_id = _as_uuid(location_id)

    level = StockLevel.query.filter_by(part_id=part_id, branch_id=branch_id, location_id=location_id).first()
    if level is None:
        level = StockLevel(part_id=part_id, branch_id=branch_id, location_id=location_id, on_hand_qty=0, reserved_qty=0)
        db.session.add(level)
        db.session.flush()
    return level


def apply_stock_movement(part_id, branch_id, location_id, movement_type, quantity, notes=None, ticket_id=None):
    part_id = _as_uuid(part_id)
    branch_id = _as_uuid(branch_id)
    location_id = _as_uuid(location_id)
    ticket_id = _as_uuid(ticket_id) if ticket_id else None
    qty = _as_decimal(quantity)
    level = get_or_create_stock_level(part_id, branch_id, location_id)

    if movement_type == "inbound":
        level.on_hand_qty = _as_decimal(level.on_hand_qty) + qty
    elif movement_type in {"outbound", "install"}:
        level.on_hand_qty = _as_decimal(level.on_hand_qty) - qty
    elif movement_type == "reservation":
        level.reserved_qty = _as_decimal(level.reserved_qty) + qty
    elif movement_type == "release":
        level.reserved_qty = _as_decimal(level.reserved_qty) - qty
    elif movement_type == "adjustment":
        level.on_hand_qty = _as_decimal(level.on_hand_qty) + qty

    movement = StockMovement(
        part_id=part_id,
        branch_id=branch_id,
        location_id=location_id,
        ticket_id=ticket_id,
        movement_type=movement_type,
        quantity=qty,
        notes=notes,
    )
    db.session.add(movement)
    db.session.flush()
    return movement


def reserve_stock_for_ticket(ticket_id, part_id, branch_id, location_id, quantity):
    ticket_id = _as_uuid(ticket_id)
    part_id = _as_uuid(part_id)
    branch_id = _as_uuid(branch_id)
    location_id = _as_uuid(location_id)
    qty = _as_decimal(quantity)
    level = get_or_create_stock_level(part_id, branch_id, location_id)
    available = _as_decimal(level.on_hand_qty) - _as_decimal(level.reserved_qty)
    if qty > available:
        raise ValueError("Insufficient available stock")

    reservation = StockReservation(
        ticket_id=ticket_id,
        part_id=part_id,
        branch_id=branch_id,
        location_id=location_id,
        quantity=qty,
        status="reserved",
    )
    db.session.add(reservation)
    apply_stock_movement(part_id, branch_id, location_id, "reservation", qty, notes="Reserved for ticket", ticket_id=ticket_id)
    return reservation
