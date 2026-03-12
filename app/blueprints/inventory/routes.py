import uuid
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.inventory_forms import PartForm, StockAdjustmentForm, StockLocationForm
from app.models import Branch, Part, StockLevel, StockLocation
from app.services.inventory_service import apply_stock_movement


inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@inventory_bp.get("/")
@login_required
def stock_overview():
    levels = StockLevel.query.order_by(StockLevel.updated_at.desc()).all()
    return render_template("inventory/overview.html", levels=levels)


@inventory_bp.get("/parts")
@login_required
def list_parts():
    parts = Part.query.filter(Part.deleted_at.is_(None)).order_by(Part.name.asc()).all()
    return render_template("inventory/parts_list.html", parts=parts)


@inventory_bp.route("/parts/new", methods=["GET", "POST"])
@login_required
def new_part():
    form = PartForm()
    if form.validate_on_submit():
        part = Part(
            sku=form.sku.data,
            barcode=form.barcode.data,
            name=form.name.data,
            category=form.category.data,
            supplier_sku=form.supplier_sku.data,
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
        location = StockLocation(
            branch_id=uuid.UUID(str(form.branch_id.data)),
            code=form.code.data,
            name=form.name.data,
            location_type=form.location_type.data,
            is_active=True,
        )
        db.session.add(location)
        db.session.commit()
        flash(_("Stock location created"), "success")
        return redirect(url_for("inventory.list_locations"))

    return render_template("inventory/location_new.html", form=form)


@inventory_bp.route("/movements/new", methods=["GET", "POST"])
@login_required
def new_movement():
    form = StockAdjustmentForm()
    form.part_id.choices = [(str(p.id), f"{p.sku} - {p.name}") for p in Part.query.order_by(Part.name).all()]
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
