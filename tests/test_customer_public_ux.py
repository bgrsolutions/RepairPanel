import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    IntakeSubmission,
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
    ]
    for table in tables:
        table.create(bind=db.engine, checkfirst=True)


def _extract_csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match is not None, "csrf token not found"
    return match.group(1).decode("utf-8")


def _login(client):
    login_page = client.get("/auth/login")
    token = _extract_csrf_token(login_page.data)
    response = client.post(
        "/auth/login",
        data={"email": "admin@ironcore.com", "password": "admin1234", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_public_pages_use_isolated_layout_without_internal_nav(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)
    response = client.get("/public/check-in")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Public Check-In" in html
    assert "Tickets" not in html
    assert "My Queue" not in html
    assert "Logout" not in html


def test_customer_list_search_and_profile_links(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        branch = Branch.query.filter_by(code="HQ").first()
        customer = Customer(
            full_name="Customer Alpha",
            phone="+34000000001",
            email="alpha@example.com",
            preferred_language="en",
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()

        device = Device(
            customer=customer,
            category="phones",
            brand="Apple",
            model="iPhone 14",
            serial_number="SN-ALPHA",
            imei="111122223333444",
        )
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="HQ-20260312-0001",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status="New",
            customer_status="Received",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.commit()

    client = app.test_client()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)
    _login(client)

    list_response = client.get("/customers/?q=alpha@example.com")
    assert list_response.status_code == 200
    list_html = list_response.data.decode("utf-8")
    assert "Customer Alpha" in list_html

    with app.app_context():
        customer = Customer.query.filter_by(email="alpha@example.com").first()
        assert customer is not None

    detail_response = client.get(f"/customers/{customer.id}")
    assert detail_response.status_code == 200
    detail_html = detail_response.data.decode("utf-8")
    assert "Linked Devices" in detail_html
    assert "Repair History" in detail_html
    assert "HQ-20260312-0001" in detail_html
