import uuid

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import gettext as _
from flask_login import login_required

from app.extensions import db
from app.forms.user_forms import UserCreateForm, UserEditForm
from app.models import Branch, Role, User
from app.utils.permissions import roles_required


users_bp = Blueprint("users", __name__, url_prefix="/users")


def _role_choices():
    return [(str(role.id), role.name) for role in Role.query.order_by(Role.name.asc()).all()]


def _branch_choices():
    return [(str(branch.id), f"{branch.code} - {branch.name}") for branch in Branch.query.order_by(Branch.code.asc()).all()]


@users_bp.get("/")
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def list_users():
    users = User.query.filter(User.deleted_at.is_(None)).order_by(User.full_name.asc()).all()
    return render_template("users/list.html", users=users)


@users_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def create_user():
    form = UserCreateForm()
    form.role_ids.choices = _role_choices()
    form.branch_ids.choices = _branch_choices()

    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if existing and existing.deleted_at is None:
            flash(_("A user with this email already exists"), "error")
            return render_template("users/new.html", form=form)

        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            preferred_language=(form.preferred_language.data or "en").strip().lower(),
            is_active=bool(form.is_active.data),
        )
        user.set_password(form.password.data)

        roles = [db.session.get(Role, uuid.UUID(str(role_id))) for role_id in form.role_ids.data]
        branches = [db.session.get(Branch, uuid.UUID(str(branch_id))) for branch_id in form.branch_ids.data]

        user.roles = [role for role in roles if role is not None]
        user.branches = [branch for branch in branches if branch is not None]
        user.default_branch = user.branches[0] if user.branches else None

        db.session.add(user)
        db.session.commit()
        flash(_("User created"), "success")
        return redirect(url_for("users.list_users"))

    return render_template("users/new.html", form=form)


@users_bp.route("/<uuid:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("Super Admin", "Admin", "Manager")
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user or user.deleted_at is not None:
        flash(_("User not found"), "error")
        return redirect(url_for("users.list_users"))

    form = UserEditForm(obj=user)
    form.role_ids.choices = _role_choices()
    form.branch_ids.choices = _branch_choices()

    if form.validate_on_submit():
        existing = User.query.filter(User.email == form.email.data.strip().lower(), User.id != user.id).first()
        if existing and existing.deleted_at is None:
            flash(_("A user with this email already exists"), "error")
            return render_template("users/edit.html", form=form, user=user)

        user.full_name = form.full_name.data.strip()
        user.email = form.email.data.strip().lower()
        user.preferred_language = (form.preferred_language.data or "en").strip().lower()
        user.is_active = bool(form.is_active.data)
        if form.password.data:
            user.set_password(form.password.data)

        roles = [db.session.get(Role, uuid.UUID(str(role_id))) for role_id in form.role_ids.data]
        branches = [db.session.get(Branch, uuid.UUID(str(branch_id))) for branch_id in form.branch_ids.data]
        user.roles = [role for role in roles if role is not None]
        user.branches = [branch for branch in branches if branch is not None]
        if user.default_branch and user.default_branch not in user.branches:
            user.default_branch = user.branches[0] if user.branches else None

        db.session.commit()
        flash(_("User updated"), "success")
        return redirect(url_for("users.list_users"))

    if not form.is_submitted():
        form.role_ids.data = [str(role.id) for role in user.roles]
        form.branch_ids.data = [str(branch.id) for branch in user.branches]

    return render_template("users/edit.html", form=form, user=user)
