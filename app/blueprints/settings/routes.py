import uuid as _uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required
from sqlalchemy import inspect

from app.extensions import db
from app.forms.branch_forms import BranchEditForm
from app.models import AppSetting, Branch, Company


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _get_setting(key: str, default: str = "") -> str:
    if not inspect(db.engine).has_table("app_settings"):
        return default
    row = AppSetting.query.filter_by(key=key, branch_id=None).order_by(AppSetting.created_at.desc()).first()
    return row.value if row and row.value is not None else default


def _company_choices():
    try:
        if not inspect(db.engine).has_table("companies"):
            return [("", "-- None --")]
    except Exception:
        return [("", "-- None --")]
    companies = Company.query.filter(Company.deleted_at.is_(None)).order_by(Company.legal_name).all()
    choices = [("", "-- None --")]
    choices.extend((str(c.id), c.display_name) for c in companies)
    return choices


@settings_bp.get("/")
@login_required
def index():
    branches = Branch.query.filter(Branch.deleted_at.is_(None)).order_by(Branch.code).all()
    return render_template("settings/index.html", branches=branches)


@settings_bp.post("/branches")
@login_required
def create_branch():
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    if not code or not name:
        flash(_("Branch code and name are required"), "error")
        return redirect(url_for("settings.index"))

    branch = Branch(code=code, name=name, is_active=True)
    db.session.add(branch)
    db.session.commit()
    flash(_("Branch created"), "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/branches/<branch_id>/edit", methods=["GET", "POST"])
@login_required
def edit_branch(branch_id):
    import uuid as _uuid
    try:
        _bid = _uuid.UUID(str(branch_id))
    except (ValueError, TypeError):
        from flask import abort
        abort(404)
    branch = db.session.get(Branch, _bid)
    if not branch:
        from flask import abort
        abort(404)
    form = BranchEditForm(obj=branch)
    form.company_id.choices = _company_choices()
    if request.method == "GET":
        form.company_id.data = str(branch.company_id) if branch.company_id else ""
    if form.validate_on_submit():
        branch.code = form.code.data.strip().upper()
        branch.name = form.name.data.strip()
        branch.company_id = _uuid.UUID(form.company_id.data) if form.company_id.data else None
        branch.address_line_1 = (form.address_line_1.data or "").strip() or None
        branch.address_line_2 = (form.address_line_2.data or "").strip() or None
        branch.postcode = (form.postcode.data or "").strip() or None
        branch.city = (form.city.data or "").strip() or None
        branch.island_or_region = (form.island_or_region.data or "").strip() or None
        branch.country = (form.country.data or "").strip() or None
        branch.phone = (form.phone.data or "").strip() or None
        branch.email = (form.email.data or "").strip() or None
        branch.opening_hours = (form.opening_hours.data or "").strip() or None
        branch.ticket_prefix = (form.ticket_prefix.data or "").strip() or None
        branch.quote_prefix = (form.quote_prefix.data or "").strip() or None
        db.session.commit()
        flash(_("Branch updated"), "success")
        return redirect(url_for("settings.index"))
    return render_template("settings/branch_edit.html", form=form, branch=branch)


@settings_bp.get("/portal")
@login_required
def portal_settings():
    default_disclaimer = current_app.config.get("DEFAULT_INTAKE_DISCLAIMER_TEXT", "")
    return render_template(
        "settings/portal.html",
        supported_locales=_get_setting("portal_supported_locales", ",".join(current_app.config.get("SUPPORTED_LOCALES", ["en"]))),
        disclaimer=_get_setting("portal_default_disclaimer", default_disclaimer),
        footer_help_text=_get_setting("portal_footer_help_text", ""),
        branding_name=_get_setting("portal_branding_name", "IRONCore"),
    )


@settings_bp.post("/portal")
@login_required
def save_portal_settings():
    if not inspect(db.engine).has_table("app_settings"):
        flash(_("Portal settings persistence unavailable until migrations are applied"), "warning")
        return redirect(url_for("settings.portal_settings"))

    entries = {
        "portal_supported_locales": (request.form.get("supported_locales") or "").strip(),
        "portal_default_disclaimer": (request.form.get("disclaimer") or "").strip(),
        "portal_footer_help_text": (request.form.get("footer_help_text") or "").strip(),
        "portal_branding_name": (request.form.get("branding_name") or "").strip(),
    }
    for key, value in entries.items():
        row = AppSetting.query.filter_by(key=key, branch_id=None).first()
        if not row:
            row = AppSetting(key=key, branch_id=None)
            db.session.add(row)
        row.value = value
    db.session.commit()
    flash(_("Portal settings saved"), "success")
    return redirect(url_for("settings.portal_settings"))


@settings_bp.get("/quotes")
@login_required
def quote_settings():
    return render_template(
        "settings/quotes.html",
        quote_terms=_get_setting("quote_default_terms", ""),
    )


@settings_bp.post("/quotes")
@login_required
def save_quote_settings():
    if not inspect(db.engine).has_table("app_settings"):
        flash(_("Settings persistence unavailable until migrations are applied"), "warning")
        return redirect(url_for("settings.quote_settings"))
    key = "quote_default_terms"
    value = (request.form.get("quote_terms") or "").strip()
    row = AppSetting.query.filter_by(key=key, branch_id=None).first()
    if not row:
        row = AppSetting(key=key, branch_id=None)
        db.session.add(row)
    row.value = value
    db.session.commit()
    flash(_("Quote settings saved"), "success")
    return redirect(url_for("settings.quote_settings"))
