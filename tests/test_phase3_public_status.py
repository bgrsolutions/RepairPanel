import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    IntakeSubmission,
    Quote,
    QuoteApproval,
    QuoteLine,
    QuoteOption,
    Role,
    Ticket,
    User,
)
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import seed_phase1_data


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"
    SUPPORTED_LOCALES = ["en", "es"]
    DEFAULT_BRANCH_CODE = "HQ"


def _create_tables():
    tables = [
        Branch.__table__,
        Role.__table__,
        Customer.__table__,
        User.__table__,
        role_permissions,
        user_roles,
        user_branch_access,
        Device.__table__,
        Ticket.__table__,
        IntakeSubmission.__table__,
        Diagnostic.__table__,
        Quote.__table__,
        QuoteOption.__table__,
        QuoteLine.__table__,
        QuoteApproval.__table__,
    ]
    for table in tables:
        table.create(bind=db.engine, checkfirst=True)


def _extract_csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match is not None
    return match.group(1).decode("utf-8")


def test_public_status_lookup_and_quote_approval(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        branch = Branch.query.filter_by(code="HQ").first()
        customer = Customer(
            full_name="Status User",
            phone="+34999999999",
            email="status.user@example.com",
            preferred_language="en",
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()

        device = Device(customer=customer, category="laptops", brand="Lenovo", model="X1", serial_number="SN-STAT", imei=None)
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="HQ-20260312-2000",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status="awaiting_quote_approval",
            customer_status="Quote sent",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.flush()

        quote = Quote(ticket_id=ticket.id, version=1, status="sent", currency="EUR", language="en")
        db.session.add(quote)
        db.session.flush()

        option = QuoteOption(quote_id=quote.id, name="Standard", position=1)
        db.session.add(option)
        db.session.flush()
        db.session.add(QuoteLine(option_id=option.id, line_type="fixed", description="Repair", quantity=1, unit_price=99))

        approval = QuoteApproval(quote_id=quote.id, status="pending", language="en")
        db.session.add(approval)
        db.session.commit()
        token = approval.token

    monkeypatch.setattr("app.blueprints.public_portal.routes.log_action", lambda *args, **kwargs: None)

    client = app.test_client()

    status_get = client.get("/public/status")
    assert status_get.status_code == 200
    status_csrf = _extract_csrf_token(status_get.data)

    status_post = client.post(
        "/public/status",
        data={
            "csrf_token": status_csrf,
            "ticket_number": "HQ-20260312-2000",
            "verifier": "status.user@example.com",
        },
        follow_redirects=True,
    )
    assert status_post.status_code == 200
    html = status_post.data.decode("utf-8")
    assert "Quote status" in html or "approve quote" in html.lower()

    approval_get = client.get(f"/public/quote/{token}")
    assert approval_get.status_code == 200
    approval_csrf = _extract_csrf_token(approval_get.data)

    approval_post = client.post(
        f"/public/quote/{token}",
        data={
            "csrf_token": approval_csrf,
            "decision": "approved",
            "actor_name": "Status User",
            "actor_contact": "status.user@example.com",
            "language": "en",
            "declined_reason": "",
        },
        follow_redirects=True,
    )
    assert approval_post.status_code == 200

    with app.app_context():
        quote = Quote.query.filter_by(ticket_id=Ticket.query.filter_by(ticket_number="HQ-20260312-2000").first().id).first()
        assert quote.status == "approved"
