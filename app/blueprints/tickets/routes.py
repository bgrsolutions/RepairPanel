import uuid
from datetime import datetime

from flask import Blueprint, flash, render_template, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.diagnostic_forms import DiagnosticForm
from app.forms.inventory_forms import StockReservationForm
from app.forms.ticket_forms import TicketCreateForm
from app.forms.ticket_note_forms import TicketAssignmentForm, TicketNoteForm
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    Part,
    PartOrder,
    Quote,
    StockReservation,
    Ticket,
    TicketNote,
    User,
)
from app.services.audit_service import log_action
from app.services.inventory_service import reserve_stock_for_ticket
from app.services.quote_service import compute_quote_totals
from app.utils.ticketing import generate_ticket_number


tickets_bp = Blueprint("tickets", __name__, url_prefix="/tickets")


def _technician_choices(ticket: Ticket):
    users = User.query.filter(User.deleted_at.is_(None), User.is_active.is_(True)).order_by(User.full_name).all()
    scoped = []
    for u in users:
        is_technician = any(r.name.lower() == "technician" for r in u.roles)
        has_branch = (not u.branches) or any(str(b.id) == str(ticket.branch_id) for b in u.branches)
        if is_technician and has_branch:
            scoped.append((str(u.id), u.full_name))
    return scoped


@tickets_bp.get("/")
@login_required
def list_tickets():
    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).all()
    return render_template("tickets/list.html", tickets=tickets)


@tickets_bp.get("/<uuid:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    timeline_placeholder = [
        {"time": ticket.created_at, "event": "Ticket created", "by": "System"},
        {"time": ticket.updated_at, "event": "Latest update", "by": "Staff"},
    ]

    ticket_uuid = uuid.UUID(str(ticket.id))

    diagnosis_entries = (
        Diagnostic.query.filter_by(ticket_id=ticket_uuid)
        .order_by(Diagnostic.version.desc(), Diagnostic.created_at.desc())
        .all()
    )
    latest_diagnosis = diagnosis_entries[0] if diagnosis_entries else None

    diagnostic_form = DiagnosticForm()
    if latest_diagnosis:
        diagnostic_form.customer_reported_fault.data = latest_diagnosis.customer_reported_fault
        diagnostic_form.technician_diagnosis.data = latest_diagnosis.technician_diagnosis
        diagnostic_form.recommended_repair.data = latest_diagnosis.recommended_repair
        diagnostic_form.estimated_labour.data = latest_diagnosis.estimated_labour
        diagnostic_form.repair_notes.data = latest_diagnosis.repair_notes

    quotes = (
        Quote.query.filter_by(ticket_id=ticket_uuid)
        .order_by(Quote.version.desc(), Quote.created_at.desc())
        .all()
    )
    quote_summaries = []
    for quote in quotes:
        option_totals, quote_total = compute_quote_totals(quote)
        quote_summaries.append({"quote": quote, "option_totals": option_totals, "quote_total": quote_total})

    assignment_form = TicketAssignmentForm()
    assignment_form.assigned_technician_id.choices = _technician_choices(ticket)
    if ticket.assigned_technician_id:
        assignment_form.assigned_technician_id.data = str(ticket.assigned_technician_id)

    note_form = TicketNoteForm()
    notes = TicketNote.query.filter_by(ticket_id=ticket_uuid).order_by(TicketNote.created_at.desc()).all()

    reservation_form = StockReservationForm()
    reservation_form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter_by(is_active=True).order_by(Part.name).all()]
    # use all locations in ticket branch for reservations
    from app.models import StockLocation

    reservation_form.location_id.choices = [
        (str(loc.id), f"{loc.code} - {loc.name}")
        for loc in StockLocation.query.filter_by(branch_id=ticket.branch_id).order_by(StockLocation.name).all()
    ]
    reservations = StockReservation.query.filter_by(ticket_id=ticket_uuid).order_by(StockReservation.created_at.desc()).all()

    orders = PartOrder.query.filter_by(ticket_id=ticket_uuid).order_by(PartOrder.created_at.desc()).all()

    return render_template(
        "tickets/detail.html",
        ticket=ticket,
        timeline_placeholder=timeline_placeholder,
        diagnosis_entries=diagnosis_entries,
        latest_diagnosis=latest_diagnosis,
        diagnostic_form=diagnostic_form,
        quote_summaries=quote_summaries,
        assignment_form=assignment_form,
        note_form=note_form,
        notes=notes,
        reservation_form=reservation_form,
        reservations=reservations,
        orders=orders,
    )


@tickets_bp.post("/<uuid:ticket_id>/assign")
@login_required
def assign_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketAssignmentForm()
    form.assigned_technician_id.choices = _technician_choices(ticket)
    if form.validate_on_submit():
        technician_id = uuid.UUID(str(form.assigned_technician_id.data))
        technician = db.session.get(User, technician_id)
        ticket.assigned_technician_id = uuid.UUID(str(technician.id)) if technician else None
        db.session.commit()
        flash(_("Technician assignment updated"), "success")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    flash(_("Invalid assignment request"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/notes")
@login_required
def add_note(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    ticket_uuid = uuid.UUID(str(ticket.id))
    form = TicketNoteForm()
    if form.validate_on_submit():
        note = TicketNote(
            ticket_id=ticket_uuid,
            author_user_id=uuid.UUID(str(current_user.id)),
            note_type=form.note_type.data,
            content=form.content.data,
        )
        db.session.add(note)
        db.session.commit()
        flash(_("Note added"), "success")
    else:
        flash(_("Invalid note submission"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/reserve")
@login_required
def reserve_part(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    ticket_uuid = uuid.UUID(str(ticket.id))
    form = StockReservationForm()
    form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter_by(is_active=True).all()]
    from app.models import StockLocation

    form.location_id.choices = [(str(loc.id), f"{loc.code} - {loc.name}") for loc in StockLocation.query.filter_by(branch_id=ticket.branch_id).all()]

    if form.validate_on_submit():
        try:
            reserve_stock_for_ticket(
                ticket_id=ticket_uuid,
                part_id=uuid.UUID(str(form.part_id.data)),
                branch_id=uuid.UUID(str(ticket.branch_id)),
                location_id=uuid.UUID(str(form.location_id.data)),
                quantity=form.quantity.data,
            )
            db.session.commit()
            flash(_("Part reserved"), "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    else:
        flash(_("Invalid reservation request"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.get("/board")
@login_required
def repair_board():
    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).order_by(Ticket.created_at.desc()).all()
    columns = [
        "New",
        "Awaiting Diagnosis",
        "Awaiting Quote Approval",
        "Awaiting Parts",
        "In Repair",
        "Testing / QA",
        "Ready for Collection",
    ]

    grouped = {status: [] for status in columns}
    for ticket in tickets:
        status = ticket.internal_status if ticket.internal_status in grouped else "New"
        grouped[status].append(ticket)

    return render_template("tickets/board.html", grouped=grouped, columns=columns, now=datetime.utcnow())


@tickets_bp.get("/my-queue")
@login_required
def my_queue():
    assigned = (
        Ticket.query.filter(Ticket.deleted_at.is_(None), Ticket.assigned_technician_id == current_user.id)
        .order_by(Ticket.created_at.asc())
        .all()
    )

    grouped = {
        "Awaiting Diagnosis": [t for t in assigned if t.internal_status == "Awaiting Diagnosis"],
        "In Repair": [t for t in assigned if t.internal_status == "In Repair"],
        "Testing / QA": [t for t in assigned if t.internal_status in {"Testing / QA", "Testing", "QA"}],
        "Other": [
            t
            for t in assigned
            if t.internal_status not in {"Awaiting Diagnosis", "In Repair", "Testing / QA", "Testing", "QA"}
        ],
    }

    return render_template("tickets/my_queue.html", grouped=grouped)


@tickets_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_ticket():
    form = TicketCreateForm()
    form.customer_id.choices = [(str(c.id), c.full_name) for c in Customer.query.order_by(Customer.full_name).all()]
    form.device_id.choices = [
        (str(d.id), f"{d.brand} {d.model} ({d.serial_number or 'N/A'})") for d in Device.query.order_by(Device.brand).all()
    ]
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]

    if form.validate_on_submit():
        branch = db.session.get(Branch, form.branch_id.data)
        sequence = Ticket.query.count() + 1
        ticket = Ticket(
            ticket_number=generate_ticket_number(branch.code, sequence),
            branch_id=form.branch_id.data,
            customer_id=form.customer_id.data,
            device_id=form.device_id.data,
            priority=form.priority.data,
            internal_status="New",
            customer_status="Received",
        )
        db.session.add(ticket)
        db.session.commit()
        log_action("ticket.create", "Ticket", str(ticket.id), details={"ticket_number": ticket.ticket_number})
        flash(_("Ticket created"), "success")
        return redirect(url_for("tickets.list_tickets"))

    return render_template("tickets/new.html", form=form)
