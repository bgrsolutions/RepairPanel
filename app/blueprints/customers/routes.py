from sqlalchemy import or_

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.models import Customer, Ticket


customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.get("/")
@login_required
def list_customers():
    query = (request.args.get("q") or "").strip()

    customers_query = Customer.query.filter(Customer.deleted_at.is_(None))
    if query:
        like = f"%{query}%"
        customers_query = customers_query.filter(
            or_(
                Customer.full_name.ilike(like),
                Customer.phone.ilike(like),
                Customer.email.ilike(like),
            )
        )

    customers = customers_query.order_by(Customer.full_name.asc()).all()
    return render_template("customers/list.html", customers=customers, query=query)


@customers_bp.get("/<uuid:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.filter(Customer.id == customer_id, Customer.deleted_at.is_(None)).first_or_404()

    devices = [device for device in customer.devices if device.deleted_at is None]
    tickets = (
        Ticket.query.filter(Ticket.customer_id == customer.id, Ticket.deleted_at.is_(None))
        .order_by(Ticket.created_at.desc())
        .all()
    )

    return render_template(
        "customers/detail.html",
        customer=customer,
        devices=devices,
        tickets=tickets,
    )
