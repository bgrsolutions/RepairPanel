import secrets
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
from app.models import Branch, Customer, Device, Diagnostic, Part, PartOrder, PortalToken, Quote, RepairChecklist, RepairService, StockLevel, StockReservation, Ticket, TicketNote, User
from app.services.audit_service import log_action
from app.services.permission_service import (
    can_consume_reservation,
    can_create_ticket,
    can_manage_customer_portal,
    can_manage_warranty,
    can_progress_workflow,
    can_send_branded_email,
    can_send_customer_updates,
)
from app.utils.permissions import permission_required
from app.services.customer_communication_service import (
    available_templates,
    generate_message,
    get_portal_token,
    get_quote_approval_url_for_ticket,
    regenerate_portal_token,
    revoke_portal_token,
    suggested_template_key,
)
from app.services.inventory_service import consume_reservation, reserve_stock_for_ticket
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
        if status == "overdue" and not is_ticket_overdue(t, now, sla_days=current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)):
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


@tickets_bp.get("/device-search")
@login_required
def device_search():
    """AJAX endpoint: search devices by brand, model, serial, or IMEI."""
    q = (request.args.get("q") or "").strip()
    customer_id = (request.args.get("customer_id") or "").strip()
    if len(q) < 2:
        return {"items": []}
    from sqlalchemy import or_
    like = f"%{q}%"
    query = Device.query.filter(
        Device.deleted_at.is_(None),
        or_(Device.brand.ilike(like), Device.model.ilike(like),
            Device.serial_number.ilike(like), Device.imei.ilike(like)),
    )
    if customer_id:
        query = query.filter(Device.customer_id == uuid.UUID(customer_id))
    rows = query.order_by(Device.brand.asc()).limit(25).all()
    return {"items": [
        {"id": str(d.id), "label": f"{d.brand} {d.model} ({d.serial_number or 'N/A'})",
         "brand": d.brand, "model": d.model, "serial_number": d.serial_number or "",
         "customer_name": d.customer.full_name if d.customer else ""}
        for d in rows
    ]}


@tickets_bp.post("/device-create-json")
@login_required
def device_create_json():
    """AJAX endpoint: create a new device for a customer during ticket creation."""
    data = request.get_json(silent=True) or {}
    customer_id = (data.get("customer_id") or "").strip()
    brand = (data.get("brand") or "").strip()
    model = (data.get("model") or "").strip()
    category = (data.get("category") or "phones").strip()
    serial_number = (data.get("serial_number") or "").strip() or None
    imei = (data.get("imei") or "").strip() or None
    if not customer_id or not brand or not model:
        return jsonify({"ok": False, "error": "Customer, brand, and model are required"}), 400
    device = Device(
        customer_id=uuid.UUID(customer_id), category=category,
        brand=brand, model=model, serial_number=serial_number, imei=imei,
    )
    db.session.add(device)
    db.session.commit()
    return jsonify({
        "ok": True, "id": str(device.id),
        "label": f"{device.brand} {device.model} ({device.serial_number or 'N/A'})",
    })


@tickets_bp.get("/<uuid:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    from app.services.workflow_service import detect_blockers, next_recommended_action

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
    pre_repair_checklists = RepairChecklist.query.filter_by(ticket_id=ticket_uuid, checklist_type="pre_repair").order_by(RepairChecklist.created_at.asc()).all() if has_checklists else []
    post_repair_checklists = RepairChecklist.query.filter_by(ticket_id=ticket_uuid, checklist_type="post_repair").order_by(RepairChecklist.created_at.asc()).all() if has_checklists else []

    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)
    blockers = detect_blockers(ticket, now=datetime.utcnow(), sla_days=sla_days)
    next_action = next_recommended_action(ticket, blockers)

    # Public status URL for sharing with customer
    try:
        status_token = PortalToken.query.filter_by(ticket_id=ticket_uuid, token_type="public_status_lookup").first()
        public_status_url = url_for("public_portal.public_repair_status", token=status_token.token, _external=True) if status_token else None
    except Exception:
        public_status_url = None

    # Quote approval URL for communication shortcuts
    try:
        quote_approval_url = get_quote_approval_url_for_ticket(ticket)
    except Exception:
        quote_approval_url = None

    # Communication context for message builder
    comm_templates = available_templates()
    suggested_tpl = suggested_template_key(normalize_ticket_status(ticket.internal_status))

    # Communication history (notes with type="communication")
    communication_notes = [n for n in notes if n.note_type == "communication"]

    portal_token_active = public_status_url is not None

    # Warranty context (Phase 17)
    from app.forms.warranty_forms import WarrantyForm, WarrantyClaimForm, WarrantyVoidForm
    warranty_form = WarrantyForm()
    warranty_claim_form = WarrantyClaimForm()
    warranty_void_form = WarrantyVoidForm()
    try:
        from app.services.warranty_service import evaluate_warranty, get_ticket_parts_summary
        warranty_info = evaluate_warranty(ticket)
        # Pre-fill warranty days from company defaults
        if not warranty_info["has_warranty"]:
            from app.models import Company
            company = Company.query.filter_by(is_active=True, deleted_at=None).first()
            if company and company.default_warranty_days:
                warranty_form.warranty_days.data = company.default_warranty_days
            if company and company.default_warranty_terms:
                warranty_form.terms.data = company.default_warranty_terms
            # Auto-fill parts used summary
            parts_summary = get_ticket_parts_summary(ticket)
            if parts_summary:
                warranty_form.repair_summary.data = parts_summary
    except Exception:
        warranty_info = {"has_warranty": False, "warranty": None, "is_active": False, "days_remaining": 0, "prior_repairs": []}

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
        pre_repair_checklists=pre_repair_checklists,
        post_repair_checklists=post_repair_checklists,
        blockers=blockers,
        next_action=next_action,
        public_status_url=public_status_url,
        quote_approval_url=quote_approval_url,
        comm_templates=comm_templates,
        suggested_tpl=suggested_tpl,
        communication_notes=communication_notes,
        portal_token_active=portal_token_active,
        warranty_info=warranty_info,
        warranty_form=warranty_form,
        warranty_claim_form=warranty_claim_form,
        warranty_void_form=warranty_void_form,
    )


@tickets_bp.post("/<uuid:ticket_id>/assign")
@login_required
@permission_required(can_progress_workflow)
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
@permission_required(can_progress_workflow)
def update_status(ticket_id):
    from app.services.workflow_service import is_valid_transition

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = TicketStatusForm()
    if form.validate_on_submit():
        new_status = normalize_ticket_status(form.internal_status.data)
        current_status = normalize_ticket_status(ticket.internal_status)

        # Validate transition (allow same-status no-op)
        if new_status != current_status and not is_valid_transition(current_status, new_status):
            flash(_("Invalid status transition from %(from_s)s to %(to_s)s",
                     from_s=current_status.replace("_", " ").title(),
                     to_s=new_status.replace("_", " ").title()), "error")
            return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

        # Enforce post-repair checklist completion before marking as completed or ready for collection
        if new_status in (Ticket.STATUS_COMPLETED, Ticket.STATUS_READY_FOR_COLLECTION) and sa_inspect(db.engine).has_table("repair_checklists"):
            post_checklists = RepairChecklist.query.filter_by(
                ticket_id=ticket.id, checklist_type="post_repair"
            ).all()
            has_complete_post = any(cl.is_complete for cl in post_checklists)
            if not has_complete_post:
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
@permission_required(can_progress_workflow)
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
@permission_required(can_progress_workflow)
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
@permission_required(can_send_customer_updates)
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
@permission_required(can_progress_workflow)
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
@permission_required(can_progress_workflow)
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
@permission_required(can_progress_workflow)
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


@tickets_bp.post("/<uuid:ticket_id>/consume-reservation/<uuid:reservation_id>")
@login_required
@permission_required(can_consume_reservation)
def consume_part(ticket_id, reservation_id):
    """Consume a reserved part — mark as installed and deduct stock."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    reservation = db.session.get(StockReservation, reservation_id)
    if not reservation or str(reservation.ticket_id) != str(ticket_id):
        flash(_("Reservation not found"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    if reservation.status != "reserved":
        flash(_("Reservation is not in reserved state"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    try:
        consume_reservation(reservation)
        part_name = reservation.part.name if reservation.part else "Part"
        db.session.add(TicketNote(
            ticket_id=ticket.id, author_user_id=current_user.id,
            note_type="internal",
            content=f"Part installed: {part_name} (qty {reservation.quantity})",
        ))
        db.session.commit()
        flash(_("Part consumed and stock updated"), "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/assign-to-me")
@login_required
@permission_required(can_progress_workflow)
def assign_to_me(ticket_id):
    """Quick action: assign ticket to current user."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    previous = ticket.assigned_technician.full_name if ticket.assigned_technician else "Unassigned"
    ticket.assigned_technician_id = current_user.id
    _sync_assignment_status(ticket)
    db.session.add(TicketNote(
        ticket_id=ticket.id, author_user_id=current_user.id,
        note_type="internal",
        content=f"Assignment changed: {previous} → {current_user.full_name}",
    ))
    db.session.commit()
    flash(_("Ticket assigned to you"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/quick-status")
@login_required
@permission_required(can_progress_workflow)
def quick_status(ticket_id):
    """Quick action: transition to a pre-defined status shortcut."""
    from app.services.workflow_service import is_valid_transition

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    action = (request.form.get("action") or "").strip()
    current_status = normalize_ticket_status(ticket.internal_status)

    ACTION_MAP = {
        "diagnosis_complete": Ticket.STATUS_AWAITING_QUOTE_APPROVAL,
        "waiting_parts": Ticket.STATUS_AWAITING_PARTS,
        "start_repair": Ticket.STATUS_IN_REPAIR,
        "repair_complete": Ticket.STATUS_TESTING_QA,
        "ready_for_collection": Ticket.STATUS_READY_FOR_COLLECTION,
        "mark_complete": Ticket.STATUS_COMPLETED,
    }

    new_status = ACTION_MAP.get(action)
    if not new_status:
        flash(_("Unknown quick action"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    if new_status != current_status and not is_valid_transition(current_status, new_status):
        flash(_("Invalid status transition from %(from_s)s to %(to_s)s",
                 from_s=current_status.replace("_", " ").title(),
                 to_s=new_status.replace("_", " ").title()), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    # Enforce post-repair checklist for completion/ready statuses
    if new_status in (Ticket.STATUS_COMPLETED, Ticket.STATUS_READY_FOR_COLLECTION) and sa_inspect(db.engine).has_table("repair_checklists"):
        post_checklists = RepairChecklist.query.filter_by(
            ticket_id=ticket.id, checklist_type="post_repair"
        ).all()
        if not any(cl.is_complete for cl in post_checklists):
            flash(_("Cannot change status: the post-repair checklist must be completed first."), "error")
            return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    previous = ticket.internal_status
    ticket.internal_status = new_status
    db.session.add(TicketNote(
        ticket_id=ticket.id, author_user_id=current_user.id,
        note_type="internal",
        content=f"Status changed: {previous} → {new_status}",
    ))
    db.session.commit()
    flash(_("Ticket status updated to %(status)s", status=new_status.replace("_", " ").title()), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/quick-note")
@login_required
@permission_required(can_progress_workflow)
def quick_note(ticket_id):
    """Quick action: add an internal bench note without the full modal."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    content = (request.form.get("content") or "").strip()
    if not content:
        flash(_("Note content is required"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    db.session.add(TicketNote(
        ticket_id=ticket.id,
        author_user_id=uuid.UUID(str(current_user.id)),
        note_type="internal",
        content=content,
    ))
    db.session.commit()
    flash(_("Bench note added"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.get("/board")
@login_required
def repair_board():
    from app.services.workflow_service import detect_blockers

    now = datetime.utcnow()
    sort = (request.args.get("sort") or "oldest")
    technician_id = (request.args.get("technician_id") or "").strip()
    branch_id = (request.args.get("branch_id") or "").strip()
    date_range = (request.args.get("date_range") or "").strip()
    only_waiting_parts = request.args.get("waiting_parts") == "1"
    only_overdue = request.args.get("only_overdue") == "1"
    only_waiting_quote = request.args.get("waiting_quote") == "1"
    status_filter = (request.args.get("status") or "").strip()

    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)
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
        if normalized in Ticket.CLOSED_STATUSES:
            continue
        if technician_id and str(ticket.assigned_technician_id or "") != technician_id:
            continue
        if branch_id and str(ticket.branch_id) != branch_id:
            continue
        if status_filter and normalized != status_filter:
            continue
        if not in_range(ticket):
            continue
        scoped.append(ticket)

    # Compute blockers for each ticket
    ticket_blockers: dict[str, list] = {}
    for ticket in scoped:
        ticket_blockers[str(ticket.id)] = detect_blockers(ticket, now=now, sla_days=sla_days)

    # Apply blocker-based filters
    if only_waiting_parts:
        scoped = [t for t in scoped if any(b.kind == "parts" for b in ticket_blockers[str(t.id)])]
    if only_overdue:
        scoped = [t for t in scoped if is_ticket_overdue(t, now, sla_days=sla_days)]
    if only_waiting_quote:
        scoped = [t for t in scoped if any(b.kind == "quote" for b in ticket_blockers[str(t.id)])]

    def sort_key(ticket):
        if sort == "newest":
            return -ticket.created_at.timestamp()
        if sort == "promise_due":
            return (ticket.quoted_completion_at or datetime.max).timestamp()
        if sort == "sla_due":
            return (ticket.sla_target_at or datetime.max).timestamp()
        return ticket.created_at.timestamp()

    scoped.sort(key=sort_key)

    # Phase 8A: workflow-oriented columns
    BOARD_COLUMNS = [
        ("Awaiting Diagnosis", {Ticket.STATUS_UNASSIGNED, Ticket.STATUS_ASSIGNED, Ticket.STATUS_AWAITING_DIAGNOSTICS}),
        ("Awaiting Quote Approval", {Ticket.STATUS_AWAITING_QUOTE_APPROVAL}),
        ("Awaiting Parts", {Ticket.STATUS_AWAITING_PARTS}),
        ("Ready For Repair", {Ticket.STATUS_IN_REPAIR}),
        ("Testing / QA", {Ticket.STATUS_TESTING_QA}),
        ("Ready For Collection", {Ticket.STATUS_READY_FOR_COLLECTION}),
    ]

    from collections import OrderedDict
    grouped: dict[str, list] = OrderedDict()
    for col_name, _ in BOARD_COLUMNS:
        grouped[col_name] = []

    for ticket in scoped:
        normalized = normalize_ticket_status(ticket.internal_status)
        for col_name, statuses in BOARD_COLUMNS:
            if normalized in statuses:
                grouped[col_name].append(ticket)
                break

    technicians = [u for u in User.query.filter(User.deleted_at.is_(None), User.is_active.is_(True)).order_by(User.full_name.asc()).all() if any(r.name.lower() in {"technician", "manager", "admin", "super admin"} for r in u.roles)]
    branches = Branch.query.order_by(Branch.code.asc()).all()

    return render_template(
        "tickets/board.html",
        grouped=grouped,
        now=now,
        ticket_age_days=ticket_age_days,
        is_ticket_overdue=is_ticket_overdue,
        ticket_blockers=ticket_blockers,
        technicians=technicians,
        branches=branches,
        filters={
            "sort": sort,
            "technician_id": technician_id,
            "branch_id": branch_id,
            "date_range": date_range,
            "waiting_parts": only_waiting_parts,
            "only_overdue": only_overdue,
            "waiting_quote": only_waiting_quote,
            "status": status_filter,
        },
    )


@tickets_bp.post("/<uuid:ticket_id>/quick-assign")
@login_required
def quick_assign(ticket_id):
    """AJAX endpoint for assigning a technician from the bench board."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        return jsonify({"ok": False, "error": "Ticket not found"}), 404

    tech_id = (request.form.get("technician_id") or "").strip()
    previous = ticket.assigned_technician.full_name if ticket.assigned_technician else "Unassigned"

    if tech_id:
        technician = db.session.get(User, uuid.UUID(tech_id))
        if not technician:
            return jsonify({"ok": False, "error": "Technician not found"}), 404
        ticket.assigned_technician_id = uuid.UUID(tech_id)
        new_name = technician.full_name
    else:
        ticket.assigned_technician_id = None
        new_name = "Unassigned"

    _sync_assignment_status(ticket)
    db.session.add(TicketNote(
        ticket_id=ticket.id, author_user_id=current_user.id,
        note_type="internal",
        content=f"Assignment changed: {previous} → {new_name}",
    ))
    db.session.commit()
    return jsonify({"ok": True, "technician": new_name})


@tickets_bp.get("/my-queue")
@login_required
def my_queue():
    now = datetime.utcnow()
    assigned = Ticket.query.filter(Ticket.deleted_at.is_(None), Ticket.assigned_technician_id == current_user.id).order_by(Ticket.created_at.asc()).all()

    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)
    grouped = {
        "Awaiting Diagnostics": [t for t in assigned if normalize_ticket_status(t.internal_status) == Ticket.STATUS_AWAITING_DIAGNOSTICS],
        "In Repair": [t for t in assigned if normalize_ticket_status(t.internal_status) in {Ticket.STATUS_IN_REPAIR, Ticket.STATUS_TESTING_QA}],
        "Waiting on Parts": [t for t in assigned if _ticket_waiting_on_parts(t)],
        "Overdue Parts": [t for t in assigned if _ticket_has_overdue_parts(t, now)],
        "Overdue Tickets": [t for t in assigned if is_ticket_overdue(t, now, sla_days=sla_days)],
    }

    eta_by_ticket = {str(t.id): _ticket_next_parts_eta(t) for t in assigned}

    return render_template("tickets/my_queue.html", grouped=grouped, is_ticket_overdue=is_ticket_overdue, now=now, eta_by_ticket=eta_by_ticket)


def _service_choices():
    """Build choices list for repair service selector."""
    try:
        from sqlalchemy import inspect as _insp
        if not _insp(db.engine).has_table("repair_services"):
            return [("", "-- Select Service (optional) --")]
    except Exception:
        return [("", "-- Select Service (optional) --")]
    services = RepairService.query.filter(RepairService.is_active.is_(True)).order_by(RepairService.device_category, RepairService.name).all()
    choices = [("", "-- Select Service (optional) --")]
    for s in services:
        cat = f" [{s.device_category.replace('_', ' ').title()}]" if s.device_category else ""
        choices.append((str(s.id), f"{s.name}{cat}"))
    return choices


def _part_availability(part_id, branch_id=None):
    """Check stock availability for a part across branches."""
    levels = StockLevel.query.filter(StockLevel.part_id == part_id).all()
    this_store = 0
    other_stores = 0
    for lvl in levels:
        available = (lvl.on_hand_qty or 0) - (lvl.reserved_qty or 0)
        if branch_id and str(lvl.branch_id) == str(branch_id):
            this_store += max(0, available)
        else:
            other_stores += max(0, available)
    return this_store, other_stores


def _suggest_eta(service, part_in_stock):
    """Suggest a promised completion time based on service and stock."""
    now = datetime.utcnow()
    labour_hours = (service.labour_minutes or 60) / 60.0

    if part_in_stock:
        # Part in stock: promise based on labour + same-day buffer
        eta = now + timedelta(hours=max(labour_hours + 1, 2))
        # Round up to next whole hour at :00
        eta = eta.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        # Cap at 18:00 today or next business day
        if eta.hour >= 18:
            next_day = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
            eta = next_day + timedelta(hours=int(labour_hours) + 1)
    else:
        # Part not in stock: add lead time from part or default 3 days
        part = service.default_part
        lead_days = (part.lead_time_days if part and part.lead_time_days else 3)
        eta = now + timedelta(days=lead_days, hours=labour_hours)
        eta = eta.replace(hour=18, minute=0, second=0, microsecond=0)

    return eta


@tickets_bp.get("/service-availability")
@login_required
def service_availability():
    """AJAX endpoint: returns part availability and ETA for a service+branch."""
    service_id = (request.args.get("service_id") or "").strip()
    branch_id = (request.args.get("branch_id") or "").strip()
    if not service_id:
        return jsonify({"available": False})
    try:
        svc = db.session.get(RepairService, uuid.UUID(service_id))
    except (ValueError, TypeError):
        return jsonify({"available": False})
    if not svc:
        return jsonify({"available": False})

    result = {
        "service_name": svc.name,
        "labour_minutes": svc.labour_minutes,
        "suggested_price": float(svc.suggested_sale_price) if svc.suggested_sale_price else None,
    }

    if svc.default_part_id:
        part = svc.default_part
        this_store, other_stores = _part_availability(svc.default_part_id, branch_id)
        result["part_name"] = part.name if part else None
        result["stock_this_store"] = this_store
        result["stock_other_stores"] = other_stores
        result["part_in_stock"] = this_store > 0
        result["needs_ordering"] = this_store == 0 and other_stores == 0
        if part and part.lead_time_days:
            result["lead_time_days"] = part.lead_time_days

        eta = _suggest_eta(svc, this_store > 0)
        result["suggested_eta"] = eta.strftime("%Y-%m-%dT%H:%M")
        result["eta_display"] = eta.strftime("%d %b %Y %H:%M")
    else:
        # No default part — just use labour time
        eta = _suggest_eta(svc, True)
        result["suggested_eta"] = eta.strftime("%Y-%m-%dT%H:%M")
        result["eta_display"] = eta.strftime("%d %b %Y %H:%M")
        result["part_in_stock"] = True

    return jsonify(result)


@tickets_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required(can_create_ticket)
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
    form.repair_service_id.choices = _service_choices()
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
        # Record selected service
        svc_id = form.repair_service_id.data
        if svc_id:
            svc = db.session.get(RepairService, uuid.UUID(svc_id))
            if svc:
                intake_parts.append(f"Service: {svc.name}")
        if intake_parts:
            db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=current_user.id, note_type="internal", content="\n".join(intake_parts)))
        db.session.commit()
        # Create public status token for customer access
        try:
            db.session.add(PortalToken(token=secrets.token_urlsafe(24), token_type="public_status_lookup", ticket_id=ticket.id))
            db.session.commit()
        except Exception:
            db.session.rollback()
        log_action("ticket.create", "Ticket", str(ticket.id), details={"ticket_number": ticket.ticket_number})
        flash(_("Ticket created"), "success")
        return redirect(url_for("tickets.list_tickets"))

    return render_template("tickets/new.html", form=form, selected_customer=selected_customer)


# ---------------------------------------------------------------------------
# Phase 12 — Portal token lifecycle & communication actions
# ---------------------------------------------------------------------------


@tickets_bp.post("/<uuid:ticket_id>/regenerate-portal-token")
@login_required
@permission_required(can_manage_customer_portal)
def regenerate_token(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    new_token = regenerate_portal_token(ticket.id)
    db.session.add(TicketNote(
        ticket_id=ticket.id,
        author_user_id=uuid.UUID(str(current_user.id)),
        note_type="communication",
        content="Portal status link regenerated. Previous link invalidated.",
    ))
    db.session.commit()
    log_action("ticket.portal_token_regenerated", "Ticket", str(ticket.id), details={"new_token_prefix": new_token[:8]})
    flash(_("Portal link regenerated. Old link no longer works."), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/revoke-portal-token")
@login_required
@permission_required(can_manage_customer_portal)
def revoke_token(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    count = revoke_portal_token(ticket.id)
    if count > 0:
        db.session.add(TicketNote(
            ticket_id=ticket.id,
            author_user_id=uuid.UUID(str(current_user.id)),
            note_type="communication",
            content="Portal status link revoked. Customer can no longer access status via direct link.",
        ))
        db.session.commit()
        log_action("ticket.portal_token_revoked", "Ticket", str(ticket.id))
        flash(_("Portal link revoked"), "success")
    else:
        db.session.commit()
        flash(_("No active portal link to revoke"), "info")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/generate-message")
@login_required
@permission_required(can_send_customer_updates)
def generate_customer_message(ticket_id):
    """Generate a customer communication message from a template. Returns JSON."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        return jsonify({"error": "Ticket not found"}), 404

    template_key = request.json.get("template_key") if request.is_json else request.form.get("template_key")
    if not template_key:
        template_key = suggested_template_key(normalize_ticket_status(ticket.internal_status))

    # Build portal URL
    try:
        portal_tok = get_portal_token(ticket.id)
        portal_url = url_for("public_portal.public_repair_status", token=portal_tok.token, _external=True) if portal_tok else None
    except Exception:
        portal_url = None

    # Build quote approval URL
    try:
        quote_url = get_quote_approval_url_for_ticket(ticket)
    except Exception:
        quote_url = None

    # Opening hours from branch
    opening_hours = None
    if ticket.branch and hasattr(ticket.branch, "opening_hours"):
        opening_hours = ticket.branch.opening_hours

    msg = generate_message(
        template_key,
        ticket_number=ticket.ticket_number,
        device_summary=f"{ticket.device.brand} {ticket.device.model}",
        customer_name=ticket.customer.full_name if ticket.customer else None,
        portal_url=portal_url,
        quote_approval_url=quote_url,
        opening_hours=opening_hours,
    )
    return jsonify(msg)


@tickets_bp.post("/<uuid:ticket_id>/log-communication")
@login_required
@permission_required(can_send_customer_updates)
def log_communication_action(ticket_id):
    """Log a communication action (link copied, message prepared, etc.)."""
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        return jsonify({"error": "Ticket not found"}), 404

    action_type = request.json.get("action_type", "") if request.is_json else request.form.get("action_type", "")
    detail = request.json.get("detail", "") if request.is_json else request.form.get("detail", "")

    action_labels = {
        "portal_link_copied": "Portal status link copied to clipboard",
        "quote_link_copied": "Quote approval link copied to clipboard",
        "message_generated": f"Customer message prepared: {detail}" if detail else "Customer message prepared",
        "message_sent": f"Customer message sent: {detail}" if detail else "Customer message sent",
        "ready_notification_prepared": "Ready-for-collection notification prepared",
        "quote_notification_prepared": "Quote approval notification prepared",
    }
    content = action_labels.get(action_type, f"Communication action: {action_type}")

    db.session.add(TicketNote(
        ticket_id=ticket.id,
        author_user_id=uuid.UUID(str(current_user.id)),
        note_type="communication",
        content=content,
    ))
    db.session.commit()
    log_action(f"ticket.comm.{action_type}", "Ticket", str(ticket.id), details={"action_type": action_type, "detail": detail})
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Phase 17: Warranty management routes
# ---------------------------------------------------------------------------

@tickets_bp.post("/<uuid:ticket_id>/warranty")
@login_required
@permission_required(can_manage_warranty)
def create_warranty_record(ticket_id):
    """Create a warranty record for a completed/closed ticket."""
    from app.forms.warranty_forms import WarrantyForm
    from app.services.warranty_service import create_warranty, get_ticket_parts_summary

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = WarrantyForm()
    if form.validate_on_submit():
        warranty_type = form.warranty_type.data
        warranty_days = form.warranty_days.data or 0
        if warranty_type == "no_warranty":
            warranty_days = 0

        parts_summary = get_ticket_parts_summary(ticket)
        warranty = create_warranty(
            ticket=ticket,
            warranty_type=warranty_type,
            warranty_days=warranty_days,
            covers_labour=form.covers_labour.data if warranty_type != "no_warranty" else False,
            covers_parts=form.covers_parts.data if warranty_type != "no_warranty" else False,
            terms=form.terms.data,
            repair_summary=form.repair_summary.data or parts_summary,
            parts_used=parts_summary,
            created_by_id=str(current_user.id),
        )
        db.session.add(TicketNote(
            ticket_id=ticket.id,
            author_user_id=current_user.id,
            note_type="internal",
            content=f"Warranty recorded: {warranty.type_label} ({warranty.warranty_days} days)",
        ))
        db.session.commit()
        log_action("ticket.warranty.create", "Ticket", str(ticket.id), details={
            "warranty_type": warranty_type, "warranty_days": warranty_days,
        })
        flash(_("Warranty recorded successfully"), "success")
    else:
        flash(_("Invalid warranty submission"), "error")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/warranty/send-email")
@login_required
@permission_required(can_send_branded_email)
def send_warranty_email(ticket_id):
    """Send warranty confirmation email to the customer."""
    from app.services.branded_email_service import send_warranty_confirmation_email

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    from app.models.warranty import TicketWarranty
    warranty = TicketWarranty.query.filter_by(ticket_id=ticket.id, deleted_at=None).first()
    if not warranty:
        flash(_("No warranty found for this ticket"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    language = ticket.customer.preferred_language if ticket.customer else "en"
    result = send_warranty_confirmation_email(warranty, language=language)
    db.session.commit()

    db.session.add(TicketNote(
        ticket_id=ticket.id,
        author_user_id=current_user.id,
        note_type="communication",
        content=f"Warranty confirmation email: {result.message}",
    ))
    db.session.commit()
    log_action("ticket.warranty.email", "Ticket", str(ticket.id), details={
        "result": result.message, "success": result.success,
    })

    if result.success:
        flash(_("Warranty confirmation email sent"), "success")
    else:
        flash(_("Email could not be sent: %(error)s", error=result.message), "warning")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/warranty/claim")
@login_required
@permission_required(can_manage_warranty)
def warranty_claim(ticket_id):
    """Record a warranty claim."""
    from app.forms.warranty_forms import WarrantyClaimForm
    from app.services.warranty_service import record_claim

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    from app.models.warranty import TicketWarranty
    warranty = TicketWarranty.query.filter_by(ticket_id=ticket.id, deleted_at=None).first()
    if not warranty:
        flash(_("No warranty found for this ticket"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    form = WarrantyClaimForm()
    if form.validate_on_submit():
        record_claim(warranty, notes=form.claim_notes.data)
        db.session.add(TicketNote(
            ticket_id=ticket.id,
            author_user_id=current_user.id,
            note_type="internal",
            content=f"Warranty claim #{warranty.claim_count} recorded",
        ))
        db.session.commit()
        log_action("ticket.warranty.claim", "Ticket", str(ticket.id), details={
            "claim_count": warranty.claim_count,
        })
        flash(_("Warranty claim recorded"), "success")
    else:
        flash(_("Invalid claim submission"), "error")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/warranty/void")
@login_required
@permission_required(can_manage_warranty)
def warranty_void(ticket_id):
    """Void a warranty."""
    from app.forms.warranty_forms import WarrantyVoidForm
    from app.services.warranty_service import void_warranty

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    from app.models.warranty import TicketWarranty
    warranty = TicketWarranty.query.filter_by(ticket_id=ticket.id, deleted_at=None).first()
    if not warranty:
        flash(_("No warranty found for this ticket"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    form = WarrantyVoidForm()
    if form.validate_on_submit():
        void_warranty(warranty, reason=form.voided_reason.data, voided_by_id=str(current_user.id))
        db.session.add(TicketNote(
            ticket_id=ticket.id,
            author_user_id=current_user.id,
            note_type="internal",
            content=f"Warranty voided: {form.voided_reason.data}",
        ))
        db.session.commit()
        log_action("ticket.warranty.void", "Ticket", str(ticket.id), details={
            "reason": form.voided_reason.data,
        })
        flash(_("Warranty voided"), "success")
    else:
        flash(_("Invalid void submission"), "error")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@tickets_bp.post("/<uuid:ticket_id>/send-branded-email")
@login_required
@permission_required(can_send_branded_email)
def send_branded_update_email(ticket_id):
    """Send a branded email update to the customer."""
    from app.services.branded_email_service import send_branded_email

    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    content = (request.form.get("content") or "").strip()
    if not content:
        flash(_("Email content is required"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    if not ticket.customer or not ticket.customer.email:
        flash(_("Customer has no email address"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    language = ticket.customer.preferred_language or "en"
    status_text = ticket.internal_status.replace("_", " ").title()

    result = send_branded_email(
        to_email=ticket.customer.email,
        to_name=ticket.customer.full_name,
        subject=_("Repair Update — %(ticket)s", ticket=ticket.ticket_number),
        template_name="ticket_update.html",
        template_context={
            "ticket": ticket,
            "customer": ticket.customer,
            "message": content,
            "status_text": status_text,
        },
        language=language,
    )

    db.session.add(TicketNote(
        ticket_id=ticket.id,
        author_user_id=current_user.id,
        note_type="communication",
        content=f"Branded email sent to {ticket.customer.email}: {result.message}",
    ))
    db.session.commit()
    log_action("ticket.branded_email", "Ticket", str(ticket.id), details={
        "result": result.message, "success": result.success,
    })

    if result.success:
        flash(_("Branded email sent successfully"), "success")
    else:
        flash(_("Email could not be sent: %(error)s", error=result.message), "warning")

    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))
