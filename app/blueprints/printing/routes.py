"""Print routes for quotes, tickets, checklists, and labels."""
import uuid
from decimal import Decimal

from flask import Blueprint, current_app, render_template
from flask_login import login_required
from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.models import Diagnostic, Quote, RepairChecklist, Ticket, TicketNote
from app.services.document_service import customer_block, generate_qr_data_uri, resolve_branch_identity
from app.services.quote_service import compute_quote_totals

printing_bp = Blueprint("printing", __name__, url_prefix="/print")


@printing_bp.get("/quote/<uuid:quote_id>")
@login_required
def print_quote(quote_id):
    quote = db.session.get(Quote, quote_id)
    if not quote:
        return "Quote not found", 404

    # Resolve branch from ticket or first branch
    branch = None
    if quote.ticket:
        branch = quote.ticket.branch
    if not branch:
        from app.models import Branch
        branch = Branch.query.first()

    identity = resolve_branch_identity(branch)
    customer = quote.resolved_customer
    customer_info = customer_block(customer)

    option_totals, quote_total = compute_quote_totals(quote)
    igic_rate = Decimal(str(current_app.config.get("DEFAULT_IGIC_RATE", 0.07)))
    tax_total = quote_total * igic_rate
    grand_total = quote_total + tax_total

    latest_diag = None
    if quote.ticket_id:
        latest_diag = Diagnostic.query.filter_by(ticket_id=quote.ticket_id).order_by(Diagnostic.created_at.desc()).first()

    # QR code with quote reference
    ref = quote.ticket.ticket_number if quote.ticket else f"Q-v{quote.version}"
    qr_data_uri = generate_qr_data_uri(ref)

    return render_template(
        "print/quote.html",
        quote=quote, identity=identity, customer_info=customer_info,
        option_totals=option_totals, quote_total=quote_total,
        igic_rate=igic_rate, tax_total=tax_total, grand_total=grand_total,
        latest_diag=latest_diag, qr_data_uri=qr_data_uri,
    )


@printing_bp.get("/ticket/<uuid:ticket_id>")
@login_required
def print_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return "Ticket not found", 404

    identity = resolve_branch_identity(ticket.branch)
    customer_info = customer_block(ticket.customer)

    # Get intake notes (first internal note usually has intake details)
    ticket_uuid = uuid.UUID(str(ticket.id))
    intake_notes = TicketNote.query.filter_by(
        ticket_id=ticket_uuid, note_type="internal"
    ).order_by(TicketNote.created_at.asc()).limit(3).all()

    # Latest diagnosis
    latest_diagnosis = Diagnostic.query.filter_by(ticket_id=ticket_uuid).order_by(Diagnostic.created_at.desc()).first()

    # Pre-repair check items
    pre_checks = []
    if sa_inspect(db.engine).has_table("repair_checklists"):
        pre_cl = RepairChecklist.query.filter_by(
            ticket_id=ticket_uuid, checklist_type="pre_repair"
        ).order_by(RepairChecklist.created_at.asc()).first()
        if pre_cl:
            pre_checks = list(pre_cl.items)

    qr_data_uri = generate_qr_data_uri(ticket.ticket_number)

    return render_template(
        "print/ticket.html",
        ticket=ticket, identity=identity, customer_info=customer_info,
        intake_notes=intake_notes, latest_diagnosis=latest_diagnosis,
        pre_checks=pre_checks, qr_data_uri=qr_data_uri,
    )


@printing_bp.get("/ticket/<uuid:ticket_id>/checklist")
@login_required
def print_checklist(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return "Ticket not found", 404

    identity = resolve_branch_identity(ticket.branch)

    checklists = []
    if sa_inspect(db.engine).has_table("repair_checklists"):
        ticket_uuid = uuid.UUID(str(ticket.id))
        checklists = RepairChecklist.query.filter_by(
            ticket_id=ticket_uuid
        ).order_by(RepairChecklist.checklist_type, RepairChecklist.created_at.asc()).all()

    return render_template(
        "print/checklist.html",
        ticket=ticket, identity=identity, checklists=checklists,
    )


@printing_bp.get("/ticket/<uuid:ticket_id>/label/device")
@login_required
def print_device_label(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return "Ticket not found", 404

    identity = resolve_branch_identity(ticket.branch)
    qr_data_uri = generate_qr_data_uri(ticket.ticket_number, box_size=6, border=1)

    return render_template(
        "print/label_device.html",
        ticket=ticket, identity=identity, qr_data_uri=qr_data_uri,
    )


@printing_bp.get("/ticket/<uuid:ticket_id>/label/accessory")
@login_required
def print_accessory_label(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket:
        return "Ticket not found", 404

    identity = resolve_branch_identity(ticket.branch)

    # Parse accessories from intake notes
    ticket_uuid = uuid.UUID(str(ticket.id))
    accessories = []
    notes = TicketNote.query.filter_by(ticket_id=ticket_uuid, note_type="internal").order_by(TicketNote.created_at.asc()).limit(5).all()
    for note in notes:
        if note.content and "Accessories:" in note.content:
            for line in note.content.split("\n"):
                if line.startswith("Accessories:"):
                    acc_text = line.replace("Accessories:", "").strip()
                    if acc_text:
                        accessories = [a.strip() for a in acc_text.split(",") if a.strip()]

    return render_template(
        "print/label_accessory.html",
        ticket=ticket, identity=identity, accessories=accessories,
    )
