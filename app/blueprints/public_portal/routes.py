import uuid
import secrets
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import inspect

from app.extensions import db
from app.forms.intake_forms import PublicIntakeForm
from app.forms.public_forms import PublicContactUpdateForm, PublicQuoteApprovalForm, PublicStatusLookupForm
from app.models import (
    Attachment,
    Branch,
    Customer,
    Device,
    IntakeDisclaimerAcceptance,
    IntakeSignature,
    IntakeSubmission,
    Part,
    PortalToken,
    Quote,
    QuoteApproval,
    RepairChecklist,
    Ticket,
    TicketNote,
)
from app.services.audit_service import log_action
from app.services.customer_status_service import (
    CUSTOMER_SAFE_NOTE_TYPES,
    communication_summary,
    customer_friendly_status,
    progress_step_index,
    progress_steps,
)
from app.services.payment_service import create_quote_checkout_session
from app.services.quote_service import compute_quote_totals
from app.utils.file_uploads import save_intake_file
from app.utils.ticketing import normalize_ticket_status


public_portal_bp = Blueprint("public_portal", __name__, url_prefix="/public")


def _new_intake_reference() -> str:
    return f"INT-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def _safe_exact_customer_match(email: str | None, phone: str | None):
    email = (email or "").strip().lower()
    phone = (phone or "").strip()
    customer = None
    if email and "@" in email and len(email) >= 6:
        customer = Customer.query.filter_by(email=email).first()
    if customer is None and phone and len(phone) >= 7:
        customer = Customer.query.filter_by(phone=phone).first()
    return customer


@public_portal_bp.route("/check-in", methods=["GET", "POST"])
def public_checkin():
    return _render_public_checkin(kiosk_mode=False)


@public_portal_bp.route("/kiosk/check-in", methods=["GET", "POST"])
def kiosk_checkin():
    return _render_public_checkin(kiosk_mode=True)


def _render_public_checkin(kiosk_mode: bool):
    form = PublicIntakeForm()
    branches = Branch.query.filter(Branch.deleted_at.is_(None), Branch.is_active.is_(True)).order_by(Branch.code.asc()).all()
    form.branch_id.choices = [(str(branch.id), f"{branch.code} - {branch.name}") for branch in branches]

    if form.validate_on_submit():
        branch = db.session.get(Branch, uuid.UUID(str(form.branch_id.data)))
        if not branch:
            flash(_("Branch not found"), "error")
            return render_template("public/check_in.html", form=form, kiosk_mode=kiosk_mode)

        matched_customer = _safe_exact_customer_match(form.customer_email.data, form.customer_phone.data)
        customer = matched_customer or Customer(
            full_name=form.customer_name.data,
            phone=form.customer_phone.data,
            email=form.customer_email.data,
            preferred_language=form.preferred_language.data,
            primary_branch=branch,
        )
        if not matched_customer:
            db.session.add(customer)
            db.session.flush()

        device = Device(
            customer_id=customer.id,
            category=form.category.data,
            brand=form.device_brand.data,
            model=form.device_model.data,
            serial_number=form.serial_number.data,
            imei=form.imei.data,
        )
        db.session.add(device)
        db.session.flush()

        intake = IntakeSubmission(
            reference=_new_intake_reference(),
            source="public" if not kiosk_mode else "kiosk",
            status="pre_check_in",
            branch=branch,
            customer=customer,
            device=device,
            category=form.category.data,
            customer_name=form.customer_name.data,
            customer_phone=form.customer_phone.data,
            customer_email=form.customer_email.data,
            device_brand=form.device_brand.data,
            device_model=form.device_model.data,
            serial_number=form.serial_number.data,
            imei=form.imei.data,
            reported_fault=form.reported_fault.data,
            accessories=form.accessories.data,
            intake_notes=form.intake_notes.data,
            preferred_language=form.preferred_language.data,
            preferred_contact_method=form.preferred_contact_method.data,
        )
        db.session.add(intake)
        db.session.flush()

        db.session.add(
            IntakeDisclaimerAcceptance(
                intake_submission_id=intake.id,
                disclaimer_key="general_intake",
                disclaimer_text=current_app.config["DEFAULT_INTAKE_DISCLAIMER_TEXT"],
                accepted=bool(form.accepted_disclaimer.data),
            )
        )

        if form.signature_data.data:
            db.session.add(
                IntakeSignature(
                    intake_submission_id=intake.id,
                    signer_name=form.customer_name.data,
                    signature_data=form.signature_data.data,
                    signed_at=datetime.utcnow(),
                )
            )

        if form.photo.data:
            try:
                storage_path, size = save_intake_file(current_app.config["UPLOAD_ROOT"], intake.reference, form.photo.data)
                db.session.add(
                    Attachment(
                        intake_submission_id=intake.id,
                        original_filename=form.photo.data.filename or "upload.bin",
                        storage_path=storage_path,
                        mime_type=form.photo.data.mimetype,
                        byte_size=size,
                        is_public_upload=True,
                    )
                )
            except ValueError:
                flash(_("Unsupported attachment file type"), "error")

        db.session.add(PortalToken(token=secrets.token_urlsafe(24), token_type="public_intake_confirmation", intake_submission_id=intake.id))
        db.session.commit()

        return redirect(url_for("public_portal.public_checkin_thank_you", reference=intake.reference, kiosk=int(kiosk_mode)))

    return render_template("public/check_in.html", form=form, kiosk_mode=kiosk_mode)


@public_portal_bp.get("/check-in/thank-you")
def public_checkin_thank_you():
    reference = request.args.get("reference")
    kiosk_mode = request.args.get("kiosk", "0") == "1"
    return render_template("public/thank_you.html", reference=reference, kiosk_mode=kiosk_mode)


def _build_lookup_result(ticket):
    """Build the customer-safe lookup result dict for a ticket."""
    internal_status = normalize_ticket_status(ticket.internal_status)
    active_quote = Quote.query.filter(Quote.ticket_id == ticket.id).order_by(Quote.version.desc(), Quote.created_at.desc()).first()

    customer_updates = []
    if inspect(db.engine).has_table("ticket_notes"):
        notes = TicketNote.query.filter_by(ticket_id=ticket.id).order_by(TicketNote.created_at.desc()).all()
        customer_updates = [n for n in notes if n.note_type in CUSTOMER_SAFE_NOTE_TYPES]

    checklists = []
    if inspect(db.engine).has_table("repair_checklists"):
        checklists = RepairChecklist.query.filter_by(ticket_id=ticket.id).order_by(RepairChecklist.created_at.desc()).all()

    has_pending_quote = active_quote is not None and active_quote.status in ("draft", "sent")
    has_pending_parts = internal_status == Ticket.STATUS_AWAITING_PARTS

    return {
        "ticket": ticket,
        "ticket_number": ticket.ticket_number,
        "device_summary": f"{ticket.device.brand} {ticket.device.model}",
        "customer_status": ticket.customer_status,
        "internal_status": internal_status,
        "friendly_status": customer_friendly_status(internal_status),
        "ready_for_collection": internal_status == Ticket.STATUS_READY_FOR_COLLECTION,
        "quote": active_quote,
        "has_pending_quote": has_pending_quote,
        "estimated_completion": ticket.quoted_completion_at.strftime("%Y-%m-%d %H:%M") if ticket.quoted_completion_at else None,
        "customer_updates": customer_updates,
        "checklists": checklists,
        "communication_summary": communication_summary(internal_status, has_pending_quote=has_pending_quote, has_pending_parts=has_pending_parts),
        "progress_steps": progress_steps(),
        "current_step": progress_step_index(internal_status),
        "created_at": ticket.created_at.strftime("%b %d, %Y") if ticket.created_at else None,
    }


def _get_or_create_status_token(ticket) -> str:
    """Get or create a public status lookup token for a ticket."""
    existing = PortalToken.query.filter_by(ticket_id=ticket.id, token_type="public_status_lookup").first()
    if existing:
        return existing.token
    token = secrets.token_urlsafe(24)
    db.session.add(PortalToken(token=token, token_type="public_status_lookup", ticket_id=ticket.id))
    db.session.flush()
    return token


@public_portal_bp.route("/status", methods=["GET", "POST"])
def public_status_lookup():
    form = PublicStatusLookupForm()
    contact_form = PublicContactUpdateForm()
    lookup_result = None

    if form.validate_on_submit():
        ticket_number = (form.ticket_number.data or "").strip()
        verifier = (form.verifier.data or "").strip().lower()

        ticket = Ticket.query.filter(Ticket.ticket_number == ticket_number, Ticket.deleted_at.is_(None)).first()
        if ticket and verifier and verifier in {(ticket.customer.email or "").lower(), (ticket.customer.phone or "").lower()}:
            lookup_result = _build_lookup_result(ticket)
            contact_form.contact_person.data = ticket.customer.full_name
            contact_form.contact_phone.data = ticket.customer.phone
            contact_form.contact_email.data = ticket.customer.email
        else:
            flash(_("No repair record found for the provided details"), "error")

    return render_template("public/status.html", form=form, lookup_result=lookup_result, contact_form=contact_form)


@public_portal_bp.get("/repair/<token>")
def public_repair_status(token):
    """Direct token-based access to repair status — no login or verifier needed.

    Security hardening (Phase 12):
    - Token must be exactly the expected length range (20-50 chars) to reject garbage
    - Token must match type "public_status_lookup" exactly
    - Expired tokens (expires_at in the past) are rejected
    - Revoked tokens (deleted from DB) naturally fail lookup
    """
    # Basic token format validation — reject obviously invalid tokens early
    if not token or len(token) < 20 or len(token) > 50:
        flash(_("Invalid or expired repair status link"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    portal_token = PortalToken.query.filter_by(token=token, token_type="public_status_lookup").first()
    if not portal_token or not portal_token.ticket_id:
        flash(_("Invalid or expired repair status link"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    # Check token expiry if set
    if portal_token.expires_at and portal_token.expires_at < datetime.utcnow():
        flash(_("This repair status link has expired"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    ticket = db.session.get(Ticket, portal_token.ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Repair record not found"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    lookup_result = _build_lookup_result(ticket)
    contact_form = PublicContactUpdateForm()
    contact_form.contact_person.data = ticket.customer.full_name
    contact_form.contact_phone.data = ticket.customer.phone
    contact_form.contact_email.data = ticket.customer.email

    return render_template("public/status.html", form=None, lookup_result=lookup_result, contact_form=contact_form, token_access=True)


@public_portal_bp.post("/status/<uuid:ticket_id>/contact")
def public_status_contact_update(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if not ticket or ticket.deleted_at is not None:
        flash(_("Ticket not found"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    form = PublicContactUpdateForm()
    if form.validate_on_submit():
        if form.contact_person.data:
            ticket.customer.full_name = form.contact_person.data
        ticket.customer.phone = form.contact_phone.data
        ticket.customer.email = form.contact_email.data
        if form.remarks.data and inspect(db.engine).has_table("ticket_notes"):
            db.session.add(TicketNote(ticket_id=ticket.id, note_type="customer_update", content=f"Customer remarks: {form.remarks.data}"))
        db.session.commit()
        flash(_("Contact preferences updated"), "success")
    else:
        flash(_("Invalid contact update"), "error")
    return redirect(url_for("public_portal.public_status_lookup"))


@public_portal_bp.get("/quote/Q-<int:version>/<token>")
def public_quote_approval_friendly(version, token):
    """Friendly URL that includes human-readable quote reference; delegates to the same logic."""
    return public_quote_approval(token)


@public_portal_bp.route("/quote/<token>", methods=["GET", "POST"])
def public_quote_approval(token):
    approval = QuoteApproval.query.filter_by(token=token).first()
    if not approval:
        flash(_("Invalid quote approval link"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    quote = approval.quote

    # Build a human-readable quote reference
    quote_ref = f"Q-{quote.version}"
    if quote.ticket:
        quote_ref_full = f"{quote.ticket.ticket_number} / {quote_ref}"
    else:
        quote_ref_full = quote_ref

    form = PublicQuoteApprovalForm()
    expired = approval.expires_at and approval.expires_at < datetime.utcnow()
    option_totals, quote_total = compute_quote_totals(quote)
    igic_rate = Decimal(str(current_app.config.get("DEFAULT_IGIC_RATE", 0.07)))
    tax_total = quote_total * igic_rate
    grand_total = quote_total + tax_total

    if form.validate_on_submit() and not expired:
        decision = form.decision.data
        if decision in {"approved", "declined"}:
            approval.status = decision
            approval.method = "portal_token"
            approval.actor_name = form.actor_name.data
            approval.actor_contact = form.actor_contact.data
            approval.language = form.language.data or quote.language
            approval.ip_address = request.remote_addr
            approval.approved_at = datetime.utcnow()
            approval.declined_reason = form.declined_reason.data if decision == "declined" else None
            approval.payment_choice = form.payment_choice.data if decision == "approved" else None

            if decision == "approved":
                quote.status = "approved"
                if quote.ticket:
                    quote.ticket.internal_status = "in_repair"
                if form.payment_choice.data == "pay_now":
                    checkout = create_quote_checkout_session(
                        quote_id=str(quote.id),
                        amount_total=grand_total,
                        currency=quote.currency,
                        success_url=url_for("public_portal.public_quote_approval", token=token, _external=True),
                        cancel_url=url_for("public_portal.public_quote_approval", token=token, _external=True),
                        stripe_secret_key=current_app.config.get("STRIPE_SECRET_KEY"),
                    )
                    approval.payment_status = "pending_online"
                    approval.stripe_session_id = checkout.get("session_id")
                    approval.stripe_checkout_url = checkout.get("checkout_url")
                else:
                    approval.payment_status = "pay_in_store"
            else:
                quote.status = "declined"
                if quote.ticket:
                    quote.ticket.internal_status = "awaiting_quote_approval"
                approval.payment_status = "not_applicable"

            db.session.commit()
            try:
                log_action("quote.public_decision", "QuoteApproval", str(approval.id), details={"quote_id": str(quote.id), "decision": decision, "payment_choice": approval.payment_choice})
            except Exception:
                pass
            # Fire notification event so staff dashboards pick up the change
            try:
                from app.services.notification_service import create_notification_event
                if quote.ticket:
                    event_type = "quote_approved" if decision == "approved" else "quote_declined"
                    create_notification_event(event_type=event_type, ticket=quote.ticket, context={"source": "portal", "quote_id": str(quote.id)})
                    db.session.commit()
            except Exception:
                db.session.rollback()
            flash(_("Your quote decision has been recorded"), "success")
            return redirect(url_for("public_portal.public_quote_approval", token=token))

    if expired and quote.status == "sent":
        quote.status = "expired"
        if quote.ticket:
            quote.ticket.internal_status = "awaiting_quote_approval"
        db.session.commit()

    return render_template("public/quote_approval.html", approval=approval, quote=quote, expired=expired, form=form, option_totals=option_totals, quote_total=quote_total, igic_rate=igic_rate, tax_total=tax_total, grand_total=grand_total, quote_ref=quote_ref, quote_ref_full=quote_ref_full)


@public_portal_bp.get('/quote-payment-placeholder')
def quote_payment_placeholder():
    return render_template('public/thank_you.html', reference='Payment session created. Continue in Stripe checkout.', kiosk_mode=False)
