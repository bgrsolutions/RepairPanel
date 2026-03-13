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
    TicketNote,
    User,
    Part,
    PartOrder,
    PartOrderEvent,
    PartOrderLine,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    Supplier,
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
        TicketNote.__table__,
        Supplier.__table__,
        Part.__table__,
        StockLocation.__table__,
        StockLevel.__table__,
        StockMovement.__table__,
        StockReservation.__table__,
        PartOrder.__table__,
        PartOrderLine.__table__,
        PartOrderEvent.__table__,
    ]
    for table in tables:
        table.create(bind=db.engine, checkfirst=True)


def _extract_csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match is not None
    return match.group(1).decode("utf-8")


def _login(client):
    page = client.get("/auth/login")
    token = _extract_csrf_token(page.data)
    resp = client.post(
        "/auth/login",
        data={"email": "admin@ironcore.com", "password": "admin1234", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def _seed_ticket(app):
    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        customer = Customer(
            full_name="Quote Customer",
            phone="+34123123123",
            email="quote.customer@example.com",
            preferred_language="en",
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()

        device = Device(
            customer=customer,
            category="phones",
            brand="Google",
            model="Pixel 8",
            serial_number="PX8-SN",
            imei="123451234512345",
        )
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="HQ-20260312-1000",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status="awaiting_diagnostics",
            customer_status="Received",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket.id


def test_phase3_diagnostics_and_quote_workflow(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.blueprints.diagnostics.routes.log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *args, **kwargs: None)

    ticket_id = _seed_ticket(app)

    client = app.test_client()
    _login(client)

    detail_page = client.get(f"/tickets/{ticket_id}")
    token = _extract_csrf_token(detail_page.data)

    diag_resp = client.post(
        f"/diagnostics/ticket/{ticket_id}/save",
        data={
            "csrf_token": token,
            "customer_reported_fault": "Battery drains quickly",
            "technician_diagnosis": "Battery health degraded",
            "recommended_repair": "Replace battery module",
            "estimated_labour": "49.99",
            "repair_notes": "Needs adhesive replacement",
        },
        follow_redirects=False,
    )
    assert diag_resp.status_code == 302

    quote_new_page = client.get(f"/quotes/ticket/{ticket_id}/new")
    quote_token = _extract_csrf_token(quote_new_page.data)

    quote_create_resp = client.post(
        f"/quotes/ticket/{ticket_id}/create",
        data={
            "csrf_token": quote_token,
            "currency": "EUR",
            "language": "en",
            "expires_at": "2026-12-31",
            "notes_snapshot": "Phase 3 quote note",
            "terms_snapshot": "Standard terms",
            "options-0-name": "OEM Repair",
            "options-0-lines-0-line_type": "labour",
            "options-0-lines-0-description": "Battery replacement labour",
            "options-0-lines-0-quantity": "1",
            "options-0-lines-0-unit_price": "49.99",
        },
        follow_redirects=False,
    )
    assert quote_create_resp.status_code == 302

    with app.app_context():
        diagnostics = Diagnostic.query.all()
        assert len(diagnostics) == 1
        assert diagnostics[0].technician_diagnosis == "Battery health degraded"

        quote = Quote.query.filter_by(ticket_id=ticket_id).first()
        assert quote is not None
        assert quote.status == "draft"
        assert len(quote.options) == 1
        assert len(quote.options[0].lines) == 1

        send_resp = client.post(f"/quotes/{quote.id}/send", follow_redirects=False)
        assert send_resp.status_code == 302

        db.session.refresh(quote)
        assert quote.status == "sent"
        assert quote.ticket.internal_status == "awaiting_quote_approval"

        approval = QuoteApproval.query.filter_by(quote_id=quote.id).first()
        assert approval is not None
        assert approval.token
