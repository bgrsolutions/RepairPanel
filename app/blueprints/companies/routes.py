import uuid as _uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.company_forms import CompanyForm
from app.models import Company

companies_bp = Blueprint("companies_admin", __name__, url_prefix="/admin/companies")


@companies_bp.get("/")
@login_required
def list_companies():
    companies = Company.query.filter(Company.deleted_at.is_(None)).order_by(Company.legal_name).all()
    return render_template("companies/list.html", companies=companies)


@companies_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_company():
    form = CompanyForm()
    if form.validate_on_submit():
        company = Company(
            legal_name=form.legal_name.data.strip(),
            trading_name=(form.trading_name.data or "").strip() or None,
            cif_nif=(form.cif_nif.data or "").strip() or None,
            tax_mode=form.tax_mode.data,
            phone=(form.phone.data or "").strip() or None,
            email=(form.email.data or "").strip() or None,
            website=(form.website.data or "").strip() or None,
            default_quote_terms=(form.default_quote_terms.data or "").strip() or None,
            default_repair_terms=(form.default_repair_terms.data or "").strip() or None,
            document_footer=(form.document_footer.data or "").strip() or None,
        )
        db.session.add(company)
        db.session.commit()
        flash(_("Company created"), "success")
        return redirect(url_for("companies_admin.list_companies"))
    return render_template("companies/form.html", form=form, editing=False)


@companies_bp.route("/<company_id>/edit", methods=["GET", "POST"])
@login_required
def edit_company(company_id):
    try:
        _cid = _uuid.UUID(str(company_id))
    except (ValueError, TypeError):
        abort(404)
    company = db.session.get(Company, _cid)
    if not company:
        abort(404)
    form = CompanyForm(obj=company)
    if form.validate_on_submit():
        form.populate_obj(company)
        db.session.commit()
        flash(_("Company updated"), "success")
        return redirect(url_for("companies_admin.list_companies"))
    return render_template("companies/form.html", form=form, company=company, editing=True)
