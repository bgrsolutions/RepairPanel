from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.forms.auth_forms import LoginForm
from app.services.auth_service import authenticate, sign_out


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate(form.email.data, form.password.data)
        if user:
            flash(_("Welcome back"), "success")
            return redirect(url_for("core.dashboard"))
        flash(_("Invalid credentials"), "error")
    return render_template("auth/login.html", form=form)


@auth_bp.get("/logout")
@login_required
def logout():
    sign_out()
    flash(_("Signed out"), "info")
    return redirect(url_for("auth.login"))
