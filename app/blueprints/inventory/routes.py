import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required
from sqlalchemy import func, or_

from app.extensions import db
from app.forms.inventory_forms import PartForm, StockAdjustmentForm, StockLocationForm
from app.models import Branch, Part, StockLevel, StockLocation, Supplier
from app.services.inventory_service import apply_stock_movement
from app.utils.permissions import roles_required


inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@inventory_bp.get("/")
@login_required
def stock_overview():
    levels = StockLevel.query.order_by(StockLevel.updated_at.desc()).all()
    return render_template("inventory/overview.html", levels=levels)


@inventory_bp.get("/parts")
@login_required
def list_parts():
    query = (request.args.get("q") or "").strip()
    include_inactive = request.args.get("include_inactive") == "1"

    parts_query = Part.query.filter(Part.deleted_at.is_(None))
    if not include_inactive:
        parts_query = parts_query.filter(Part.is_active.is_(True))
    if query:
        like = f"%{query}%"
        parts_query = parts_query.filter(or_(Part.name.ilike(like), Part.sku.ilike(like), Part.barcode.ilike(like), Part.supplier_sku.ilike(like)))

    parts = parts_query.order_by(Part.name.asc()).all()
    totals = {
        str(pid): (float(on_hand or 0), float(reserved or 0))
        for pid, on_hand, reserved in db.session.query(
            StockLevel.part_id, func.sum(StockLevel.on_hand_qty), func.sum(StockLevel.reserved_qty)
        ).group_by(StockLevel.part_id)
    }

    return render_template("inventory/parts_list.html", parts=parts, query=query, include_inactive=include_inactive, totals=totals)


@inventory_bp.get('/parts/search')
@login_required
def search_parts():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return {"items": []}
    like = f"%{q}%"
    rows = Part.query.filter(
        Part.deleted_at.is_(None),
        Part.is_active.is_(True),
        or_(Part.name.ilike(like), Part.sku.ilike(like), Part.barcode.ilike(like), Part.supplier_sku.ilike(like)),
    ).order_by(Part.name.asc()).limit(25).all()
    return {"items": [{"id": str(p.id), "label": f"{p.sku} - {p.name}"} for p in rows]}


@inventory_bp.post("/parts/<uuid:part_id>/toggle-active")
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def toggle_part_active(part_id):
    part = db.session.get(Part, part_id)
    if not part or part.deleted_at is not None:
        flash(_("Part not found"), "error")
        return redirect(url_for("inventory.list_parts"))

    part.is_active = not part.is_active
    db.session.commit()
    flash(_("Part status updated"), "success")
    return redirect(url_for("inventory.list_parts", include_inactive=1))


@inventory_bp.route("/parts/new", methods=["GET", "POST"])
@login_required
def new_part():
    form = PartForm()
    form.default_supplier_id.choices = [("", "-- None --")] + [(str(s.id), s.name) for s in Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()]
    if form.validate_on_submit():
        part = Part(
            sku=form.sku.data,
            barcode=form.barcode.data,
            name=form.name.data,
            category=form.category.data,
            supplier_sku=form.supplier_sku.data,
            default_supplier_id=uuid.UUID(form.default_supplier_id.data) if form.default_supplier_id.data else None,
            lead_time_days=form.lead_time_days.data,
            cost_price=form.cost_price.data,
            sale_price=form.sale_price.data,
            serial_tracking=bool(form.serial_tracking.data),
            notes=form.notes.data,
            is_active=bool(form.is_active.data),
        )
        db.session.add(part)
        db.session.commit()
        flash(_("Part created"), "success")
        return redirect(url_for("inventory.list_parts"))

    return render_template("inventory/part_new.html", form=form)


@inventory_bp.get("/locations")
@login_required
def list_locations():
    locations = StockLocation.query.filter(StockLocation.deleted_at.is_(None)).order_by(StockLocation.name.asc()).all()
    return render_template("inventory/locations_list.html", locations=locations)


@inventory_bp.route("/locations/new", methods=["GET", "POST"])
@login_required
def new_location():
    form = StockLocationForm()
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]
    if form.validate_on_submit():
        location = StockLocation(branch_id=uuid.UUID(str(form.branch_id.data)), code=form.code.data, name=form.name.data, location_type=form.location_type.data, is_active=True)
        db.session.add(location)
        db.session.commit()
        flash(_("Stock location created"), "success")
        return redirect(url_for("inventory.list_locations"))

    return render_template("inventory/location_new.html", form=form)


@inventory_bp.route("/movements/new", methods=["GET", "POST"])
@login_required
def new_movement():
    form = StockAdjustmentForm()
    form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.filter(Part.is_active.is_(True)).order_by(Part.name).all()]
    form.branch_id.choices = [(str(b.id), f"{b.code} - {b.name}") for b in Branch.query.order_by(Branch.code).all()]
    form.location_id.choices = [(str(l.id), f"{l.code} - {l.name}") for l in StockLocation.query.order_by(StockLocation.name).all()]

    if form.validate_on_submit():
        apply_stock_movement(
            part_id=form.part_id.data,
            branch_id=uuid.UUID(str(form.branch_id.data)),
            location_id=form.location_id.data,
            movement_type=form.movement_type.data,
            quantity=form.quantity.data,
            notes=form.notes.data,
        )
        db.session.commit()
        flash(_("Stock movement recorded"), "success")
        return redirect(url_for("inventory.stock_overview"))

    return render_template("inventory/movement_new.html", form=form)
