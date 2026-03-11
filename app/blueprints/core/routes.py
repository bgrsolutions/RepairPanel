from flask import Blueprint, render_template
from flask_login import login_required

from app.models import Branch, Customer, Device, Ticket, User


core_bp = Blueprint("core", __name__)


@core_bp.get("/")
@login_required
def dashboard():
    stats = {
        "tickets": Ticket.query.filter(Ticket.deleted_at.is_(None)).count(),
        "customers": Customer.query.filter(Customer.deleted_at.is_(None)).count(),
        "devices": Device.query.filter(Device.deleted_at.is_(None)).count(),
        "users": User.query.filter(User.deleted_at.is_(None)).count(),
        "branches": Branch.query.filter(Branch.deleted_at.is_(None)).count(),
    }
    return render_template("core/dashboard.html", stats=stats)
