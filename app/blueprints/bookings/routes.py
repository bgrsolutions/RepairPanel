import uuid as _uuid
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.booking_forms import BookingForm
from app.models import Booking, Branch, Customer, RepairService

bookings_bp = Blueprint("bookings", __name__, url_prefix="/bookings")


def _location_choices():
    branches = Branch.query.filter(Branch.deleted_at.is_(None), Branch.is_active.is_(True)).order_by(Branch.name).all()
    return [(str(b.id), f"{b.name} ({b.code})") for b in branches]


def _service_choices():
    services = RepairService.query.filter(RepairService.is_active.is_(True)).order_by(RepairService.name).all()
    choices = [("", "-- None --")]
    choices.extend((str(s.id), s.name) for s in services)
    return choices


@bookings_bp.get("/")
@login_required
def list_bookings():
    date_str = request.args.get("date", "")
    location_id = request.args.get("location_id", "")

    if date_str:
        try:
            view_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            view_date = datetime.utcnow().date()
    else:
        view_date = datetime.utcnow().date()

    day_start = datetime.combine(view_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    q = Booking.query.filter(Booking.start_time >= day_start, Booking.start_time < day_end)
    if location_id:
        q = q.filter(Booking.location_id == location_id)
    bookings = q.order_by(Booking.start_time).all()

    branches = Branch.query.filter(Branch.deleted_at.is_(None), Branch.is_active.is_(True)).order_by(Branch.name).all()

    # Build week view dates
    week_start = view_date - timedelta(days=view_date.weekday())  # Monday
    week_dates = [week_start + timedelta(days=i) for i in range(7)]

    return render_template(
        "bookings/list.html",
        bookings=bookings,
        branches=branches,
        view_date=view_date,
        week_dates=week_dates,
        selected_location=location_id,
    )


@bookings_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_booking():
    form = BookingForm()
    form.location_id.choices = _location_choices()
    form.repair_service_id.choices = _service_choices()
    if form.validate_on_submit():
        booking = Booking(
            location_id=_uuid.UUID(form.location_id.data),
            customer_id=_uuid.UUID(form.customer_id.data) if form.customer_id.data else None,
            repair_service_id=_uuid.UUID(form.repair_service_id.data) if form.repair_service_id.data else None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            status=form.status.data,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(booking)
        db.session.commit()
        flash(_("Booking created"), "success")
        return redirect(url_for("bookings.list_bookings", date=booking.start_time.strftime("%Y-%m-%d")))
    return render_template("bookings/form.html", form=form, editing=False)


@bookings_bp.route("/<booking_id>/edit", methods=["GET", "POST"])
@login_required
def edit_booking(booking_id):
    try:
        _bid = _uuid.UUID(str(booking_id))
    except (ValueError, TypeError):
        abort(404)
    booking = db.session.get(Booking, _bid)
    if not booking:
        abort(404)
    form = BookingForm(obj=booking)
    form.location_id.choices = _location_choices()
    form.repair_service_id.choices = _service_choices()
    if request.method == "GET":
        form.location_id.data = str(booking.location_id)
        form.repair_service_id.data = str(booking.repair_service_id) if booking.repair_service_id else ""
        form.customer_id.data = str(booking.customer_id) if booking.customer_id else ""
    if form.validate_on_submit():
        booking.location_id = _uuid.UUID(form.location_id.data)
        booking.customer_id = _uuid.UUID(form.customer_id.data) if form.customer_id.data else None
        booking.repair_service_id = _uuid.UUID(form.repair_service_id.data) if form.repair_service_id.data else None
        booking.start_time = form.start_time.data
        booking.end_time = form.end_time.data
        booking.status = form.status.data
        booking.notes = (form.notes.data or "").strip() or None
        db.session.commit()
        flash(_("Booking updated"), "success")
        return redirect(url_for("bookings.list_bookings", date=booking.start_time.strftime("%Y-%m-%d")))
    return render_template("bookings/form.html", form=form, booking=booking, editing=True)
