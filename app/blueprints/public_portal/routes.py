import secrets
import uuid
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.forms.intake_forms import PublicIntakeForm
from app.forms.public_forms import PublicQuoteApprovalForm, PublicStatusLookupForm
from app.models import (
    Attachment,
    Branch,
    Customer,
    Device,
    IntakeDisclaimerAcceptance,
    IntakeSignature,
    IntakeSubmission,
    PortalToken,
    Quote,
    QuoteApproval,
    Ticket,
)
from app.services.audit_service import log_action
from app.utils.file_uploads import save_intake_file


public_portal_bp = Blueprint("public_portal", __name__, url_prefix="/public")


def _new_intake_reference() -> str:
    return f"INT-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


@public_portal_bp.route("/check-in", methods=["GET", "POST"])
def public_checkin():
    return _render_public_checkin(kiosk_mode=False)


@public_portal_bp.route("/kiosk/check-in", methods=["GET", "POST"])
def kiosk_checkin():
    return _render_public_checkin(kiosk_mode=True)


def _render_public_checkin(kiosk_mode: bool):
    form = PublicIntakeForm()
    branches = Branch.query.filter(Branch.deleted_at.is_(None), Branch.is_active.is_(True)).order_by(Branch.code).all()
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in branches]

    if form.validate_on_submit():
        branch = db.session.get(Branch, uuid.UUID(str(form.branch_id.data)))

        customer = None
        if form.customer_email.data:
            customer = Customer.query.filter_by(email=form.customer_email.data.lower().strip()).first()
        if customer is None:
            customer = Customer.query.filter_by(phone=form.customer_phone.data.strip()).first()
        if customer is None:
            customer = Customer(
                full_name=form.customer_name.data,
                phone=form.customer_phone.data,
                email=form.customer_email.data.lower().strip() if form.customer_email.data else None,
                preferred_language=form.preferred_language.data,
                primary_branch=branch,
            )
            db.session.add(customer)
            db.session.flush()

        device = None
        if form.serial_number.data:
            device = Device.query.filter_by(serial_number=form.serial_number.data.strip()).first()
        if device is None and form.imei.data:
            device = Device.query.filter_by(imei=form.imei.data.strip()).first()
        if device is None:
            device = Device(
                customer=customer,
                category=form.category.data,
                brand=form.device_brand.data,
                model=form.device_model.data,
                serial_number=form.serial_number.data.strip() if form.serial_number.data else None,
                imei=form.imei.data.strip() if form.imei.data else None,
            )
            db.session.add(device)
            db.session.flush()

        intake = IntakeSubmission(
            reference=_new_intake_reference(),
            source="kiosk" if kiosk_mode else "public",
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

        db.session.add(
            PortalToken(
                token=secrets.token_urlsafe(24),
                token_type="public_intake_confirmation",
                intake_submission_id=intake.id,
            )
        )
        db.session.commit()

        return redirect(url_for("public_portal.public_checkin_thank_you", reference=intake.reference, kiosk=int(kiosk_mode)))

    return render_template("public/check_in.html", form=form, kiosk_mode=kiosk_mode)


@public_portal_bp.get("/check-in/thank-you")
def public_checkin_thank_you():
    reference = request.args.get("reference")
    kiosk_mode = request.args.get("kiosk", "0") == "1"
    return render_template("public/thank_you.html", reference=reference, kiosk_mode=kiosk_mode)


@public_portal_bp.route("/status", methods=["GET", "POST"])
def public_status_lookup():
    form = PublicStatusLookupForm()
    lookup_result = None
    quote_pending = False

    if form.validate_on_submit():
        ticket_number = (form.ticket_number.data or "").strip()
        verifier = (form.verifier.data or "").strip().lower()

        ticket = Ticket.query.filter(Ticket.ticket_number == ticket_number, Ticket.deleted_at.is_(None)).first()
        if ticket and verifier and verifier in {(ticket.customer.email or "").lower(), (ticket.customer.phone or "").lower()}:
            active_quote = (
                Quote.query.filter(Quote.ticket_id == ticket.id)
                .order_by(Quote.version.desc(), Quote.created_at.desc())
                .first()
            )
            quote_pending = bool(active_quote and active_quote.status in {"sent", "draft"})
            lookup_result = {
                "ticket_number": ticket.ticket_number,
                "device_summary": f"{ticket.device.brand} {ticket.device.model}",
                "customer_status": ticket.customer_status,
                "ready_for_collection": ticket.customer_status.lower() == "ready for collection",
                "quote_pending": quote_pending,
                "estimated_completion": "TBD",
            }
        else:
            flash(_("No repair record found for the provided details"), "error")

    return render_template("public/status.html", form=form, lookup_result=lookup_result, quote_pending=quote_pending)


@public_portal_bp.route("/quote/<token>", methods=["GET", "POST"])
def public_quote_approval(token):
    approval = QuoteApproval.query.filter_by(token=token).first()
    if not approval:
        flash(_("Invalid quote approval link"), "error")
        return redirect(url_for("public_portal.public_status_lookup"))

    quote = approval.quote
    form = PublicQuoteApprovalForm()
    expired = approval.expires_at and approval.expires_at < datetime.utcnow()

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

            quote.status = decision
            quote.ticket.internal_status = "Quote Approved" if decision == "approved" else "On Hold"

            db.session.commit()
            try:
                log_action(
                    "quote.public_decision",
                    "QuoteApproval",
                    str(approval.id),
                    details={"quote_id": str(quote.id), "decision": decision},
                )
            except Exception:
                db.session.rollback()

            flash(_("Your quote decision has been recorded"), "success")
            return redirect(url_for("public_portal.public_quote_approval", token=token))

    if expired and quote.status == "sent":
        quote.status = "expired"
        quote.ticket.internal_status = "On Hold"
        db.session.commit()

    return render_template("public/quote_approval.html", approval=approval, quote=quote, expired=expired, form=form)
