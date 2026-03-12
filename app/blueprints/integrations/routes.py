import json

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.models import ExportQueueItem, Ticket
from app.services.export_service import build_ticket_export_payload, queue_ticket_export


integrations_bp = Blueprint("integrations", __name__, url_prefix="/integrations")


@integrations_bp.get("/exports")
@login_required
def export_queue():
    items = ExportQueueItem.query.order_by(ExportQueueItem.created_at.desc()).all()
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(50).all()
    return render_template("integrations/exports.html", items=items, tickets=tickets)


@integrations_bp.post("/exports/ticket/<uuid:ticket_id>/queue")
@login_required
def queue_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("integrations.export_queue"))

    queue_ticket_export(ticket)
    db.session.commit()
    flash(_("Ticket export queued"), "success")
    return redirect(url_for("integrations.export_queue"))


@integrations_bp.get("/exports/ticket/<uuid:ticket_id>/preview")
@login_required
def preview_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("integrations.export_queue"))

    payload = build_ticket_export_payload(ticket)
    return render_template("integrations/preview.html", ticket=ticket, payload=json.dumps(payload, indent=2, ensure_ascii=False))
