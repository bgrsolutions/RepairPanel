import uuid
import secrets
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.intake_forms import InternalIntakeForm
from app.models import (
    Attachment,
    Branch,
    Customer,
    Device,
    IntakeDisclaimerAcceptance,
    IntakeSignature,
    IntakeSubmission,
    PortalToken,
    Ticket,
)
from app.services.audit_service import log_action
from app.utils.file_uploads import save_intake_file
from app.utils.ticketing import generate_ticket_number


intake_bp = Blueprint("intake", __name__, url_prefix="/intake")


def _new_intake_reference() -> str:
    return f"INT-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def _find_or_create_customer(name: str, phone: str | None, email: str | None, language: str, branch: Branch) -> Customer:
    customer = None
    if email:
        customer = Customer.query.filter_by(email=email.lower().strip()).first()
    if customer is None and phone:
        customer = Customer.query.filter_by(phone=phone.strip()).first()
    if customer is None:
        customer = Customer(full_name=name.strip(), phone=phone, email=(email.lower().strip() if email else None), preferred_language=language, primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
    return customer


def _find_or_create_device(customer: Customer, category: str, brand: str, model: str, serial_number: str | None, imei: str | None) -> Device:
    device = None
    if serial_number:
        device = Device.query.filter_by(serial_number=serial_number.strip()).first()
    if device is None and imei:
        device = Device.query.filter_by(imei=imei.strip()).first()
    if device is None:
        device = Device(
            customer=customer,
            category=category,
            brand=brand.strip(),
            model=model.strip(),
            serial_number=serial_number.strip() if serial_number else None,
            imei=imei.strip() if imei else None,
        )
        db.session.add(device)
        db.session.flush()
    return device


@intake_bp.get("/")
@login_required
def list_intakes():
    intakes = IntakeSubmission.query.filter(IntakeSubmission.deleted_at.is_(None)).order_by(IntakeSubmission.created_at.desc()).all()
    return render_template("intake/list.html", intakes=intakes)


@intake_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_intake():
    form = InternalIntakeForm()
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.filter(Branch.deleted_at.is_(None)).order_by(Branch.code).all()]

    if form.validate_on_submit():
        branch = db.session.get(Branch, uuid.UUID(str(form.branch_id.data)))
        customer = _find_or_create_customer(
            name=form.customer_name.data,
            phone=form.customer_phone.data,
            email=form.customer_email.data,
            language=getattr(current_user, "preferred_language", "en") or "en",
            branch=branch,
        )
        device = _find_or_create_device(
            customer=customer,
            category=form.category.data,
            brand=form.device_brand.data,
            model=form.device_model.data,
            serial_number=form.serial_number.data,
            imei=form.imei.data,
        )

        intake = IntakeSubmission(
            reference=_new_intake_reference(),
            source="internal",
            status="pre_check_in",
            branch=branch,
            customer=customer,
            device=device,
            submitted_by_user_id=current_user.id,
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
            preferred_language=getattr(current_user, "preferred_language", "en") or "en",
            preferred_contact_method="phone",
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
                        uploaded_by_user_id=current_user.id,
                        is_public_upload=False,
                    )
                )
            except ValueError:
                flash(_("Unsupported attachment file type"), "error")

        db.session.add(
            PortalToken(
                token=secrets.token_urlsafe(24),
                token_type="public_status_lookup",
                intake_submission_id=intake.id,
            )
        )

        db.session.commit()
        log_action("intake.create", "IntakeSubmission", str(intake.id), details={"reference": intake.reference})
        flash(_("Intake created"), "success")
        return redirect(url_for("intake.intake_detail", intake_id=intake.id))

    return render_template("intake/new.html", form=form)


@intake_bp.get("/<uuid:intake_id>")
@login_required
def intake_detail(intake_id):
    intake = db.session.get(IntakeSubmission, intake_id)
    if not intake or intake.deleted_at is not None:
        flash(_("Intake not found"), "error")
        return redirect(url_for("intake.list_intakes"))

    attachments = Attachment.query.filter_by(intake_submission_id=intake.id).all()
    disclaimers = IntakeDisclaimerAcceptance.query.filter_by(intake_submission_id=intake.id).all()
    signatures = IntakeSignature.query.filter_by(intake_submission_id=intake.id).all()
    return render_template(
        "intake/detail.html",
        intake=intake,
        attachments=attachments,
        disclaimers=disclaimers,
        signatures=signatures,
    )


@intake_bp.post("/<uuid:intake_id>/convert")
@login_required
def convert_intake(intake_id):
    intake = db.session.get(IntakeSubmission, intake_id)
    if not intake or intake.deleted_at is not None:
        flash(_("Intake not found"), "error")
        return redirect(url_for("intake.list_intakes"))

    if intake.converted_ticket_id:
        flash(_("Intake already converted"), "info")
        return redirect(url_for("tickets.ticket_detail", ticket_id=intake.converted_ticket_id))

    sequence = Ticket.query.count() + 1
    ticket = Ticket(
        ticket_number=generate_ticket_number(intake.branch.code, sequence),
        branch_id=intake.branch_id,
        customer_id=intake.customer_id,
        device_id=intake.device_id,
        internal_status="unassigned",
        customer_status="Received",
        priority="normal",
    )
    db.session.add(ticket)
    db.session.flush()

    intake.converted_ticket_id = ticket.id
    intake.converted_at = datetime.utcnow()
    intake.status = "converted"
    db.session.commit()

    log_action("intake.convert", "IntakeSubmission", str(intake.id), details={"ticket_id": str(ticket.id)})
    flash(_("Intake converted to ticket"), "success")
    return redirect(url_for("tickets.ticket_detail", ticket_id=ticket.id))


@intake_bp.get("/<uuid:intake_id>/receipt")
@login_required
def intake_receipt(intake_id):
    intake = db.session.get(IntakeSubmission, intake_id)
    if not intake or intake.deleted_at is not None:
        flash(_("Intake not found"), "error")
        return redirect(url_for("intake.list_intakes"))
    return render_template("intake/receipt.html", intake=intake)
