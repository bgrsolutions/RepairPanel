from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

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
