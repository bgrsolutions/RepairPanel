from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.models import Branch


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


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
    return render_template(
        "settings/portal.html",
        supported_locales=current_app.config.get("SUPPORTED_LOCALES", ["en"]),
        disclaimer=current_app.config.get("DEFAULT_INTAKE_DISCLAIMER_TEXT", ""),
    )
