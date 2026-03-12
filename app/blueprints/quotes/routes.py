from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.quote_forms import QuoteCreateForm
from app.models import Quote, QuoteApproval, QuoteLine, QuoteOption, Ticket
from app.services.audit_service import log_action
from app.services.quote_service import compute_quote_totals, set_quote_status


quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")


@quotes_bp.get("/ticket/<uuid:ticket_id>/new")
@login_required
def new_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    if not form.options:
        form.options.append_entry()
    if not form.options[0].form.lines:
        form.options[0].form.lines.append_entry()

    return render_template("quotes/new.html", ticket=ticket, form=form)


@quotes_bp.post("/ticket/<uuid:ticket_id>/create")
@login_required
def create_quote(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = QuoteCreateForm()
    if not form.validate_on_submit():
        flash(_("Invalid quote data"), "error")
        return redirect(url_for("quotes.new_quote", ticket_id=ticket.id))

    latest_version = db.session.query(db.func.max(Quote.version)).filter(Quote.ticket_id == ticket.id).scalar() or 0
    quote = Quote(
        ticket_id=ticket.id,
        version=int(latest_version) + 1,
        status="draft",
        currency=form.currency.data,
        language=form.language.data,
        notes_snapshot=form.notes_snapshot.data,
        terms_snapshot=form.terms_snapshot.data,
        expires_at=datetime.combine(form.expires_at.data, datetime.min.time()) if form.expires_at.data else None,
    )
    db.session.add(quote)
    db.session.flush()

    for idx, option_form in enumerate(form.options.entries, start=1):
        option = QuoteOption(quote_id=quote.id, name=option_form.form.name.data, position=idx)
        db.session.add(option)
        db.session.flush()
        for line_form in option_form.form.lines.entries:
            line = QuoteLine(
                option_id=option.id,
                line_type=line_form.form.line_type.data,
                description=line_form.form.description.data,
                quantity=line_form.form.quantity.data,
                unit_price=line_form.form.unit_price.data,
            )
            db.session.add(line)

    approval = QuoteApproval(
        quote_id=quote.id,
        status="pending",
        language=quote.language,
    )
    db.session.add(approval)

    db.session.commit()

    log_action("quote.create", "Quote", str(quote.id), details={"ticket_id": str(ticket.id), "version": quote.version})
    flash(_("Quote created"), "success")
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
    quote.ticket.internal_status = "Awaiting Quote Approval"
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
    quote.ticket.internal_status = "On Hold"
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
        quote.ticket.internal_status = "Quote Approved"
    else:
        quote.status = "declined"
        quote.ticket.internal_status = "On Hold"

    db.session.commit()
    log_action("quote.manual_decision", "QuoteApproval", str(approval.id), details={"quote_id": str(quote.id), "decision": decision})
    flash(_("Manual quote decision recorded"), "success")
    return redirect(url_for("quotes.quote_detail", quote_id=quote.id))
