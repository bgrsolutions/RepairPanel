import uuid
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.quote_forms import QuoteCreateForm
from app.models import AppSetting, Branch, Customer, Device, Diagnostic, Part, Quote, QuoteApproval, QuoteLine, QuoteOption, RepairService, Ticket
from app.services.audit_service import log_action
from app.services.permission_service import can_create_quote, can_create_ticket, can_manage_quote
from app.services.quote_service import compute_quote_totals, set_quote_status
from app.utils.permissions import permission_required
from app.utils.ticketing import default_sla_target, generate_ticket_number


def _default_quote_terms() -> str:
    try:
        from sqlalchemy import inspect as sa_inspect
        if not sa_inspect(db.engine).has_table("app_settings"):
            return ""
        row = AppSetting.query.filter_by(key="quote_default_terms", branch_id=None).first()
        return row.value if row and row.value else ""
    except Exception:
        return ""


quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")


def _get_parts_data():
    """Return parts metadata dict for the quote builder JS."""
    parts = Part.query.filter(Part.is_active.is_(True)).order_by(Part.name.asc()).all()
    return {str(p.id): {"name": p.name, "sku": p.sku or "", "sale_price": float(p.sale_price or 0)} for p in parts}


def _ensure_default_entries(form: QuoteCreateForm):
    if not form.options:
        form.options.append_entry({"name": "Repair Quote"})
    if not form.options[0].form.lines:
        form.options[0].form.lines.append_entry()


def _save_quote_from_form(quote: Quote, form: QuoteCreateForm):
    quote.currency = form.currency.data
    quote.language = form.language.data
    quote.notes_snapshot = form.notes_snapshot.data
    quote.terms_snapshot = form.terms_snapshot.data
    quote.expires_at = datetime.combine(form.expires_at.data, datetime.min.time()) if form.expires_at.data else None

    quote.options.clear()
    db.session.flush()

    for idx, option_form in enumerate(form.options.entries, start=1):
        option_name = (option_form.form.name.data or "").strip() or "Repair Quote"
        option = QuoteOption(quote_id=quote.id, name=option_name, position=idx)
        db.session.add(option)
        db.session.flush()

        kept_lines = 0
        for line_form in option_form.form.lines.entries:
            description = (line_form.form.description.data or "").strip()
            quantity = line_form.form.quantity.data
            unit_price = line_form.form.unit_price.data
            linked_part_id = line_form.form.linked_part_id.data or None
            linked_part_uuid = uuid.UUID(str(linked_part_id)) if linked_part_id else None
            linked_part = db.session.get(Part, linked_part_uuid) if linked_part_uuid else None

            if not description and linked_part:
                description = linked_part.name
            if (unit_price is None or unit_price <= 0) and linked_part and linked_part.sale_price is not None:
                unit_price = linked_part.sale_price
            if quantity is None or quantity <= 0:
                quantity = Decimal("1")
            if not description or unit_price is None:
                continue

            db.session.add(
                QuoteLine(
                    option_id=option.id,
                    line_type=line_form.form.line_type.data or "part",
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    part_id=linked_part_uuid,
                )
            )
            kept_lines += 1

        if kept_lines == 0:
            db.session.delete(option)


def _get_services_data():
    """Return active repair services for the service selector."""
    try:
        services = RepairService.query.filter(RepairService.is_active.is_(True)).order_by(RepairService.name.asc()).all()
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "service_code": s.service_code or "",
                "labour_price": float(s.labour_price) if s.labour_price else (float(s.suggested_sale_price) if s.suggested_sale_price else 0),
                "labour_minutes": s.labour_minutes,
            }
            for s in services
        ]
    except Exception:
        return []


def _render_quote_form(ticket, form, mode, parts_data, quote=None):
    """Render the quote builder template with all required context."""
    ctx = {
        "form": form,
        "mode": mode,
        "igic_rate": current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
        "parts_data": parts_data,
        "services_data": _get_services_data(),
    }
    if ticket:
        ctx["ticket"] = ticket
    if quote:
        ctx["quote"] = quote
        if not ticket and quote.ticket:
            ctx["ticket"] = quote.ticket
    return render_template("quotes/new.html", **ctx)


@quotes_bp.get("/part-price/<uuid:part_id>")
@login_required
def part_price(part_id):
    part = db.session.get(Part, part_id)
    if not part:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "sale_price": float(part.sale_price or 0)})


# ── Ticket-linked quote routes ──────────────────────────────────

@quotes_bp.get("/ticket/<uuid:ticket_id>/new")
@login_required
@permission_required(can_create_quote)
def new_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    form.terms_snapshot.data = _default_quote_terms()
    _ensure_default_entries(form)
    parts_data = _get_parts_data()

    return _render_quote_form(ticket, form, "create", parts_data)


@quotes_bp.post("/ticket/<uuid:ticket_id>/create")
@login_required
@permission_required(can_create_quote)
def create_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    _ensure_default_entries(form)
    parts_data = _get_parts_data()

    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        return _render_quote_form(ticket, form, "create", parts_data)

    latest_version = db.session.query(db.func.max(Quote.version)).filter(Quote.ticket_id == ticket.id).scalar() or 0
    quote = Quote(ticket_id=ticket.id, version=int(latest_version) + 1, status="draft")
    db.session.add(quote)
    db.session.flush()

    _save_quote_from_form(quote, form)

    approval = QuoteApproval(quote_id=quote.id, status="pending", language=quote.language)
    db.session.add(approval)
    db.session.commit()

    log_action("quote.create", "Quote", str(quote.id), details={"ticket_id": str(ticket.id), "version": quote.version})
    flash(_("Quote created"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


# ── Standalone quote routes ──────────────────────────────────

@quotes_bp.get("/standalone/new")
@login_required
@permission_required(can_create_quote)
def new_standalone_quote():
    form = QuoteCreateForm()
    form.terms_snapshot.data = _default_quote_terms()
    _ensure_default_entries(form)
    parts_data = _get_parts_data()
    customers = Customer.query.order_by(Customer.full_name.asc()).all()

    return render_template(
        "quotes/standalone_new.html",
        form=form,
        mode="create",
        igic_rate=current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
        parts_data=parts_data,
        customers=customers,
    )


@quotes_bp.post("/standalone/create")
@login_required
@permission_required(can_create_quote)
def create_standalone_quote():
    form = QuoteCreateForm()
    _ensure_default_entries(form)
    parts_data = _get_parts_data()

    customer_id = request.form.get("customer_id") or None
    customer_name = request.form.get("customer_name", "").strip()
    device_description = request.form.get("device_description", "").strip()

    if not customer_id and not customer_name:
        flash(_("Please select or enter a customer"), "error")
        customers = Customer.query.order_by(Customer.full_name.asc()).all()
        return render_template(
            "quotes/standalone_new.html",
            form=form, mode="create",
            igic_rate=current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
            parts_data=parts_data, customers=customers,
        )

    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        customers = Customer.query.order_by(Customer.full_name.asc()).all()
        return render_template(
            "quotes/standalone_new.html",
            form=form, mode="create",
            igic_rate=current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
            parts_data=parts_data, customers=customers,
        )

    customer_uuid = uuid.UUID(str(customer_id)) if customer_id else None

    quote = Quote(
        ticket_id=None,
        customer_id=customer_uuid,
        customer_name=customer_name or (db.session.get(Customer, customer_uuid).full_name if customer_uuid else "Walk-in"),
        device_description=device_description,
        version=1,
        status="draft",
    )
    db.session.add(quote)
    db.session.flush()

    _save_quote_from_form(quote, form)

    approval = QuoteApproval(quote_id=quote.id, status="pending", language=quote.language)
    db.session.add(approval)
    db.session.commit()

    log_action("quote.create_standalone", "Quote", str(quote.id), details={"customer_name": quote.customer_name})
    flash(_("Standalone quote created"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.get("/list")
@login_required
def list_quotes():
    quotes = Quote.query.order_by(Quote.created_at.desc()).all()
    return render_template("quotes/list.html", quotes=quotes)


# ── Edit / update (works for both ticket-linked and standalone) ──

@quotes_bp.get("/<uuid:quote_id>/edit")
@login_required
@permission_required(can_create_quote)
def edit_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm(obj=quote)
    while len(form.options.entries):
        form.options.pop_entry()
    for option in quote.options:
        opt = form.options.append_entry({"name": option.name})
        while len(opt.form.lines.entries):
            opt.form.lines.pop_entry()
        for line in option.lines:
            opt.form.lines.append_entry(
                {
                    "line_type": line.line_type,
                    "linked_part_id": str(line.part_id) if line.part_id else "",
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                }
            )
        opt.form.lines.append_entry()
    if not form.options:
        _ensure_default_entries(form)
    parts_data = _get_parts_data()

    if quote.ticket_id:
        return _render_quote_form(quote.ticket, form, "edit", parts_data, quote=quote)
    else:
        customers = Customer.query.order_by(Customer.full_name.asc()).all()
        return render_template(
            "quotes/standalone_new.html",
            form=form, mode="edit", quote=quote,
            igic_rate=current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
            parts_data=parts_data, customers=customers,
        )


@quotes_bp.post("/<uuid:quote_id>/update")
@login_required
@permission_required(can_create_quote)
def update_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    parts_data = _get_parts_data()
    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        if quote.ticket_id:
            return _render_quote_form(quote.ticket, form, "edit", parts_data, quote=quote)
        else:
            customers = Customer.query.order_by(Customer.full_name.asc()).all()
            return render_template(
                "quotes/standalone_new.html",
                form=form, mode="edit", quote=quote,
                igic_rate=current_app.config.get("DEFAULT_IGIC_RATE", 0.07),
                parts_data=parts_data, customers=customers,
            )

    # Update standalone quote metadata if present
    if not quote.ticket_id:
        customer_id = request.form.get("customer_id") or None
        quote.customer_name = request.form.get("customer_name", "").strip() or quote.customer_name
        quote.device_description = request.form.get("device_description", "").strip()
        if customer_id:
            quote.customer_id = uuid.UUID(str(customer_id))

    _save_quote_from_form(quote, form)
    db.session.commit()
    flash(_("Quote updated"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


# ── Detail / actions ──────────────────────────────────

@quotes_bp.get("/<uuid:quote_id>")
@login_required
def quote_detail(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    option_totals, quote_total = compute_quote_totals(quote)
    igic_rate = Decimal(str(current_app.config.get("DEFAULT_IGIC_RATE", 0.07)))
    tax_total = quote_total * igic_rate
    grand_total = quote_total + tax_total
    latest_diag = None
    if quote.ticket_id:
        latest_diag = Diagnostic.query.filter_by(ticket_id=quote.ticket_id).order_by(Diagnostic.created_at.desc()).first()
    return render_template(
        "quotes/detail.html",
        quote=quote,
        option_totals=option_totals,
        quote_total=quote_total,
        igic_rate=igic_rate,
        tax_total=tax_total,
        grand_total=grand_total,
        latest_diag=latest_diag,
    )


@quotes_bp.post("/<uuid:quote_id>/send")
@login_required
@permission_required(can_manage_quote)
def send_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    set_quote_status(quote, "sent")
    if quote.ticket:
        quote.ticket.internal_status = "awaiting_quote_approval"
    db.session.commit()

    log_action("quote.send", "Quote", str(quote.id), details={"ticket_id": str(quote.ticket_id) if quote.ticket_id else None})
    flash(_("Quote sent for approval"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.post("/<uuid:quote_id>/mark-expired")
@login_required
@permission_required(can_manage_quote)
def mark_expired(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    quote.status = "expired"
    if quote.ticket:
        quote.ticket.internal_status = "awaiting_quote_approval"
    db.session.commit()
    log_action("quote.expire", "Quote", str(quote.id), details={"ticket_id": str(quote.ticket_id) if quote.ticket_id else None})
    flash(_("Quote marked as expired"), "info")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.post("/<uuid:quote_id>/manual-approval")
@login_required
@permission_required(can_manage_quote)
def manual_approval(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    decision = request.form.get("decision", "approved")
    approval = QuoteApproval(
        quote_id=quote.id,
        status=decision,
        method="in_store_manual",
        actor_name=request.form.get("actor_name") or "In-store",
        actor_contact=request.form.get("actor_contact"),
        approved_at=datetime.utcnow(),
        language=quote.language,
    )
    db.session.add(approval)

    if decision == "approved":
        quote.status = "approved"
        if quote.ticket:
            quote.ticket.internal_status = "in_repair"
    else:
        quote.status = "declined"
        if quote.ticket:
            quote.ticket.internal_status = "awaiting_quote_approval"

    db.session.commit()
    log_action("quote.manual_decision", "QuoteApproval", str(approval.id), details={"quote_id": str(quote.id), "decision": decision})
    flash(_("Manual quote decision recorded"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.post("/<uuid:quote_id>/create-ticket")
@login_required
@permission_required(can_create_ticket)
def create_ticket_from_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("quotes.list_quotes"))
    if quote.ticket_id:
        flash(_("This quote already has a ticket"), "info")
        return redirect(url_for("quotes.quote_detail", quote_id=quote.id))

    branch = Branch.query.first()
    customer = db.session.get(Customer, quote.customer_id) if quote.customer_id else None

    # Find or create device based on quote device_description
    device = None
    if customer and quote.device_description:
        device = Device.query.filter_by(customer_id=customer.id).first()
    if not device and customer:
        device = Device(customer=customer, category="other", brand=quote.device_description or "Unknown", model="From Quote")
        db.session.add(device)
        db.session.flush()

    now = datetime.utcnow()
    seq = Ticket.query.count() + 1
    sla_days = current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)

    ticket = Ticket(
        ticket_number=generate_ticket_number(branch.code if branch else "HQ", seq),
        branch_id=branch.id if branch else None,
        customer_id=customer.id if customer else None,
        device_id=device.id if device else None,
        internal_status="in_repair",
        customer_status="In Progress",
        priority="normal",
        sla_target_at=default_sla_target(now, sla_days),
    )
    db.session.add(ticket)
    db.session.flush()

    quote.ticket_id = ticket.id
    db.session.commit()

    log_action("ticket.create_from_quote", "Ticket", str(ticket.id), details={"quote_id": str(quote.id)})
    flash(_("Ticket %(number)s created from quote", number=ticket.ticket_number), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))
