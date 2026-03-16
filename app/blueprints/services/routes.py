import uuid as _uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.service_forms import RepairServiceForm
from app.models import Part, RepairService

services_bp = Blueprint("services", __name__, url_prefix="/services")


def _part_choices():
    parts = Part.query.filter(Part.deleted_at.is_(None), Part.is_active.is_(True)).order_by(Part.name).all()
    choices = [("", "-- None --")]
    choices.extend((str(p.id), f"{p.name} ({p.sku})" if p.sku else p.name) for p in parts)
    return choices


@services_bp.get("/")
@login_required
def list_services():
    show_inactive = request.args.get("show_inactive") == "1"
    q = RepairService.query
    if not show_inactive:
        q = q.filter(RepairService.is_active.is_(True))
    services = q.order_by(RepairService.device_category, RepairService.name).all()
    return render_template("services/list.html", services=services, show_inactive=show_inactive)


@services_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_service():
    form = RepairServiceForm()
    form.default_part_id.choices = _part_choices()
    if form.validate_on_submit():
        svc = RepairService(
            name=form.name.data.strip(),
            device_category=form.device_category.data or None,
            description=(form.description.data or "").strip() or None,
            default_part_id=_uuid.UUID(form.default_part_id.data) if form.default_part_id.data else None,
            labour_minutes=form.labour_minutes.data,
            suggested_sale_price=form.suggested_sale_price.data,
            is_active=form.is_active.data,
        )
        db.session.add(svc)
        db.session.commit()
        flash(_("Service created"), "success")
        return redirect(url_for("services.list_services"))
    return render_template("services/form.html", form=form, editing=False)


@services_bp.route("/<service_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service(service_id):
    try:
        _sid = _uuid.UUID(str(service_id))
    except (ValueError, TypeError):
        abort(404)
    svc = db.session.get(RepairService, _sid)
    if not svc:
        abort(404)
    form = RepairServiceForm(obj=svc)
    form.default_part_id.choices = _part_choices()
    if request.method == "GET":
        form.default_part_id.data = str(svc.default_part_id) if svc.default_part_id else ""
    if form.validate_on_submit():
        svc.name = form.name.data.strip()
        svc.device_category = form.device_category.data or None
        svc.description = (form.description.data or "").strip() or None
        svc.default_part_id = _uuid.UUID(form.default_part_id.data) if form.default_part_id.data else None
        svc.labour_minutes = form.labour_minutes.data
        svc.suggested_sale_price = form.suggested_sale_price.data
        svc.is_active = form.is_active.data
        db.session.commit()
        flash(_("Service updated"), "success")
        return redirect(url_for("services.list_services"))
    return render_template("services/form.html", form=form, service=svc, editing=True)
