import uuid
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.quote_forms import QuoteCreateForm
from app.models import Part, Quote, QuoteApproval, QuoteLine, QuoteOption, Ticket
from app.services.audit_service import log_action
from app.services.quote_service import compute_quote_totals, set_quote_status


quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")


def _populate_part_choices(form: QuoteCreateForm):
    choices = [("", "-- No linked part --")] + [
        (str(part.id), f"{part.sku} - {part.name}") for part in Part.query.filter(Part.is_active.is_(True)).order_by(Part.name.asc()).all()
    ]
    for option in form.options.entries:
        for line in option.form.lines.entries:
            line.form.linked_part_id.choices = choices


def _ensure_default_entries(form: QuoteCreateForm):
    if not form.options:
        form.options.append_entry()
    if not form.options[0].form.lines:
        for _ in range(3):
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
        if not (option_form.form.name.data or "").strip():
            continue
        option = QuoteOption(quote_id=quote.id, name=option_form.form.name.data.strip(), position=idx)
        db.session.add(option)
        db.session.flush()

        for line_form in option_form.form.lines.entries:
            description = (line_form.form.description.data or "").strip()
            quantity = line_form.form.quantity.data
            unit_price = line_form.form.unit_price.data
            if not description:
                continue
            if quantity is None or unit_price is None:
                continue
            db.session.add(
                QuoteLine(
                    option_id=option.id,
                    line_type=line_form.form.line_type.data,
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    part_id=uuid.UUID(str(line_form.form.linked_part_id.data)) if line_form.form.linked_part_id.data else None,
                )
            )


@quotes_bp.get("/ticket/<uuid:ticket_id>/new")
@login_required
def new_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    _ensure_default_entries(form)
    _populate_part_choices(form)

    return render_template("quotes/new.html", ticket=ticket, form=form, mode="create")


@quotes_bp.post("/ticket/<uuid:ticket_id>/create")
@login_required
def create_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    _ensure_default_entries(form)
    _populate_part_choices(form)

    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        return render_template("quotes/new.html", ticket=ticket, form=form, mode="create")

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


@quotes_bp.get("/<uuid:quote_id>/edit")
@login_required
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
    _populate_part_choices(form)

    return render_template("quotes/new.html", ticket=quote.ticket, form=form, mode="edit", quote=quote)


@quotes_bp.post("/<uuid:quote_id>/update")
@login_required
def update_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    _populate_part_choices(form)
    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        return render_template("quotes/new.html", ticket=quote.ticket, form=form, mode="edit", quote=quote)

    _save_quote_from_form(quote, form)
    db.session.commit()
    flash(_("Quote updated"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.get("/<uuid:quote_id>")
@login_required
def quote_detail(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    option_totals, quote_total = compute_quote_totals(quote)
    return render_template("quotes/detail.html", quote=quote, option_totals=option_totals, quote_total=quote_total)


@quotes_bp.post("/<uuid:quote_id>/send")
@login_required
def send_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    set_quote_status(quote, "sent")
    quote.ticket.internal_status = "awaiting_quote_approval"
    db.session.commit()

    log_action("quote.send", "Quote", str(quote.id), details={"ticket_id": str(quote.ticket_id)})
    flash(_("Quote sent for approval"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.post("/<uuid:quote_id>/mark-expired")
@login_required
def mark_expired(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        flash(_("Quote not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    quote.status = "expired"
    quote.ticket.internal_status = "awaiting_quote_approval"
    db.session.commit()
    log_action("quote.expire", "Quote", str(quote.id), details={"ticket_id": str(quote.ticket_id)})
    flash(_("Quote marked as expired"), "info")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))


@quotes_bp.post("/<uuid:quote_id>/manual-approval")
@login_required
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
        quote.ticket.internal_status = "in_repair"
    else:
        quote.status = "declined"
        quote.ticket.internal_status = "awaiting_quote_approval"

    db.session.commit()
    log_action("quote.manual_decision", "QuoteApproval", str(approval.id), details={"quote_id": str(quote.id), "decision": decision})
    flash(_("Manual quote decision recorded"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))
