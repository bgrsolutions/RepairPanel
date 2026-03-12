import uuid
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.order_forms import PartOrderCreateForm, PartOrderStatusForm
from app.models import Branch, Part, PartOrder, PartOrderLine, Supplier, Ticket
from app.services.order_service import append_order_event


orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.get("/")
@login_required
def list_orders():
    orders = PartOrder.query.order_by(PartOrder.created_at.desc()).all()
    return render_template("orders/list.html", orders=orders)


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_order():
    form = PartOrderCreateForm()
    form.supplier_id.choices = [(str(s.id), s.name) for s in Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()]
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]
    for entry in form.lines.entries:
        entry.form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.order_by(Part.name).all()]

    if form.validate_on_submit():
        ticket = Ticket.query.filter(Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).first()
        if ticket is None:
            flash(_("No ticket available to link order"), "error")
            return redirect(url_for("orders.list_orders"))

        order = PartOrder(
            ticket_id=ticket.id,
            supplier_id=uuid.UUID(str(form.supplier_id.data)),
            branch_id=uuid.UUID(str(form.branch_id.data)),
            reference=form.reference.data,
            shipping_reference=form.shipping_reference.data,
            eta_date=form.eta_date.data,
            status="ordered",
        )
        db.session.add(order)
        db.session.flush()

        for line_entry in form.lines.entries:
            db.session.add(
                PartOrderLine(
                    order_id=order.id,
                    part_id=uuid.UUID(str(line_entry.form.part_id.data)),
                    quantity=line_entry.form.quantity.data,
                    unit_cost=line_entry.form.unit_cost.data,
                    status="ordered",
                )
            )

        append_order_event(order, "ordered", notes="Order created")
        db.session.commit()
        flash(_("Part order created"), "success")
        return redirect(url_for("orders.list_orders"))

    return render_template("orders/new.html", form=form)


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
        if form.event_type.data == "installed":
            for line in order.lines:
                line.status = "installed"
        elif form.event_type.data == "arrived":
            for line in order.lines:
                line.status = "arrived"
        db.session.commit()
        flash(_("Order status updated"), "success")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    return render_template("orders/detail.html", order=order, form=form)
