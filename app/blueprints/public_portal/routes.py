import uuid
import secrets
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.forms.intake_forms import PublicIntakeForm
from app.models import (
    Attachment,
    Branch,
    Customer,
    Device,
    IntakeDisclaimerAcceptance,
    IntakeSignature,
    IntakeSubmission,
    PortalToken,
)
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
