import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.forms.diagnostic_forms import DiagnosticForm
from app.forms.inventory_forms import StockReservationForm
from app.forms.ticket_forms import TicketCreateForm
from app.forms.ticket_note_forms import TicketAssignmentForm, TicketMetaForm, TicketNoteForm, TicketStatusForm
from app.models import Branch, Customer, Device, Diagnostic, Part, PartOrder, Quote, RepairChecklist, StockReservation, Ticket, TicketNote, User
from app.services.audit_service import log_action
from app.services.inventory_service import reserve_stock_for_ticket
from app.services.quote_service import compute_quote_totals
from app.utils.ticketing import default_sla_target, generate_ticket_number, is_ticket_overdue, normalize_ticket_status, ticket_age_days


tickets_bp = Blueprint("tickets", __name__, url_prefix="/tickets")


def _technician_choices(branch_id=None):
    users = User.query.filter(User.deleted_at.is_(None), User.is_active.is_(True)).order_by(User.full_name).all()
    scoped = [("", "-- Unassigned --")]
    for u in users:
        is_technician = any(r.name.lower() in {"technician", "manager", "admin", "super admin"} for r in u.roles)
        has_branch = (branch_id is None) or (not u.branches) or any(str(b.id) == str(branch_id) for b in u.branches)
        if is_technician and has_branch:
            scoped.append((str(u.id), u.full_name))
    return scoped


def _sync_assignment_status(ticket: Ticket):
    normalized = normalize_ticket_status(ticket.internal_status)
    if normalized == Ticket.STATUS_UNASSIGNED and ticket.assigned_technician_id:
        ticket.internal_status = Ticket.STATUS_ASSIGNED
    elif normalized == Ticket.STATUS_ASSIGNED and not ticket.assigned_technician_id:
        ticket.internal_status = Ticket.STATUS_UNASSIGNED


def _ticket_has_overdue_parts(ticket: Ticket, now: datetime | None = None) -> bool:
    current = now or datetime.utcnow()
    orders = PartOrder.query.filter(PartOrder.ticket_id == ticket.id, PartOrder.estimated_arrival_at.is_not(None)).all()
    return any(o.status not in {"received", "cancelled"} and o.estimated_arrival_at < current for o in orders)


def _open_ticket_orders(ticket: Ticket):
    return PartOrder.query.filter(PartOrder.ticket_id == ticket.id).all()


def _ticket_waiting_on_parts(ticket: Ticket) -> bool:
    normalized = normalize_ticket_status(ticket.internal_status)
    if normalized == Ticket.STATUS_AWAITING_PARTS:
        return True
    return any(o.status not in {"received", "cancelled"} for o in _open_ticket_orders(ticket))


def _ticket_next_parts_eta(ticket: Ticket) -> datetime | None:
    open_orders = [o for o in _open_ticket_orders(ticket) if o.status not in {"received", "cancelled"} and o.estimated_arrival_at]
    if not open_orders:
        return None
    return min(o.estimated_arrival_at for o in open_orders)


@tickets_bp.get("/")
@login_required
def list_tickets():
    now = datetime.utcnow()
    status = (request.args.get("status") or "").strip()
    branch_id = (request.args.get("branch_id") or "").strip()
    technician_id = (request.args.get("technician_id") or "").strip()
    date_range = (request.args.get("date_range") or "").strip()
    sort = (request.args.get("sort") or "newest")

    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()

    def in_range(ticket):
        if date_range == "today":
            return ticket.created_at.date() == now.date()
        if date_range == "last_week":
            return ticket.created_at >= (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7))
        if date_range == "this_month":
            return ticket.created_at.year == now.year and ticket.created_at.month == now.month
        return True

    filtered = []
    for t in tickets:
        n = normalize_ticket_status(t.internal_status)
        if status != "archived" and n == Ticket.STATUS_ARCHIVED:
            continue
        if status == "archived" and n != Ticket.STATUS_ARCHIVED:
            continue
        if status == "overdue" and not is_ticket_overdue(t, now):
            continue
        if status == "awaiting_parts" and not _ticket_waiting_on_parts(t):
            continue
        if status == "assigned" and not t.assigned_technician_id:
            continue
        if status == "unassigned" and t.assigned_technician_id:
            continue
        if status == "in_repair" and n not in {Ticket.STATUS_IN_REPAIR, Ticket.STATUS_TESTING_QA}:
            continue
        if status == "ready_for_collection" and n != Ticket.STATUS_READY_FOR_COLLECTION:
            continue
        if branch_id and str(t.branch_id) != branch_id:
            continue
        if technician_id and str(t.assigned_technician_id or "") != technician_id:
            continue
        if not in_range(t):
            continue
        filtered.append(t)

    if sort == "oldest":
        filtered.sort(key=lambda t: t.created_at)
    elif sort == "sla_due":
        filtered.sort(key=lambda t: t.sla_target_at or datetime.max)
    elif sort == "promise_due":
        filtered.sort(key=lambda t: t.quoted_completion_at or datetime.max)
    else:
        filtered.sort(key=lambda t: t.created_at, reverse=True)

    branches = Branch.query.order_by(Branch.code.asc()).all()
    technicians = [u for u in User.query.filter(User.is_active.is_(True), User.deleted_at.is_(None)).order_by(User.full_name.asc()).all() if any(r.name.lower() in {"technician", "manager", "admin", "super admin"} for r in u.roles)]

    return render_template("tickets/list.html", tickets=filtered, is_ticket_overdue=is_ticket_overdue, ticket_age_days=ticket_age_days, branches=branches, technicians=technicians, filters={"status":status,"branch_id":branch_id,"technician_id":technician_id,"date_range":date_range,"sort":sort})


@tickets_bp.get("/customer-search")
@login_required
def customer_search():
    q=(request.args.get("q") or "").strip()
    if len(q)<2:
        return {"items": []}
    from sqlalchemy import or_
    like=f"%{q}%"
    rows=Customer.query.filter(Customer.deleted_at.is_(None), or_(Customer.full_name.ilike(like), Customer.email.ilike(like), Customer.phone.ilike(like))).order_by(Customer.full_name.asc()).limit(25).all()
    return {"items": [{"id": str(c.id), "label": f"{c.full_name} · {c.phone or c.email or ''}"} for c in rows]}


@tickets_bp.get("/customer/<uuid:customer_id>/devices")
@login_required
def customer_devices(customer_id):
    devices = Device.query.filter(Device.customer_id == customer_id, Device.deleted_at.is_(None)).order_by(Device.brand.asc()).all()
    return jsonify([{"id": str(device.id), "label": f"{device.brand} {device.model} ({device.serial_number or 'N/A'})"} for device in devices])


@tickets_bp.get("/<uuid:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    ticket.internal_status = normalize_ticket_status(ticket.internal_status)
    _sync_assignment_status(ticket)

    ticket_uuid = uuid.UUID(str(ticket.id))
    diagnosis_entries = Diagnostic.query.filter_by(ticket_id=ticket_uuid).order_by(Diagnostic.version.desc(), Diagnostic.created_at.desc()).all()
    latest_diagnosis = diagnosis_entries[0] if diagnosis_entries else None

    diagnostic_form = DiagnosticForm()
    if latest_diagnosis:
        diagnostic_form.customer_reported_fault.data = latest_diagnosis.customer_reported_fault
        diagnostic_form.technician_diagnosis.data = latest_diagnosis.technician_diagnosis
        diagnostic_form.recommended_repair.data = latest_diagnosis.recommended_repair
        diagnostic_form.estimated_labour.data = latest_diagnosis.estimated_labour
        diagnostic_form.repair_notes.data = latest_diagnosis.repair_notes

    quotes = Quote.query.filter_by(ticket_id=ticket_uuid).order_by(Quote.version.desc(), Quote.created_at.desc()).all()
    quote_summaries = []
    igic_rate = Decimal(str(current_app.config.get("DEFAULT_IGIC_RATE", 0.07) or 0.07))
    for quote in quotes:
        option_totals, quote_total = compute_quote_totals(quote)
        tax_total = quote_total * igic_rate
        grand_total = quote_total + tax_total
        latest_approval = sorted(list(quote.approvals), key=lambda a: a.created_at or datetime.min, reverse=True)[0] if quote.approvals else None
        quote_summaries.append(
            {
                "quote": quote,
                "option_totals": option_totals,
                "quote_total": quote_total,
                "tax_total": tax_total,
                "grand_total": grand_total,
                "latest_approval": latest_approval,
            }
        )

    assignment_form = TicketAssignmentForm()
    assignment_form.assigned_technician_id.choices = _technician_choices(ticket.branch_id)
    assignment_form.assigned_technician_id.data = str(ticket.assigned_technician_id) if ticket.assigned_technician_id else ""

    status_form = TicketStatusForm()
    status_form.internal_status.data = normalize_ticket_status(ticket.internal_status)

    meta_form = TicketMetaForm()
    meta_form.issue_summary.data = ticket.issue_summary
    if ticket.quoted_completion_at:
        meta_form.quoted_completion_at.data = ticket.quoted_completion_at

    note_form = TicketNoteForm()
    notes = TicketNote.query.filter_by(ticket_id=ticket_uuid).order_by(TicketNote.created_at.desc()).all()

    reservation_form = StockReservationForm()
    reservation_form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter_by(is_active=True).order_by(Part.name).all()]
    from app.models import StockLocation

    reservation_form.location_id.choices = [(str(loc.id), f"{loc.code} - {loc.name}") for loc in StockLocation.query.filter_by(branch_id=ticket.branch_id).order_by(StockLocation.name).all()]
    reservations = StockReservation.query.filter_by(ticket_id=ticket_uuid).order_by(StockReservation.created_at.desc()).all()
    orders = PartOrder.query.filter_by(ticket_id=ticket_uuid).order_by(PartOrder.created_at.desc()).all()

    has_checklists = sa_inspect(db.engine).has_table("repair_checklists")
    pre_repair_checklist = RepairChecklist.query.filter_by(ticket_id=ticket_uuid, checklist_type="pre_repair").first() if has_checklists else None
    post_repair_checklist = RepairChecklist.query.filter_by(ticket_id=ticket_uuid, checklist_type="post_repair").first() if has_checklists else None

    return render_template(
        "tickets/detail.html",
        ticket=ticket,
        diagnosis_entries=diagnosis_entries,
        latest_diagnosis=latest_diagnosis,
        diagnostic_form=diagnostic_form,
        quote_summaries=quote_summaries,
        igic_rate=igic_rate,
        assignment_form=assignment_form,
        status_form=status_form,
        meta_form=meta_form,
        note_form=note_form,
        notes=notes,
        reservation_form=reservation_form,
        reservations=reservations,
        orders=orders,
        is_overdue=is_ticket_overdue(ticket),
        age_days=ticket_age_days(ticket),
        now=datetime.utcnow(),
        pre_repair_checklist=pre_repair_checklist,
        post_repair_checklist=post_repair_checklist,
    )


@tickets_bp.post("/<uuid:ticket_id>/assign")
@login_required
def assign_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketAssignmentForm()
    form.assigned_technician_id.choices = _technician_choices(ticket.branch_id)
    if form.validate_on_submit():
        previous = ticket.assigned_technician.full_name if ticket.assigned_technician else "Unassigned"
        technician = db.session.get(User, uuid.UUID(str(form.assigned_technician_id.data))) if form.assigned_technician_id.data else None
        ticket.assigned_technician_id = uuid.UUID(str(technician.id)) if technician else None
        _sync_assignment_status(ticket)

        db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content=f"Assignment changed: {previous} → {(technician.full_name if technician else 'Unassigned')}"))
        db.session.commit()
        flash(_("Technician assignment updated"), "success")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    flash(_("Invalid assignment request"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/status")
@login_required
def update_status(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketStatusForm()
    if form.validate_on_submit():
        new_status = normalize_ticket_status(form.internal_status.data)

        # Enforce post-repair checklist completion before marking as completed or ready for collection
        if new_status in (Ticket.STATUS_COMPLETED, Ticket.STATUS_READY_FOR_COLLECTION) and sa_inspect(db.engine).has_table("repair_checklists"):
            post_checklist = RepairChecklist.query.filter_by(
                ticket_id=ticket.id, checklist_type="post_repair"
            ).first()
            if not post_checklist or not post_checklist.is_complete:
                flash(_("Cannot change status to %(status)s: the post-repair checklist must exist and be completed first.", status=new_status.replace("_", " ").title()), "error")
                return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

        previous = ticket.internal_status
        ticket.internal_status = new_status
        db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content=f"Status changed: {previous} → {ticket.internal_status}"))
        db.session.commit()
        flash(_("Ticket status updated"), "success")
    else:
        flash(_("Invalid status update request"), "error")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/meta")
@login_required
def update_ticket_meta(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketMetaForm()
    if form.validate_on_submit():
        ticket.issue_summary = form.issue_summary.data
        ticket.quoted_completion_at = form.quoted_completion_at.data
        db.session.commit()
        flash(_("Ticket details updated"), "success")
    else:
        flash(_("Invalid ticket details update"), "error")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/notes")
@login_required
def add_note(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketNoteForm()
    if form.validate_on_submit():
        db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=uuid.UUID(str(current_user.id)), note_type=form.note_type.data, content=form.content.data))
        db.session.commit()
        flash(_("Note added"), "success")
    else:
        flash(_("Invalid note submission"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))




@tickets_bp.post("/<uuid:ticket_id>/send-update")
@login_required
def send_customer_update(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    content = (request.form.get("content") or "").strip()
    send_email = request.form.get("send_email") == "1"
    if not content:
        flash(_("Update content is required"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=uuid.UUID(str(current_user.id)), note_type="customer_update", content=content))
    if send_email and ticket.customer and ticket.customer.email:
        from app.services.communication_service import send_customer_update_email

        queued = send_customer_update_email(customer_email=ticket.customer.email, customer_name=ticket.customer.full_name, ticket_number=ticket.ticket_number, message=content)
        status_text = "queued" if queued else "intended"
        db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=uuid.UUID(str(current_user.id)), note_type="communication", content=f"Customer update email {status_text} to {ticket.customer.email}"))
    db.session.commit()
    log_action("ticket.send_update", "Ticket", str(ticket.id), details={"send_email": send_email, "has_email": bool(ticket.customer and ticket.customer.email)})
    flash(_("Customer update recorded"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/archive")
@login_required
def archive_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    if ticket.internal_status == Ticket.STATUS_ARCHIVED:
        flash(_("Ticket is already archived"), "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    previous = ticket.internal_status
    ticket.internal_status = Ticket.STATUS_ARCHIVED
    db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content=f"Ticket archived (was: {previous})"))
    db.session.commit()
    log_action("ticket.archive", "Ticket", str(ticket.id), details={"previous_status": previous})
    flash(_("Ticket archived"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/reopen")
@login_required
def reopen_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    if ticket.internal_status not in Ticket.CLOSED_STATUSES:
        flash(_("Only closed or archived tickets can be reopened"), "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    previous = ticket.internal_status
    ticket.internal_status = Ticket.STATUS_UNASSIGNED if not ticket.assigned_technician_id else Ticket.STATUS_ASSIGNED
    db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content=f"Ticket reopened (was: {previous})"))
    db.session.commit()
    log_action("ticket.reopen", "Ticket", str(ticket.id), details={"previous_status": previous})
    flash(_("Ticket reopened"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/reserve")
@login_required
def reserve_part(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = StockReservationForm()
    form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter_by(is_active=True).all()]
    from app.models import StockLocation

    form.location_id.choices = [(str(loc.id), f"{loc.code} - {loc.name}") for loc in StockLocation.query.filter_by(branch_id=ticket.branch_id).all()]

    if form.validate_on_submit():
        try:
            reserve_stock_for_ticket(ticket_id=ticket.id, part_id=uuid.UUID(str(form.part_id.data)), branch_id=uuid.UUID(str(ticket.branch_id)), location_id=uuid.UUID(str(form.location_id.data)), quantity=form.quantity.data)
            db.session.commit()
            flash(_("Part reserved"), "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    else:
        flash(_("Invalid reservation request"), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/release-reservation/<uuid:reservation_id>")
@login_required
def release_reservation(ticket_id, reservation_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    reservation = db.session.get(StockReservation, reservation_id)
    if not reservation or str(reservation.ticket_id) != str(ticket_id):
        flash(_("Reservation not found"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    reservation.status = "released"
    from app.models import StockLevel

    level = StockLevel.query.filter_by(
        part_id=reservation.part_id,
        branch_id=reservation.branch_id,
        location_id=reservation.location_id,
    ).first()
    if level:
        level.reserved_qty = max(0, float(level.reserved_qty or 0) - float(reservation.quantity))
    db.session.commit()
    flash(_("Reservation released"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.get("/board")
@login_required
def repair_board():
    now = datetime.utcnow()
    sort = (request.args.get("sort") or "oldest")
    technician_id = (request.args.get("technician_id") or "").strip()
    branch_id = (request.args.get("branch_id") or "").strip()
    date_range = (request.args.get("date_range") or "").strip()
    only_waiting_parts = request.args.get("waiting_parts") == "1"
    only_overdue = request.args.get("only_overdue") == "1"

    tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()

    def in_range(ticket):
        if date_range == "today":
            return ticket.created_at.date() == now.date()
        if date_range == "this_week":
            return ticket.created_at >= (now - timedelta(days=7))
        if date_range == "this_month":
            return ticket.created_at.year == now.year and ticket.created_at.month == now.month
        return True

    scoped = []
    for ticket in tickets:
        normalized = normalize_ticket_status(ticket.internal_status)
        ticket.internal_status = normalized
        if technician_id and str(ticket.assigned_technician_id or "") != technician_id:
            continue
        if branch_id and str(ticket.branch_id) != branch_id:
            continue
        if only_waiting_parts and not _ticket_waiting_on_parts(ticket):
            continue
        if only_overdue and not is_ticket_overdue(ticket, now):
            continue
        if not in_range(ticket):
            continue
        scoped.append(ticket)

    def sort_key(ticket):
        if sort == "newest":
            return -ticket.created_at.timestamp()
        if sort == "promise_due":
            return (ticket.quoted_completion_at or datetime.max).timestamp()
        if sort == "sla_due":
            return (ticket.sla_target_at or datetime.max).timestamp()
        return ticket.created_at.timestamp()

    scoped.sort(key=sort_key)

    grouped = {"Unassigned": [], "Assigned": [], "Awaiting Diagnostics": [], "Awaiting Parts": [], "In Repair": [], "Ready for Collection": [], "Overdue": [], "Aging": []}

    for ticket in scoped:
        normalized = normalize_ticket_status(ticket.internal_status)
        if normalized == Ticket.STATUS_UNASSIGNED or not ticket.assigned_technician_id:
            grouped["Unassigned"].append(ticket)
        if normalized == Ticket.STATUS_ASSIGNED:
            grouped["Assigned"].append(ticket)
        if normalized == Ticket.STATUS_AWAITING_DIAGNOSTICS:
            grouped["Awaiting Diagnostics"].append(ticket)
        if _ticket_waiting_on_parts(ticket):
            grouped["Awaiting Parts"].append(ticket)
        if normalized in {Ticket.STATUS_IN_REPAIR, Ticket.STATUS_TESTING_QA}:
            grouped["In Repair"].append(ticket)
        if normalized == Ticket.STATUS_READY_FOR_COLLECTION:
            grouped["Ready for Collection"].append(ticket)
        if is_ticket_overdue(ticket, now):
            grouped["Overdue"].append(ticket)
        if ticket_age_days(ticket, now) >= 3 and normalized not in Ticket.CLOSED_STATUSES:
            grouped["Aging"].append(ticket)

    technicians = [u for u in User.query.filter(User.deleted_at.is_(None), User.is_active.is_(True)).order_by(User.full_name.asc()).all() if any(r.name.lower() in {"technician", "manager", "admin", "super admin"} for r in u.roles)]
    branches = Branch.query.order_by(Branch.code.asc()).all()

    return render_template("tickets/board.html", grouped=grouped, now=now, ticket_age_days=ticket_age_days, is_ticket_overdue=is_ticket_overdue, technicians=technicians, branches=branches, filters={"sort":sort,"technician_id":technician_id,"branch_id":branch_id,"date_range":date_range,"waiting_parts":only_waiting_parts,"only_overdue":only_overdue})


@tickets_bp.get("/my-queue")
@login_required
def my_queue():
    now = datetime.utcnow()
    assigned = Ticket.query.filter(Ticket.deleted_at.is_(None), Ticket.assigned_technician_id == current_user.id).order_by(Ticket.created_at.asc()).all()

    grouped = {
        "Awaiting Diagnostics": [t for t in assigned if normalize_ticket_status(t.internal_status) == Ticket.STATUS_AWAITING_DIAGNOSTICS],
        "In Repair": [t for t in assigned if normalize_ticket_status(t.internal_status) in {Ticket.STATUS_IN_REPAIR, Ticket.STATUS_TESTING_QA}],
        "Waiting on Parts": [t for t in assigned if _ticket_waiting_on_parts(t)],
        "Overdue Parts": [t for t in assigned if _ticket_has_overdue_parts(t, now)],
        "Overdue Tickets": [t for t in assigned if is_ticket_overdue(t, now)],
    }

    eta_by_ticket = {str(t.id): _ticket_next_parts_eta(t) for t in assigned}

    return render_template("tickets/my_queue.html", grouped=grouped, is_ticket_overdue=is_ticket_overdue, now=now, eta_by_ticket=eta_by_ticket)


@tickets_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_ticket():
    form = TicketCreateForm()
    selected_customer = (form.customer_id.data or request.args.get("customer_id") or "").strip()

    devices_query = Device.query.filter(Device.deleted_at.is_(None))
    if selected_customer:
        devices_query = devices_query.filter(Device.customer_id == uuid.UUID(selected_customer))
    else:
        devices_query = devices_query.filter(False)

    devices = devices_query.order_by(Device.brand).all()
    form.device_id.choices = [(str(d.id), f"{d.brand} {d.model} ({d.serial_number or 'N/A'})") for d in devices]
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]
    selected_branch = request.form.get("branch_id") or (form.branch_id.choices[0][0] if form.branch_id.choices else None)
    form.assigned_technician_id.choices = _technician_choices(selected_branch)

    if form.validate_on_submit():
        branch = db.session.get(Branch, uuid.UUID(str(form.branch_id.data)))
        sequence = Ticket.query.count() + 1
        status = normalize_ticket_status(form.internal_status.data or None)
        technician_id = uuid.UUID(str(form.assigned_technician_id.data)) if form.assigned_technician_id.data else None
        if not form.internal_status.data:
            status = Ticket.STATUS_ASSIGNED if technician_id else Ticket.STATUS_UNASSIGNED

        ticket = Ticket(
            ticket_number=generate_ticket_number(branch.code, sequence),
            branch_id=uuid.UUID(str(form.branch_id.data)),
            customer_id=uuid.UUID(str(form.customer_id.data)),
            device_id=uuid.UUID(str(form.device_id.data)),
            priority=form.priority.data,
            internal_status=status,
            customer_status="Received",
            assigned_technician_id=technician_id,
            issue_summary=form.issue_summary.data,
            quoted_completion_at=form.quoted_completion_at.data,
            sla_target_at=default_sla_target(datetime.utcnow(), current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)),
        )
        db.session.add(ticket)
        db.session.flush()
        intake_parts = []
        if form.issue_summary.data:
            intake_parts.append(f"Issue: {form.issue_summary.data}")
        if form.device_condition.data:
            intake_parts.append(f"Device condition: {form.device_condition.data}")
        if form.accessories.data:
            intake_parts.append(f"Accessories: {form.accessories.data}")
        if form.customer_notes.data:
            intake_parts.append(f"Customer notes: {form.customer_notes.data}")
        if intake_parts:
            db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content="\n".join(intake_parts)))
        db.session.commit()
        log_action("ticket.create", "Ticket", str(ticket.id), details={"ticket_number": ticket.ticket_number})
        flash(_("Ticket created"), "success")
        return redirect(url_for("tickets.list_tickets"))

    return render_template("tickets/new.html", form=form, selected_customer=selected_customer)
