import secrets
import uuid as _uuid
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms.booking_forms import BookingConvertForm, BookingForm
from app.models import Booking, Branch, Customer, Device, RepairService, Ticket, TicketNote, PortalToken
from app.services.audit_service import log_action
from app.services.booking_service import (
    InvalidTransitionError,
    convert_booking_to_ticket,
    get_intake_queue,
    status_label,
    transition_status,
)
from app.services.permission_service import (
    can_convert_booking,
    can_manage_bookings,
    can_view_bookings,
)
from app.utils.permissions import permission_required
from app.utils.ticketing import generate_ticket_number

bookings_bp = Blueprint("bookings", __name__, url_prefix="/bookings")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _location_choices():
    branches = Branch.query.filter(
        Branch.deleted_at.is_(None), Branch.is_active.is_(True)
    ).order_by(Branch.name).all()
    return [(str(b.id), f"{b.name} ({b.code})") for b in branches]


def _service_choices():
    services = RepairService.query.filter(
        RepairService.is_active.is_(True)
    ).order_by(RepairService.name).all()
    choices = [("", _("-- None --"))]
    choices.extend((str(s.id), s.name) for s in services)
    return choices


def _device_choices(customer_id=None):
    """Return device choices for a given customer."""
    choices = [("", _("-- Select Device --"))]
    if customer_id:
        try:
            cid = _uuid.UUID(str(customer_id))
        except (ValueError, TypeError):
            return choices
        devices = Device.query.filter(
            Device.customer_id == cid, Device.deleted_at.is_(None)
        ).order_by(Device.brand).all()
        choices.extend(
            (str(d.id), f"{d.brand} {d.model} ({d.serial_number or 'N/A'})")
            for d in devices
        )
    return choices


def _get_booking_or_404(booking_id):
    try:
        bid = _uuid.UUID(str(booking_id))
    except (ValueError, TypeError):
        abort(404)
    booking = db.session.get(Booking, bid)
    if not booking:
        abort(404)
    return booking


# ---------------------------------------------------------------------------
# Status badge helper (exposed to templates)
# ---------------------------------------------------------------------------

@bookings_bp.app_context_processor
def booking_context():
    return {"booking_status_label": status_label}


# ---------------------------------------------------------------------------
# Customer search (JSON) — reuses same pattern as intake/tickets
# ---------------------------------------------------------------------------

@bookings_bp.get("/customer-search")
@login_required
def booking_customer_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    like = f"%{q}%"
    customers = (
        Customer.query.filter(
            Customer.deleted_at.is_(None),
            or_(
                Customer.full_name.ilike(like),
                Customer.phone.ilike(like),
                Customer.email.ilike(like),
            ),
        )
        .order_by(Customer.full_name)
        .limit(25)
        .all()
    )
    items = []
    for c in customers:
        detail = c.phone or c.email or ""
        items.append({
            "id": str(c.id),
            "label": f"{c.full_name} · {detail}" if detail else c.full_name,
            "name": c.full_name,
            "phone": c.phone or "",
            "email": c.email or "",
        })
    return jsonify({"items": items})


# ---------------------------------------------------------------------------
# Customer create (JSON) — inline customer creation from booking form
# ---------------------------------------------------------------------------

@bookings_bp.post("/customer-create")
@login_required
@permission_required(can_manage_bookings)
def booking_customer_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()

    if not name:
        return jsonify({"ok": False, "error": _("Customer name is required")}), 400

    # Duplicate detection: check email first, then phone
    if email:
        existing = Customer.query.filter(
            Customer.deleted_at.is_(None),
            Customer.email.ilike(email),
        ).first()
        if existing:
            return jsonify({
                "ok": True,
                "id": str(existing.id),
                "name": existing.full_name,
                "phone": existing.phone or "",
                "email": existing.email or "",
                "existing": True,
            })

    if phone:
        existing = Customer.query.filter(
            Customer.deleted_at.is_(None),
            Customer.phone == phone,
        ).first()
        if existing:
            return jsonify({
                "ok": True,
                "id": str(existing.id),
                "name": existing.full_name,
                "phone": existing.phone or "",
                "email": existing.email or "",
                "existing": True,
            })

    customer = Customer(
        full_name=name,
        phone=phone or None,
        email=email or None,
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify({
        "ok": True,
        "id": str(customer.id),
        "name": customer.full_name,
        "phone": customer.phone or "",
        "email": customer.email or "",
        "existing": False,
    })


# ---------------------------------------------------------------------------
# Customer devices (JSON) — load devices for selected customer
# ---------------------------------------------------------------------------

@bookings_bp.get("/customer/<uuid:customer_id>/devices")
@login_required
def booking_customer_devices(customer_id):
    devices = Device.query.filter(
        Device.customer_id == customer_id, Device.deleted_at.is_(None)
    ).order_by(Device.brand).all()
    return jsonify([
        {"id": str(d.id), "label": f"{d.brand} {d.model} ({d.serial_number or 'N/A'})"}
        for d in devices
    ])


# ---------------------------------------------------------------------------
# Intake Queue / Booking List
# ---------------------------------------------------------------------------

@bookings_bp.get("/")
@login_required
@permission_required(can_view_bookings)
def list_bookings():
    date_str = request.args.get("date", "")
    location_id = request.args.get("location_id", "")
    status_filter = request.args.get("status", "")
    view_mode = request.args.get("view", "day")  # day or queue

    if date_str:
        try:
            view_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            view_date = datetime.utcnow().date()
    else:
        view_date = datetime.utcnow().date()

    branches = Branch.query.filter(
        Branch.deleted_at.is_(None), Branch.is_active.is_(True)
    ).order_by(Branch.name).all()

    if view_mode == "queue":
        # Intake queue mode: today + upcoming + overdue
        queue = get_intake_queue(
            location_id=location_id or None,
            status_filter=status_filter or None,
        )
        return render_template(
            "bookings/intake_queue.html",
            queue=queue,
            branches=branches,
            view_date=view_date,
            selected_location=location_id,
            selected_status=status_filter,
            all_statuses=Booking.ALL_STATUSES,
            status_label=status_label,
        )

    # Day view mode (default)
    day_start = datetime.combine(view_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = Booking.query.filter(
        Booking.start_time >= day_start, Booking.start_time < day_end
    )
    if location_id:
        q = q.filter(Booking.location_id == location_id)
    if status_filter:
        q = q.filter(Booking.status == status_filter)
    bookings = q.order_by(Booking.start_time).all()

    # Build week view dates
    week_start = view_date - timedelta(days=view_date.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(7)]

    return render_template(
        "bookings/list.html",
        bookings=bookings,
        branches=branches,
        view_date=view_date,
        week_dates=week_dates,
        selected_location=location_id,
        selected_status=status_filter,
        all_statuses=Booking.ALL_STATUSES,
        status_label=status_label,
    )


# ---------------------------------------------------------------------------
# Create Booking
# ---------------------------------------------------------------------------

@bookings_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_bookings)
def create_booking():
    form = BookingForm()
    form.location_id.choices = _location_choices()
    form.repair_service_id.choices = _service_choices()
    customer_id = form.customer_id.data or request.args.get("customer_id", "")
    form.device_id.choices = _device_choices(customer_id)

    if form.validate_on_submit():
        booking = Booking(
            location_id=_uuid.UUID(form.location_id.data),
            customer_id=_uuid.UUID(form.customer_id.data) if form.customer_id.data else None,
            device_id=_uuid.UUID(form.device_id.data) if form.device_id.data else None,
            repair_service_id=_uuid.UUID(form.repair_service_id.data) if form.repair_service_id.data else None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            status=form.status.data or "new",
            notes=(form.notes.data or "").strip() or None,
            staff_notes=(form.staff_notes.data or "").strip() or None,
            customer_name=(form.customer_name.data or "").strip() or None,
            customer_phone=(form.customer_phone.data or "").strip() or None,
            customer_email=(form.customer_email.data or "").strip() or None,
            device_description=(form.device_description.data or "").strip() or None,
        )
        db.session.add(booking)
        db.session.commit()
        flash(_("Booking created"), "success")
        return redirect(url_for("bookings.list_bookings", date=booking.start_time.strftime("%Y-%m-%d")))
    return render_template("bookings/form.html", form=form, editing=False)


# ---------------------------------------------------------------------------
# Booking Detail
# ---------------------------------------------------------------------------

@bookings_bp.get("/<booking_id>")
@login_required
@permission_required(can_view_bookings)
def booking_detail(booking_id):
    booking = _get_booking_or_404(booking_id)
    return render_template(
        "bookings/detail.html",
        booking=booking,
        status_label=status_label,
        can_convert=can_convert_booking(),
        can_manage=can_manage_bookings(),
    )


# ---------------------------------------------------------------------------
# Edit Booking
# ---------------------------------------------------------------------------

@bookings_bp.route("/<booking_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_bookings)
def edit_booking(booking_id):
    booking = _get_booking_or_404(booking_id)
    form = BookingForm(obj=booking)
    form.location_id.choices = _location_choices()
    form.repair_service_id.choices = _service_choices()
    customer_id = form.customer_id.data or (str(booking.customer_id) if booking.customer_id else "")
    form.device_id.choices = _device_choices(customer_id)

    if request.method == "GET":
        form.location_id.data = str(booking.location_id)
        form.repair_service_id.data = str(booking.repair_service_id) if booking.repair_service_id else ""
        form.customer_id.data = str(booking.customer_id) if booking.customer_id else ""
        form.device_id.data = str(booking.device_id) if booking.device_id else ""
        form.customer_name.data = booking.customer_name or (booking.customer.full_name if booking.customer else "")
        form.customer_phone.data = booking.customer_phone or (booking.customer.phone if booking.customer else "")
        form.customer_email.data = booking.customer_email or (booking.customer.email if booking.customer else "")
        form.device_description.data = booking.device_description or ""
        form.staff_notes.data = booking.staff_notes or ""

    if form.validate_on_submit():
        booking.location_id = _uuid.UUID(str(form.location_id.data))
        cid = str(form.customer_id.data).strip() if form.customer_id.data else ""
        booking.customer_id = _uuid.UUID(cid) if cid else None
        did = str(form.device_id.data).strip() if form.device_id.data else ""
        booking.device_id = _uuid.UUID(did) if did else None
        sid = str(form.repair_service_id.data).strip() if form.repair_service_id.data else ""
        booking.repair_service_id = _uuid.UUID(sid) if sid else None
        booking.start_time = form.start_time.data
        booking.end_time = form.end_time.data
        booking.status = form.status.data
        booking.notes = (form.notes.data or "").strip() or None
        booking.staff_notes = (form.staff_notes.data or "").strip() or None
        booking.customer_name = (form.customer_name.data or "").strip() or None
        booking.customer_phone = (form.customer_phone.data or "").strip() or None
        booking.customer_email = (form.customer_email.data or "").strip() or None
        booking.device_description = (form.device_description.data or "").strip() or None
        db.session.commit()
        flash(_("Booking updated"), "success")
        return redirect(url_for("bookings.booking_detail", booking_id=booking.id))
    return render_template("bookings/form.html", form=form, booking=booking, editing=True)


# ---------------------------------------------------------------------------
# Status Action Routes (POST only)
# ---------------------------------------------------------------------------

@bookings_bp.post("/<booking_id>/confirm")
@login_required
@permission_required(can_manage_bookings)
def confirm_booking(booking_id):
    booking = _get_booking_or_404(booking_id)
    try:
        transition_status(booking, Booking.STATUS_CONFIRMED, str(current_user.id))
        db.session.commit()
        flash(_("Booking confirmed"), "success")
    except InvalidTransitionError:
        flash(_("Cannot confirm this booking"), "warning")
    return redirect(url_for("bookings.booking_detail", booking_id=booking.id))


@bookings_bp.post("/<booking_id>/arrive")
@login_required
@permission_required(can_manage_bookings)
def mark_arrived(booking_id):
    booking = _get_booking_or_404(booking_id)
    try:
        transition_status(booking, Booking.STATUS_ARRIVED, str(current_user.id))
        db.session.commit()
        flash(_("Customer marked as arrived"), "success")
    except InvalidTransitionError:
        flash(_("Cannot mark this booking as arrived"), "warning")
    return redirect(url_for("bookings.booking_detail", booking_id=booking.id))


@bookings_bp.post("/<booking_id>/no-show")
@login_required
@permission_required(can_manage_bookings)
def mark_no_show(booking_id):
    booking = _get_booking_or_404(booking_id)
    try:
        transition_status(booking, Booking.STATUS_NO_SHOW, str(current_user.id))
        db.session.commit()
        flash(_("Booking marked as no-show"), "success")
    except InvalidTransitionError:
        flash(_("Cannot mark this booking as no-show"), "warning")
    return redirect(url_for("bookings.booking_detail", booking_id=booking.id))


@bookings_bp.post("/<booking_id>/cancel")
@login_required
@permission_required(can_manage_bookings)
def cancel_booking(booking_id):
    booking = _get_booking_or_404(booking_id)
    try:
        transition_status(booking, Booking.STATUS_CANCELLED, str(current_user.id))
        db.session.commit()
        flash(_("Booking cancelled"), "success")
    except InvalidTransitionError:
        flash(_("Cannot cancel this booking"), "warning")
    return redirect(url_for("bookings.booking_detail", booking_id=booking.id))


# ---------------------------------------------------------------------------
# Assisted Conversion: Booking → Ticket
# ---------------------------------------------------------------------------

@bookings_bp.route("/<booking_id>/convert", methods=["GET", "POST"])
@login_required
@permission_required(can_convert_booking)
def convert_to_ticket(booking_id):
    booking = _get_booking_or_404(booking_id)

    # Guard: already converted
    if booking.converted_ticket_id is not None:
        flash(_("This booking has already been converted to a ticket"), "warning")
        return redirect(url_for("bookings.booking_detail", booking_id=booking.id))

    # Guard: must be in a convertible state
    if not booking.can_transition_to(Booking.STATUS_CONVERTED):
        flash(_("This booking cannot be converted in its current state"), "warning")
        return redirect(url_for("bookings.booking_detail", booking_id=booking.id))

    # Guard: must have a customer
    if not booking.customer_id:
        flash(_("A customer must be assigned to the booking before conversion"), "warning")
        return redirect(url_for("bookings.edit_booking", booking_id=booking.id))

    form = BookingConvertForm()
    customer_id = str(booking.customer_id) if booking.customer_id else ""
    form.device_id.choices = _device_choices(customer_id)
    form.repair_service_id.choices = _service_choices()

    if request.method == "GET":
        # Prefill from booking data
        if booking.device_id:
            form.device_id.data = str(booking.device_id)
        form.repair_service_id.data = str(booking.repair_service_id) if booking.repair_service_id else ""
        form.issue_summary.data = booking.notes or ""

    if form.validate_on_submit():
        try:
            branch = db.session.get(Branch, booking.location_id)
            branch_code = branch.code if branch else "XX"
            sequence = Ticket.query.count() + 1
            ticket_number = generate_ticket_number(branch_code, sequence)

            # Update device on booking if changed
            device_id = _uuid.UUID(form.device_id.data) if form.device_id.data else None
            if device_id:
                booking.device_id = device_id

            # Update service if changed
            svc_id = form.repair_service_id.data
            if svc_id:
                booking.repair_service_id = _uuid.UUID(svc_id)

            ticket = convert_booking_to_ticket(
                booking=booking,
                branch_code=branch_code,
                user_id=str(current_user.id),
                ticket_number=ticket_number,
                issue_summary=form.issue_summary.data,
                device_condition=form.device_condition.data,
                accessories=form.accessories.data,
            )
            db.session.commit()
            flash(_("Ticket %(number)s created from booking", number=ticket.ticket_number), "success")
            # Redirect to the new ticket for seamless workflow continuation
            return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))
        except (InvalidTransitionError, ValueError) as e:
            db.session.rollback()
            flash(str(e), "danger")
        except Exception:
            db.session.rollback()
            flash(_("An error occurred during conversion"), "danger")

    return render_template(
        "bookings/convert.html",
        form=form,
        booking=booking,
        status_label=status_label,
    )
