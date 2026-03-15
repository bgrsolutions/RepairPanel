import uuid
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.order_forms import PartOrderCreateForm, PartOrderStatusForm, ReceiveOrderLineForm
from app.models import Branch, Customer, Part, PartOrder, PartOrderLine, StockLocation, Supplier, Ticket
from app.services.inventory_service import apply_stock_movement
from app.services.order_service import append_order_event, line_remaining_qty, order_total_cost


orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


def _part_choices():
    return [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter(Part.is_active.is_(True)).order_by(Part.name).all()]


def _ticket_choices(selected_ticket_id: str | None = None):
    rows = Ticket.query.filter(Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).limit(200).all()
    choices = [("", "-- General stock order (no ticket) --")]
    choices += [(str(t.id), f"{t.ticket_number} · {t.customer.full_name}") for t in rows]
    if selected_ticket_id and selected_ticket_id not in {c[0] for c in choices}:
        t = db.session.get(Ticket, uuid.UUID(selected_ticket_id))
        if t:
            choices.append((str(t.id), f"{t.ticket_number} · {t.customer.full_name}"))
    return choices


def _prepare_order_form(form: PartOrderCreateForm, selected_ticket_id: str | None = None):
    form.supplier_id.choices = [(str(s.id), s.name) for s in Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()]
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]
    form.ticket_id.choices = _ticket_choices(selected_ticket_id)
    if not form.lines.entries:
        form.lines.append_entry()
    part_choices = _part_choices()
    for entry in form.lines.entries:
        entry.form.part_id.choices = part_choices


def _save_order_from_form(order: PartOrder, form: PartOrderCreateForm):
    ticket_id = form.ticket_id.data or None
    order.ticket_id = uuid.UUID(ticket_id) if ticket_id else None
    order.order_type = "repair" if order.ticket_id else "stock"
    order.supplier_id = uuid.UUID(str(form.supplier_id.data))
    order.branch_id = uuid.UUID(str(form.branch_id.data))
    order.reference = form.reference.data
    order.supplier_reference = form.supplier_reference.data
    order.tracking_number = form.tracking_number.data
    order.ordered_at = form.ordered_at.data
    order.estimated_arrival_at = form.estimated_arrival_at.data
    order.notes = form.notes.data
    order.status = form.status.data

    if order.id is None:
        db.session.add(order)
        db.session.flush()

    order.lines.clear()
    db.session.flush()

    for line_entry in form.lines.entries:
        part_id = line_entry.form.part_id.data
        qty = line_entry.form.quantity.data
        if not part_id or qty is None:
            continue
        db.session.add(
            PartOrderLine(
                order_id=order.id,
                part_id=uuid.UUID(str(part_id)),
                description_override=line_entry.form.description_override.data,
                supplier_sku=line_entry.form.supplier_sku.data,
                quantity=qty,
                unit_cost=line_entry.form.unit_cost.data,
                sale_price=line_entry.form.sale_price.data,
                status=order.status,
            )
        )


@orders_bp.get("/ticket-search")
@login_required
def ticket_search():
    q=(request.args.get("q") or "").strip()
    if len(q)<2:
        return {"items": []}
    from sqlalchemy import or_
    like=f"%{q}%"
    rows=Ticket.query.filter(Ticket.deleted_at.is_(None)).join(Customer, Ticket.customer_id==Customer.id).filter(
        or_(Ticket.ticket_number.ilike(like), Customer.full_name.ilike(like), Customer.email.ilike(like))
    ).order_by(Ticket.created_at.desc()).limit(25).all()
    return {"items": [{"id": str(t.id), "label": f"{t.ticket_number} · {t.customer.full_name}"} for t in rows]}


@orders_bp.get("/")
@login_required
def list_orders():
    from sqlalchemy import or_
    query = PartOrder.query
    status_filter = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()
    if status_filter:
        query = query.filter(PartOrder.status == status_filter)
    if q:
        like = f"%{q}%"
        query = query.join(Supplier, PartOrder.supplier_id == Supplier.id).filter(
            or_(PartOrder.reference.ilike(like), PartOrder.supplier_reference.ilike(like), Supplier.name.ilike(like))
        )
    orders = query.order_by(PartOrder.created_at.desc()).all()
    now = datetime.utcnow()
    return render_template("orders/list.html", orders=orders, now=now, order_total_cost=order_total_cost)


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_order():
    selected_ticket_id = (request.args.get("ticket_id") or request.form.get("ticket_id") or "").strip()
    form = PartOrderCreateForm()
    _prepare_order_form(form, selected_ticket_id or None)

    if request.method == "GET" and selected_ticket_id:
        form.ticket_id.data = selected_ticket_id

    if form.validate_on_submit():
        order = PartOrder()
        _save_order_from_form(order, form)

        append_order_event(order, order.status, notes="Order created")
        db.session.commit()
        flash(_("Part order created"), "success")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    return render_template("orders/new.html", form=form, mode="create")


@orders_bp.route("/<uuid:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit_order(order_id):
    order = db.session.get(PartOrder, order_id)
    if not order:
        flash(_("Order not found"), "error")
        return redirect(url_for("orders.list_orders"))

    form = PartOrderCreateForm(obj=order)
    if request.method == "GET":
        form.ticket_id.data = str(order.ticket_id) if order.ticket_id else ""
        while len(form.lines.entries):
            form.lines.pop_entry()
        for line in order.lines:
            form.lines.append_entry(
                {
                    "part_id": str(line.part_id),
                    "description_override": line.description_override,
                    "supplier_sku": line.supplier_sku,
                    "quantity": line.quantity,
                    "unit_cost": line.unit_cost,
                    "sale_price": line.sale_price,
                }
            )
        form.lines.append_entry()
    _prepare_order_form(form, form.ticket_id.data)

    if form.validate_on_submit():
        _save_order_from_form(order, form)
        append_order_event(order, order.status, notes="Order updated")
        db.session.commit()
        flash(_("Order updated"), "success")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    return render_template("orders/new.html", form=form, mode="edit", order=order)


@orders_bp.post("/<uuid:order_id>/receive")
@login_required
def receive_order_line(order_id):
    order = db.session.get(PartOrder, order_id)
    if not order:
        flash(_("Order not found"), "error")
        return redirect(url_for("orders.list_orders"))

    form = ReceiveOrderLineForm()
    form.line_id.choices = [(str(line.id), f"{line.part.sku} · remaining {line_remaining_qty(line)}") for line in order.lines]
    form.location_id.choices = [
        (str(loc.id), f"{loc.code} - {loc.name}")
        for loc in StockLocation.query.filter_by(branch_id=order.branch_id).order_by(StockLocation.name.asc()).all()
    ]

    if form.validate_on_submit():
        line = db.session.get(PartOrderLine, uuid.UUID(str(form.line_id.data)))
        receive_qty = Decimal(str(form.quantity.data))
        remaining = line_remaining_qty(line)
        if receive_qty > remaining:
            flash(_("Received quantity exceeds remaining quantity"), "error")
            return redirect(url_for("orders.order_detail", order_id=order.id))

        line.received_quantity = Decimal(str(line.received_quantity or 0)) + receive_qty
        line.status = "received" if line_remaining_qty(line) <= 0 else "partially_received"

        if form.cost_price.data is not None:
            line.part.cost_price = form.cost_price.data
        # Use receive form sale_price, or fall back to order line sale_price
        effective_sale_price = form.sale_price.data if form.sale_price.data is not None else line.sale_price
        if effective_sale_price is not None:
            line.part.sale_price = effective_sale_price

        apply_stock_movement(
            part_id=line.part_id,
            branch_id=order.branch_id,
            location_id=uuid.UUID(str(form.location_id.data)),
            movement_type="inbound",
            quantity=receive_qty,
            notes=f"Order receive {order.reference or order.id}: {form.received_note.data or ''}".strip(),
            ticket_id=order.ticket_id,
            unit_cost=form.cost_price.data if form.cost_price.data is not None else line.unit_cost,
        )

        if all(line_remaining_qty(l) <= 0 for l in order.lines):
            order.status = "received"
            event_type = "received"
        else:
            order.status = "partially_received"
            event_type = "partially_received"

        append_order_event(order, event_type, notes=form.received_note.data or "Stock received")
        db.session.commit()
        flash(_("Stock received and inventory updated"), "success")
    else:
        flash(_("Invalid receiving request"), "error")

    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.post("/<uuid:order_id>/receive-all")
@login_required
def receive_all_lines(order_id):
    """Bulk-receive all remaining quantities on an order."""
    order = db.session.get(PartOrder, order_id)
    if not order:
        flash(_("Order not found"), "error")
        return redirect(url_for("orders.list_orders"))

    location_id_str = request.form.get("location_id", "").strip()
    bulk_note = request.form.get("bulk_note", "").strip() or "Bulk receive"

    if not location_id_str:
        flash(_("Please select a location"), "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    location_id = uuid.UUID(location_id_str)
    received_count = 0

    for line in order.lines:
        remaining = line_remaining_qty(line)
        if remaining <= 0:
            continue
        receive_qty = Decimal(str(remaining))
        line.received_quantity = Decimal(str(line.received_quantity or 0)) + receive_qty
        line.status = "received"

        # Update part cost/sale prices from line if set
        if line.unit_cost is not None:
            line.part.cost_price = line.unit_cost
        if line.sale_price is not None:
            line.part.sale_price = line.sale_price

        apply_stock_movement(
            part_id=line.part_id,
            branch_id=order.branch_id,
            location_id=location_id,
            movement_type="inbound",
            quantity=receive_qty,
            notes=f"Bulk receive {order.reference or order.id}: {bulk_note}",
            ticket_id=order.ticket_id,
            unit_cost=line.unit_cost,
        )
        received_count += 1

    order.status = "received"
    append_order_event(order, "received", notes=f"Bulk received {received_count} lines: {bulk_note}")
    db.session.commit()
    flash(_("All stock received (%(count)s lines)", count=received_count), "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/<uuid:order_id>", methods=["GET", "POST"])
@login_required
def order_detail(order_id):
    order = db.session.get(PartOrder, order_id)
    if not order:
        flash(_("Order not found"), "error")
        return redirect(url_for("orders.list_orders"))

    form = PartOrderStatusForm()
    if form.validate_on_submit():
        append_order_event(order, form.event_type.data, notes=form.notes.data)
        if form.event_type.data in {"cancelled", "received"}:
            for line in order.lines:
                line.status = form.event_type.data
        db.session.commit()
        flash(_("Order status updated"), "success")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    receive_form = ReceiveOrderLineForm()
    receive_form.line_id.choices = [(str(line.id), f"{line.part.sku} · remaining {line_remaining_qty(line)}") for line in order.lines if line_remaining_qty(line) > 0]
    receive_form.location_id.choices = [
        (str(loc.id), f"{loc.code} - {loc.name}")
        for loc in StockLocation.query.filter_by(branch_id=order.branch_id).order_by(StockLocation.name.asc()).all()
    ]

    return render_template(
        "orders/detail.html",
        order=order,
        form=form,
        receive_form=receive_form,
        line_remaining_qty=line_remaining_qty,
        order_total_cost=order_total_cost,
    )
