import uuid
from decimal import Decimal

from app.extensions import db
from app.models import StockLayer, StockLevel, StockMovement, StockReservation


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _as_uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _has_stock_layers_table() -> bool:
    conn = db.session.connection()
    return conn.dialect.has_table(conn, "stock_layers")


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


def _consume_fifo_layers(part_id, branch_id, location_id, qty):
    remaining = _as_decimal(qty)
    if not _has_stock_layers_table():
        return
    layers = (
        StockLayer.query.filter_by(part_id=part_id, branch_id=branch_id, location_id=location_id)
        .filter(StockLayer.quantity_remaining > 0)
        .order_by(StockLayer.created_at.asc())
        .all()
    )
    for layer in layers:
        if remaining <= 0:
            break
        available = _as_decimal(layer.quantity_remaining)
        consume = available if available <= remaining else remaining
        layer.quantity_remaining = available - consume
        remaining -= consume


def apply_stock_movement(part_id, branch_id, location_id, movement_type, quantity, notes=None, ticket_id=None, unit_cost=None):
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
        _consume_fifo_layers(part_id, branch_id, location_id, qty)
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

    if movement_type == "inbound" and _has_stock_layers_table():
        layer = StockLayer(
            part_id=part_id,
            branch_id=branch_id,
            location_id=location_id,
            source_movement_id=movement.id,
            unit_cost=unit_cost,
            quantity_received=qty,
            quantity_remaining=qty,
        )
        db.session.add(layer)
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
