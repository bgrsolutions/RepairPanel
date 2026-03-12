from datetime import datetime

from flask import Blueprint, flash, render_template, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.ticket_forms import TicketCreateForm
from app.models import Branch, Customer, Device, Ticket
from app.services.audit_service import log_action
from app.utils.ticketing import generate_ticket_number


tickets_bp = Blueprint("tickets", __name__, url_prefix="/tickets")


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

    return render_template("tickets/detail.html", ticket=ticket, timeline_placeholder=timeline_placeholder)


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
