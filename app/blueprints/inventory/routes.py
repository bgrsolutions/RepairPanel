import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required
from sqlalchemy import func, inspect, or_

from app.extensions import db
from app.forms.inventory_forms import PartCategoryForm, PartForm, StockAdjustmentForm, StockLocationForm
from app.models import Branch, Part, PartCategory, PartSupplier, StockLayer, StockLevel, StockLocation, Supplier
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
    category_id = (request.args.get("category_id") or "").strip()
    supplier_id = (request.args.get("supplier_id") or "").strip()
    stock_state = (request.args.get("stock_state") or "").strip()

    inspector = inspect(db.engine)
    has_categories = inspector.has_table("part_categories") and inspector.has_table("part_category_links")
    has_part_suppliers = inspector.has_table("part_suppliers")

    parts_query = Part.query.filter(Part.deleted_at.is_(None))
    if not include_inactive:
        parts_query = parts_query.filter(Part.is_active.is_(True))
    if query:
        like = f"%{query}%"
        parts_query = parts_query.filter(or_(Part.name.ilike(like), Part.sku.ilike(like), Part.barcode.ilike(like), Part.supplier_sku.ilike(like)))
    if category_id and has_categories:
        parts_query = parts_query.join(Part.categories).filter(PartCategory.id == uuid.UUID(category_id))
    if supplier_id:
        sid = uuid.UUID(supplier_id)
        if has_part_suppliers:
            parts_query = parts_query.outerjoin(PartSupplier, PartSupplier.part_id == Part.id).filter(
                or_(Part.default_supplier_id == sid, PartSupplier.supplier_id == sid)
            )
        else:
            parts_query = parts_query.filter(Part.default_supplier_id == sid)

    parts = parts_query.order_by(Part.name.asc()).all()
    totals = {
        str(pid): (float(on_hand or 0), float(reserved or 0))
        for pid, on_hand, reserved in db.session.query(
            StockLevel.part_id, func.sum(StockLevel.on_hand_qty), func.sum(StockLevel.reserved_qty)
        ).group_by(StockLevel.part_id)
    }

    if stock_state:
        def state_for(part):
            on_hand, reserved = totals.get(str(part.id), (0.0, 0.0))
            available = on_hand - reserved
            threshold = part.low_stock_threshold or 3
            if available <= 0:
                return "out"
            if available < threshold:
                return "low"
            return "in"
        parts = [p for p in parts if state_for(p) == stock_state]

    has_categories = inspect(db.engine).has_table("part_categories") and inspect(db.engine).has_table("part_category_links")
    has_part_suppliers = inspect(db.engine).has_table("part_suppliers")
    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else [] if has_categories else []
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name.asc()).all()
    return render_template(
        "inventory/parts_list.html",
        parts=parts,
        query=query,
        include_inactive=include_inactive,
        totals=totals,
        categories=categories,
        suppliers=suppliers,
        category_id=category_id,
        supplier_id=supplier_id,
        stock_state=stock_state,
    )


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
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    has_categories = inspect(db.engine).has_table("part_categories") and inspect(db.engine).has_table("part_category_links")
    has_part_suppliers = inspect(db.engine).has_table("part_suppliers")
    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else []
    form.default_supplier_id.choices = [("", "-- None --")] + [(str(s.id), s.name) for s in suppliers]
    form.supplier_ids.choices = [(str(s.id), s.name) for s in suppliers]
    form.category_ids.choices = [(str(c.id), c.name) for c in categories]

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
            description=form.description.data,
            image_url=form.image_url.data,
            low_stock_threshold=form.low_stock_threshold.data,
            notes=form.notes.data,
            is_active=bool(form.is_active.data),
        )
        db.session.add(part)
        db.session.flush()

        if has_categories:
            for category_id in (form.category_ids.data or []):
                category = db.session.get(PartCategory, uuid.UUID(str(category_id)))
                if category:
                    part.categories.append(category)

        if has_part_suppliers:
            for supplier_id in (form.supplier_ids.data or []):
                sid = uuid.UUID(str(supplier_id))
                if form.default_supplier_id.data and sid == uuid.UUID(form.default_supplier_id.data):
                    continue
                db.session.add(PartSupplier(part_id=part.id, supplier_id=sid, is_default=False))

        db.session.commit()
        flash(_("Part created"), "success")
        return redirect(url_for("inventory.part_detail", part_id=part.id))

    return render_template("inventory/part_new.html", form=form)


@inventory_bp.get("/parts/<uuid:part_id>")
@login_required
def part_detail(part_id):
    part = db.session.get(Part, part_id)
    if not part or part.deleted_at is not None:
        flash(_("Part not found"), "error")
        return redirect(url_for("inventory.list_parts"))

    stock_levels = StockLevel.query.filter_by(part_id=part.id).order_by(StockLevel.updated_at.desc()).all()
    linked_orders = []
    if inspect(db.engine).has_table("stock_layers"):
        linked_orders = (
            db.session.query(StockLayer)
            .filter(StockLayer.part_id == part.id)
            .order_by(StockLayer.created_at.desc())
            .limit(20)
            .all()
        )
    return render_template("inventory/part_detail.html", part=part, stock_levels=stock_levels, stock_layers=linked_orders)


@inventory_bp.get("/categories")
@login_required
def list_categories():
    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else []
    return render_template("inventory/categories_list.html", categories=categories)


@inventory_bp.route("/categories/new", methods=["GET", "POST"])
@login_required
def new_category():
    if not inspect(db.engine).has_table("part_categories"):
        flash(_("Categories unavailable until migrations are applied"), "warning")
        return redirect(url_for("inventory.list_parts"))
    form = PartCategoryForm()
    if form.validate_on_submit():
        category = PartCategory(name=form.name.data.strip(), code=(form.code.data or '').strip() or None, description=form.description.data)
        db.session.add(category)
        db.session.commit()
        flash(_("Category saved"), "success")
        return redirect(url_for("inventory.list_categories"))
    return render_template("inventory/category_new.html", form=form)


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
