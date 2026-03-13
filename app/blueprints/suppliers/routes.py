from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.supplier_forms import SupplierForm
from app.models import Supplier


suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


@suppliers_bp.get("/")
@login_required
def list_suppliers():
    suppliers = Supplier.query.filter(Supplier.deleted_at.is_(None)).order_by(Supplier.name.asc()).all()
    return render_template("suppliers/list.html", suppliers=suppliers)


@suppliers_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_supplier():
    form = SupplierForm()
    if form.validate_on_submit():
        supplier = Supplier(
            name=form.name.data,
            contact_name=form.contact_name.data,
            email=form.email.data,
            phone=form.phone.data,
            website=form.website.data,
            account_reference=form.account_reference.data,
            default_lead_time_days=form.default_lead_time_days.data,
            notes=form.notes.data,
            is_active=bool(form.is_active.data),
        )
        db.session.add(supplier)
        db.session.commit()
        flash(_("Supplier created"), "success")
        return redirect(url_for("suppliers.list_suppliers"))

    return render_template("suppliers/new.html", form=form)


@suppliers_bp.get('/<uuid:supplier_id>')
@login_required
def supplier_detail(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or supplier.deleted_at is not None:
        flash(_("Supplier not found"), "error")
        return redirect(url_for("suppliers.list_suppliers"))
    form = SupplierForm(obj=supplier)
    return render_template("suppliers/detail.html", supplier=supplier, form=form)


@suppliers_bp.post('/<uuid:supplier_id>/update')
@login_required
def update_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier or supplier.deleted_at is not None:
        flash(_("Supplier not found"), "error")
        return redirect(url_for("suppliers.list_suppliers"))
    form = SupplierForm()
    if form.validate_on_submit():
        supplier.name=form.name.data
        supplier.contact_name=form.contact_name.data
        supplier.email=form.email.data
        supplier.phone=form.phone.data
        supplier.website=form.website.data
        supplier.account_reference=form.account_reference.data
        supplier.default_lead_time_days=form.default_lead_time_days.data
        supplier.notes=form.notes.data
        supplier.is_active=bool(form.is_active.data)
        db.session.commit()
        flash(_("Supplier updated"), "success")
        return redirect(url_for("suppliers.supplier_detail", supplier_id=supplier.id))
    return render_template("suppliers/detail.html", supplier=supplier, form=form)
