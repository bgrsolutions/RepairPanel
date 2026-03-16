import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required
from sqlalchemy import func, inspect, or_

from app.extensions import db
from app.forms.inventory_forms import PartCategoryForm, PartForm, StockAdjustmentForm, StockLocationForm
from app.models import Branch, Part, PartCategory, PartOrderLine, PartSupplier, QuoteLine, RepairService, StockLayer, StockLevel, StockLocation, StockMovement, StockReservation, Supplier
from app.services.inventory_service import apply_stock_movement
from app.services.permission_service import can_manage_inventory
from app.utils.permissions import permission_required, roles_required

from datetime import datetime, timezone


inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@inventory_bp.get("/")
@login_required
def stock_overview():
    levels = StockLevel.query.order_by(StockLevel.updated_at.desc()).all()

    # Group stock levels by part for the aggregated view
    from collections import defaultdict
    parts_map = {}      # part_id -> Part object
    part_levels = defaultdict(list)  # part_id -> [StockLevel, ...]
    part_totals = {}    # part_id -> (on_hand, reserved, available)

    for level in levels:
        pid = str(level.part_id)
        parts_map[pid] = level.part
        part_levels[pid].append(level)

    for pid, lvls in part_levels.items():
        on_hand = sum(float(l.on_hand_qty or 0) for l in lvls)
        reserved = sum(float(l.reserved_qty or 0) for l in lvls)
        part_totals[pid] = (on_hand, reserved, on_hand - reserved)

    # Sort by part name
    sorted_part_ids = sorted(parts_map.keys(), key=lambda pid: parts_map[pid].name.lower())

    return render_template(
        "inventory/overview.html",
        levels=levels,
        parts_map=parts_map,
        part_levels=part_levels,
        part_totals=part_totals,
        sorted_part_ids=sorted_part_ids,
    )


@inventory_bp.get("/parts")
@login_required
def list_parts():
    query = (request.args.get("q") or "").strip()
    include_inactive = request.args.get("include_inactive") == "1"
    category_id = (request.args.get("category_id") or "").strip()
    supplier_id = (request.args.get("supplier_id") or "").strip()
    stock_state = (request.args.get("stock_state") or "").strip()
    lead_time_filter = (request.args.get("lead_time") or "").strip()

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
    if lead_time_filter == "has":
        parts_query = parts_query.filter(Part.lead_time_days.is_not(None))
    elif lead_time_filter == "long":
        parts_query = parts_query.filter(Part.lead_time_days.is_not(None), Part.lead_time_days >= 7)

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

    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else []
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
        lead_time_filter=lead_time_filter,
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
    return {"items": [{"id": str(p.id), "label": f"{p.sku} - {p.name}", "name": p.name, "sku": p.sku or "", "sale_price": float(p.sale_price or 0), "cost_price": float(p.cost_price or 0)} for p in rows]}


@inventory_bp.post("/parts/create-json")
@login_required
@permission_required(can_manage_inventory)
def create_part_json():
    data = request.get_json(silent=True) or {}
    sku = (data.get("sku") or "").strip()
    name = (data.get("name") or "").strip()
    cost_price = data.get("cost_price")
    sale_price = data.get("sale_price")
    if not sku or not name:
        return jsonify({"ok": False, "error": "SKU and name are required"}), 400
    existing = Part.query.filter_by(sku=sku).first()
    if existing:
        return jsonify({"ok": False, "error": "A part with this SKU already exists"}), 400
    part = Part(sku=sku, name=name, is_active=True, cost_price=cost_price, sale_price=sale_price)
    db.session.add(part)
    db.session.commit()
    return jsonify({"ok": True, "id": str(part.id), "label": f"{part.sku} - {part.name}", "name": part.name, "sku": part.sku, "sale_price": float(part.sale_price or 0), "cost_price": float(part.cost_price or 0)})


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


@inventory_bp.post("/parts/<uuid:part_id>/delete")
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def delete_part(part_id):
    """Soft-delete a part. Refuses if the part has historical usage that would be corrupted."""
    part = db.session.get(Part, part_id)
    if not part or part.deleted_at is not None:
        flash(_("Part not found"), "error")
        return redirect(url_for("inventory.list_parts"))

    # Safety checks — refuse if part is referenced in historical records
    reasons = []
    if StockMovement.query.filter_by(part_id=part.id).first():
        reasons.append("stock movements")
    if StockReservation.query.filter_by(part_id=part.id).first():
        reasons.append("stock reservations")
    if PartOrderLine.query.filter_by(part_id=part.id).first():
        reasons.append("part orders")
    try:
        has_quote_lines = db.session.query(QuoteLine).filter(
            QuoteLine.part_id.isnot(None)
        ).filter(QuoteLine.part_id == part.id).first()
    except Exception:
        has_quote_lines = None
    if has_quote_lines:
        reasons.append("quote lines")
    if RepairService.query.filter_by(default_part_id=part.id).first():
        reasons.append("repair services")

    if reasons:
        flash(_("Cannot delete part '%(name)s': it is referenced by %(refs)s. "
                "Deactivate it instead to hide it from active use.",
                name=part.name, refs=", ".join(reasons)), "warning")
        return redirect(url_for("inventory.part_detail", part_id=part.id))

    part.deleted_at = datetime.now(timezone.utc)
    part.is_active = False
    db.session.commit()
    flash(_("Part '%(name)s' deleted", name=part.name), "success")
    return redirect(url_for("inventory.list_parts"))


@inventory_bp.route("/parts/new", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_inventory)
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


@inventory_bp.route("/parts/<uuid:part_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_inventory)
def edit_part(part_id):
    part = db.session.get(Part, part_id)
    if not part or part.deleted_at is not None:
        flash(_("Part not found"), "error")
        return redirect(url_for("inventory.list_parts"))

    form = PartForm(obj=part)
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    has_categories = inspect(db.engine).has_table("part_categories") and inspect(db.engine).has_table("part_category_links")
    has_part_suppliers = inspect(db.engine).has_table("part_suppliers")
    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else []
    form.default_supplier_id.choices = [("", "-- None --")] + [(str(su.id), su.name) for su in suppliers]
    form.supplier_ids.choices = [(str(su.id), su.name) for su in suppliers]
    form.category_ids.choices = [(str(c.id), c.name) for c in categories]

    if request.method == "GET":
        form.default_supplier_id.data = str(part.default_supplier_id) if part.default_supplier_id else ""
        form.supplier_ids.data = [str(link.supplier_id) for link in part.supplier_links]
        form.category_ids.data = [str(cat.id) for cat in part.categories]

    if form.validate_on_submit():
        part.sku=form.sku.data
        part.barcode=form.barcode.data
        part.name=form.name.data
        part.category=form.category.data
        part.supplier_sku=form.supplier_sku.data
        part.default_supplier_id=uuid.UUID(form.default_supplier_id.data) if form.default_supplier_id.data else None
        part.lead_time_days=form.lead_time_days.data
        part.cost_price=form.cost_price.data
        part.sale_price=form.sale_price.data
        part.serial_tracking=bool(form.serial_tracking.data)
        part.description=form.description.data
        part.image_url=form.image_url.data
        part.low_stock_threshold=form.low_stock_threshold.data
        part.notes=form.notes.data
        part.is_active=bool(form.is_active.data)

        if has_categories:
            part.categories.clear()
            for category_id in (form.category_ids.data or []):
                category = db.session.get(PartCategory, uuid.UUID(str(category_id)))
                if category:
                    part.categories.append(category)

        if has_part_suppliers:
            PartSupplier.query.filter_by(part_id=part.id).delete()
            for supplier_id in (form.supplier_ids.data or []):
                sid=uuid.UUID(str(supplier_id))
                if form.default_supplier_id.data and sid == uuid.UUID(form.default_supplier_id.data):
                    continue
                db.session.add(PartSupplier(part_id=part.id, supplier_id=sid, is_default=False))

        db.session.commit()
        flash(_("Part updated"), "success")
        return redirect(url_for("inventory.part_detail", part_id=part.id))

    return render_template("inventory/part_edit.html", form=form, part=part)


@inventory_bp.get("/parts/<uuid:part_id>")
@login_required
def part_detail(part_id):
    part = db.session.get(Part, part_id)
    if not part or part.deleted_at is not None:
        flash(_("Part not found"), "error")
        return redirect(url_for("inventory.list_parts"))

    stock_levels = StockLevel.query.filter_by(part_id=part.id).order_by(StockLevel.updated_at.desc()).all()
    recent_order_lines = (
        db.session.query(PartOrderLine)
        .filter(PartOrderLine.part_id == part.id)
        .order_by(PartOrderLine.created_at.desc())
        .limit(10)
        .all()
    )
    linked_orders = []
    if inspect(db.engine).has_table("stock_layers"):
        linked_orders = (
            db.session.query(StockLayer)
            .filter(StockLayer.part_id == part.id)
            .order_by(StockLayer.created_at.desc())
            .limit(20)
            .all()
        )
    return render_template("inventory/part_detail.html", part=part, stock_levels=stock_levels, stock_layers=linked_orders, recent_order_lines=recent_order_lines)


@inventory_bp.get("/categories")
@login_required
def list_categories():
    has_categories = inspect(db.engine).has_table("part_categories")
    if not has_categories:
        flash(_("Categories unavailable until migrations are applied"), "warning")
        return redirect(url_for("inventory.list_parts"))
    categories = PartCategory.query.filter(PartCategory.deleted_at.is_(None)).order_by(PartCategory.name.asc()).all() if has_categories else []
    return render_template("inventory/categories_list.html", categories=categories)


@inventory_bp.route("/categories/new", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_inventory)
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


@inventory_bp.post("/categories/<uuid:category_id>/delete")
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def delete_category(category_id):
    category = db.session.get(PartCategory, category_id)
    if not category or category.deleted_at is not None:
        flash(_("Category not found"), "error")
        return redirect(url_for("inventory.list_categories"))

    category.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(_("Category deleted"), "success")
    return redirect(url_for("inventory.list_categories"))


@inventory_bp.get("/locations")
@login_required
def list_locations():
    locations = StockLocation.query.filter(StockLocation.deleted_at.is_(None)).order_by(StockLocation.name.asc()).all()
    return render_template("inventory/locations_list.html", locations=locations)


@inventory_bp.route("/locations/new", methods=["GET", "POST"])
@login_required
@permission_required(can_manage_inventory)
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
@permission_required(can_manage_inventory)
def new_movement():
    form = StockAdjustmentForm()
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
