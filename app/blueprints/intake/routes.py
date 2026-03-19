import uuid
import secrets
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import or_

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
    User,
)
from app.services.audit_service import log_action
from app.utils.file_uploads import save_intake_file
from app.utils.ticketing import default_sla_target, generate_ticket_number


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


def _find_or_create_device(customer: Customer, category: str, brand: str, model: str, serial_number: str | None, imei: str | None, **extra) -> Device:
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
    # Update extra device detail fields if provided
    for field in ("storage", "color", "carrier_lock", "fmi_status", "cosmetic_condition",
                  "battery_health", "cpu", "ram", "storage_type", "gpu", "os_info"):
        val = extra.get(field)
        if val:
            setattr(device, field, val)
    return device


@intake_bp.get("/")
@login_required
def list_intakes():
    intakes = IntakeSubmission.query.filter(IntakeSubmission.deleted_at.is_(None)).order_by(IntakeSubmission.created_at.desc()).all()
    return render_template("intake/list.html", intakes=intakes)




@intake_bp.get('/customer-search')
@login_required
def customer_search():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return {"items": []}
    like = f"%{q}%"
    rows = Customer.query.filter(
        Customer.deleted_at.is_(None),
        or_(Customer.full_name.ilike(like), Customer.email.ilike(like), Customer.phone.ilike(like)),
    ).order_by(Customer.full_name.asc()).limit(25).all()
    return {"items": [{"id": str(c.id), "label": f"{c.full_name} · {c.phone or c.email or ''}"} for c in rows]}



@intake_bp.get('/customer/<uuid:customer_id>')
@login_required
def customer_detail_json(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.deleted_at.is_(None)).first()
    if not customer:
        return {"ok": False}, 404
    return {"ok": True, "id": str(customer.id), "full_name": customer.full_name, "phone": customer.phone or "", "email": customer.email or ""}


@intake_bp.post("/imei-lookup")
@login_required
def imei_lookup_json():
    """AJAX: IMEI lookup via IMEIcheck.net."""
    from app.services.imei_lookup_service import is_imei_lookup_configured, lookup_imei
    data = request.get_json(silent=True) or {}
    imei_value = (data.get("imei") or "").strip()
    if not imei_value:
        return {"ok": False, "error": "IMEI is required"}, 400
    if not is_imei_lookup_configured():
        return {"ok": False, "error": "IMEI lookup not configured"}
    service_id = data.get("service_id")
    if service_id is not None:
        try:
            service_id = int(service_id)
        except (ValueError, TypeError):
            service_id = None
    brand_hint = (data.get("brand_hint") or "").strip()
    result = lookup_imei(imei_value, service_id=service_id, brand_hint=brand_hint)
    return {"ok": result.success, **result.to_dict()}


@intake_bp.get("/prechecks/<category>")
@login_required
def get_prechecks_json(category):
    """Return pre-check items for a device category."""
    from app.services.precheck_service import get_prechecks_for_category
    language = request.args.get("lang", "en")
    checks = get_prechecks_for_category(category, language=language)
    return {"checks": checks, "category": category}


@intake_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_intake():
    form = InternalIntakeForm()
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.filter(Branch.deleted_at.is_(None)).order_by(Branch.code).all()]

    if form.validate_on_submit():
        branch = db.session.get(Branch, uuid.UUID(str(form.branch_id.data)))
        existing_customer_id = form.existing_customer_id.data
        customer = db.session.get(Customer, uuid.UUID(existing_customer_id)) if existing_customer_id else None
        if customer is None:
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
            storage=getattr(form, 'storage', None) and form.storage.data,
            color=getattr(form, 'color', None) and form.color.data,
            carrier_lock=getattr(form, 'carrier_lock', None) and form.carrier_lock.data,
            fmi_status=getattr(form, 'fmi_status', None) and form.fmi_status.data,
            cosmetic_condition=getattr(form, 'cosmetic_condition', None) and form.cosmetic_condition.data,
            battery_health=getattr(form, 'battery_health', None) and form.battery_health.data,
            cpu=getattr(form, 'cpu', None) and form.cpu.data,
            ram=getattr(form, 'ram', None) and form.ram.data,
            storage_type=getattr(form, 'storage_type', None) and form.storage_type.data,
            gpu=getattr(form, 'gpu', None) and form.gpu.data,
            os_info=getattr(form, 'os_info', None) and form.os_info.data,
        )

        # Phase 18: Save secure access/unlock data
        unlock_type = getattr(form, 'unlock_type', None) and form.unlock_type.data
        unlock_value = getattr(form, 'unlock_value', None) and form.unlock_value.data
        unlock_notes = getattr(form, 'unlock_notes', None) and form.unlock_notes.data
        if unlock_type:
            from app.services.device_unlock_service import set_device_unlock
            set_device_unlock(device, unlock_type, unlock_value, unlock_notes)

        # Build enriched intake notes including pre-check results and diagnosis
        notes_parts = []
        if form.intake_notes.data:
            notes_parts.append(form.intake_notes.data)
        if form.device_condition.data:
            notes_parts.append(f"Device condition: {form.device_condition.data}")
        pre_checks = []
        for field_name, label in [
            ("check_powers_on", "Powers on"),
            ("check_screen_condition", "Screen OK"),
            ("check_charging", "Charging OK"),
            ("check_buttons", "Buttons OK"),
            ("check_water_damage", "No water damage"),
        ]:
            field = getattr(form, field_name)
            if field.data:
                pre_checks.append(f"[x] {label}")
            else:
                pre_checks.append(f"[ ] {label}")
        if any(getattr(form, f).data for f in ["check_powers_on", "check_screen_condition", "check_charging", "check_buttons", "check_water_damage"]):
            notes_parts.append("Pre-check: " + ", ".join(pre_checks))
        # Phase 18: Dynamic pre-checks from device-type-specific forms
        from app.services.precheck_service import parse_precheck_results, format_precheck_notes
        dynamic_checks = parse_precheck_results(request.form, form.category.data)
        any_checked = any(c["passed"] for c in dynamic_checks)
        if any_checked:
            notes_parts.append(format_precheck_notes(dynamic_checks))
        if form.initial_diagnosis.data:
            notes_parts.append(f"Initial diagnosis: {form.initial_diagnosis.data}")
        if form.recommended_repair.data:
            notes_parts.append(f"Recommended repair: {form.recommended_repair.data}")
        combined_notes = "\n".join(notes_parts) if notes_parts else form.intake_notes.data

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
            intake_notes=combined_notes,
            preferred_language=getattr(current_user, "preferred_language", "en") or "en",
            preferred_contact_method="phone",
        )
        db.session.add(intake)
        db.session.flush()

        db.session.add(
            IntakeDisclaimerAcceptance(
                intake_submission_id=intake.id,
                disclaimer_key="general_intake",
                disclaimer_text=current_app.config.get(
                    "DEFAULT_INTAKE_DISCLAIMER_TEXT",
                    "I confirm the provided details are accurate and accept the intake terms.",
                ),
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
                storage_path, size = save_intake_file(current_app.config.get("UPLOAD_ROOT", "uploads"), intake.reference, form.photo.data)
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
    technicians = User.query.filter(User.deleted_at.is_(None), User.is_active.is_(True)).order_by(User.full_name.asc()).all()
    technicians = [u for u in technicians if any(r.name.lower() in {"technician", "manager", "admin", "super admin"} for r in u.roles)]
    return render_template(
        "intake/detail.html",
        intake=intake,
        attachments=attachments,
        disclaimers=disclaimers,
        signatures=signatures,
        technicians=technicians,
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
    assigned_technician_id = request.form.get("assigned_technician_id")
    quoted_completion_at = request.form.get("quoted_completion_at")
    sla_target_at = request.form.get("sla_target_at")
    ticket = Ticket(
        ticket_number=generate_ticket_number(intake.branch.code, sequence),
        branch_id=intake.branch_id,
        customer_id=intake.customer_id,
        device_id=intake.device_id,
        internal_status="assigned" if assigned_technician_id else "unassigned",
        customer_status="Received",
        priority="normal",
        assigned_technician_id=uuid.UUID(str(assigned_technician_id)) if assigned_technician_id else None,
        issue_summary=intake.reported_fault,
        quoted_completion_at=datetime.fromisoformat(quoted_completion_at) if quoted_completion_at else None,
        sla_target_at=datetime.fromisoformat(sla_target_at) if sla_target_at else default_sla_target(datetime.utcnow(), current_app.config.get("DEFAULT_TICKET_SLA_DAYS", 5)),
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
