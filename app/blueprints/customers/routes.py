import uuid

from sqlalchemy import inspect, or_

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.forms.customer_forms import CustomerEditForm
from app.models import Customer, Device, IntakeSubmission, StockReservation, Ticket, TicketWarranty


customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.get("/")
@login_required
def list_customers():
    query = (request.args.get("q") or "").strip()

    customers_query = Customer.query.filter(Customer.deleted_at.is_(None))
    if query:
        like = f"%{query}%"
        customers_query = customers_query.filter(or_(Customer.full_name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))

    customers = customers_query.order_by(Customer.full_name.asc()).all()
    return render_template("customers/list.html", customers=customers, query=query)


@customers_bp.post('/devices/<uuid:device_id>/transfer')
@login_required
def transfer_device(device_id):
    target_customer_id = (request.form.get('target_customer_id') or '').strip()
    redirect_customer = request.form.get('redirect_customer_id')
    device = db.session.get(Device, device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('customers.list_customers'))
    if target_customer_id:
        target = db.session.get(Customer, uuid.UUID(target_customer_id))
        if target:
            device.customer_id = target.id
            db.session.commit()
            flash('Device ownership updated', 'success')
    return redirect(url_for('customers.customer_detail', customer_id=redirect_customer or device.customer_id))


@customers_bp.post('/devices/<uuid:device_id>/unlink')
@login_required
def unlink_device(device_id):
    redirect_customer = request.form.get('redirect_customer_id')
    device = db.session.get(Device, device_id)
    if not device:
        flash('Device not found', 'error')
        return redirect(url_for('customers.list_customers'))
    device.customer_id = None
    db.session.commit()
    flash('Device unlinked from customer', 'success')
    return redirect(url_for('customers.customer_detail', customer_id=redirect_customer))


@customers_bp.get("/search")
@login_required
def customer_search_json():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return {"items": []}
    like = f"%{query}%"
    rows = Customer.query.filter(Customer.deleted_at.is_(None)).filter(
        or_(Customer.full_name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like))
    ).order_by(Customer.full_name.asc()).limit(25).all()
    items = []
    for c in rows:
        label = c.display_name + " · " + (c.phone or c.email or "")
        items.append({"id": str(c.id), "label": label, "is_business": c.is_business})
    return {"items": items}


@customers_bp.post("/create-json")
@login_required
def create_customer_json():
    data = request.get_json(silent=True) or {}
    name = (data.get("full_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not phone:
        return jsonify({"ok": False, "error": "Name and phone are required"}), 400
    customer = Customer(full_name=name, phone=phone, email=email or None, preferred_language="en")
    db.session.add(customer)
    db.session.commit()
    return jsonify({"ok": True, "id": str(customer.id), "label": f"{customer.full_name} · {phone}"})


@customers_bp.get("/devices/<uuid:device_id>")
@login_required
def device_detail(device_id):
    """Dedicated device detail page showing all structured data and lookup history."""
    device = Device.query.filter(Device.id == device_id, Device.deleted_at.is_(None)).first_or_404()
    customer = device.customer
    tickets = Ticket.query.filter(Ticket.device_id == device.id, Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).all()

    # Parse stored IMEI lookup data
    lookup_data = None
    if device.imei_lookup_data:
        try:
            import json
            lookup_data = json.loads(device.imei_lookup_data)
        except (ValueError, TypeError):
            lookup_data = None

    # Load related intakes
    intakes = IntakeSubmission.query.filter(
        IntakeSubmission.device_id == device.id,
        IntakeSubmission.deleted_at.is_(None)
    ).order_by(IntakeSubmission.created_at.desc()).all()

    return render_template(
        "customers/device_detail.html",
        device=device,
        customer=customer,
        tickets=tickets,
        intakes=intakes,
        lookup_data=lookup_data,
    )


@customers_bp.post("/devices/<uuid:device_id>/lookup")
@login_required
def device_lookup(device_id):
    """Trigger IMEI/serial lookup for a device and persist results."""
    from app.services.permission_service import can_lookup_imei
    if not can_lookup_imei():
        return jsonify({"ok": False, "error": "Permission denied"}), 403
    device = db.session.get(Device, device_id)
    if not device:
        return jsonify({"ok": False, "error": "Device not found"}), 404
    from app.services.imei_lookup_service import is_imei_lookup_configured, lookup_imei, lookup_serial, cache_lookup_result
    if not is_imei_lookup_configured():
        return jsonify({"ok": False, "error": "Lookup service not configured"})
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or device.imei or device.serial_number or "").strip()
    brand_hint = (data.get("brand_hint") or device.brand or "").strip()
    if not identifier:
        return jsonify({"ok": False, "error": "No IMEI or serial number available"})
    # Determine if this is a serial or IMEI lookup
    if len(identifier) >= 14 and identifier.isdigit():
        result = lookup_imei(identifier, brand_hint=brand_hint)
    else:
        result = lookup_serial(identifier, brand_hint=brand_hint)
    if result.success:
        cache_lookup_result(device, result)
        db.session.commit()
    return jsonify({"ok": result.success, **result.to_dict()})


@customers_bp.route("/<uuid:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.deleted_at.is_(None)).first_or_404()
    form = CustomerEditForm(obj=customer)

    if form.validate_on_submit():
        form.populate_obj(customer)
        # Clear business fields if switched to individual
        if customer.customer_type == "individual":
            customer.company_name = None
            customer.cif_vat = None
        db.session.commit()
        flash("Customer updated", "success")
        return redirect(url_for("customers.customer_detail", customer_id=customer.id))

    return render_template("customers/edit.html", form=form, customer=customer)


@customers_bp.get("/<uuid:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.deleted_at.is_(None)).first_or_404()

    devices = Device.query.filter(Device.customer_id == customer.id, Device.deleted_at.is_(None)).all()
    tickets = Ticket.query.filter(Ticket.customer_id == customer.id, Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).all()

    fitted_parts = {}
    has_reservation_table = inspect(db.engine).has_table("stock_reservations")
    if has_reservation_table:
        for ticket in tickets:
            reservations = StockReservation.query.filter_by(ticket_id=ticket.id).all()
            fitted_parts[str(ticket.id)] = [f"{r.part.sku} ({r.quantity})" for r in reservations if r.part]

    customer_choices = Customer.query.filter(Customer.deleted_at.is_(None), Customer.id != customer.id).order_by(Customer.full_name.asc()).all()

    # Phase 17: Warranty information per ticket
    ticket_warranties = {}
    try:
        for ticket in tickets:
            w = TicketWarranty.query.filter_by(ticket_id=ticket.id, deleted_at=None).first()
            if w:
                ticket_warranties[str(ticket.id)] = w
    except Exception:
        ticket_warranties = {}

    return render_template("customers/detail.html", customer=customer, devices=devices, tickets=tickets, fitted_parts=fitted_parts, customer_choices=customer_choices, ticket_warranties=ticket_warranties)
