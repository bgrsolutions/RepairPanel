from flask import Blueprint, flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.diagnostic_forms import DiagnosticForm
from app.models import Diagnostic, Ticket
from app.services.audit_service import log_action


diagnostics_bp = Blueprint("diagnostics", __name__, url_prefix="/diagnostics")


@diagnostics_bp.post("/ticket/<uuid:ticket_id>/save")
@login_required
def save_ticket_diagnostic(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("tickets.list_tickets"))

    form = DiagnosticForm()
    if not form.validate_on_submit():
        flash(_("Invalid diagnostic submission"), "error")
        return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))

    latest = (
        Diagnostic.query.filter_by(ticket_id=ticket.id)
        .order_by(Diagnostic.version.desc(), Diagnostic.created_at.desc())
        .first()
    )
    next_version = 1 if latest is None else latest.version + 1

    entry = Diagnostic(
        ticket_id=ticket.id,
        version=next_version,
        entered_by_user_id=current_user.id,
        customer_reported_fault=form.customer_reported_fault.data,
        technician_diagnosis=form.technician_diagnosis.data,
        recommended_repair=form.recommended_repair.data,
        estimated_labour=form.estimated_labour.data,
        repair_notes=form.repair_notes.data,
    )
    db.session.add(entry)
    db.session.commit()

    log_action(
        "diagnostic.save",
        "Diagnostic",
        str(entry.id),
        details={"ticket_id": str(ticket.id), "version": entry.version},
    )
    flash(_("Diagnosis saved"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))
