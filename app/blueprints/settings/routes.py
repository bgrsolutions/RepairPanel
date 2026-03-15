from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required
from sqlalchemy import inspect

from app.extensions import db
from app.models import AppSetting, Branch


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _get_setting(key: str, default: str = "") -> str:
    if not inspect(db.engine).has_table("app_settings"):
        return default
    row = AppSetting.query.filter_by(key=key, branch_id=None).order_by(AppSetting.created_at.desc()).first()
    return row.value if row and row.value is not None else default


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
