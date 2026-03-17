"""Phase 17.2 tests: Intake entry flow, fast check-in flow, navigation
stabilisation, config resilience, and end-to-end ticket creation paths."""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from app import create_app
from app.extensions import db
from app.models import (
    Branch, Booking, ChecklistItem, Company, Customer, Device, Diagnostic,
    Part, PartCategory, PartOrder, PartOrderLine, PartOrderEvent,
    Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    RepairService, Role, StockLayer, StockLevel, StockLocation,
    StockMovement, StockReservation, Supplier, Ticket, TicketNote, User,
    AppSetting, IntakeSubmission, IntakeDisclaimerAcceptance, PortalToken,
)
from app.models.intake import IntakeSignature, Attachment
from app.models.role import role_permissions
from app.models.user import user_roles, user_branch_access
from app.models.inventory import part_category_links


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    SUPPORTED_LOCALES = ["en", "es"]
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "I confirm the provided details are accurate and accept the intake terms."
    UPLOAD_ROOT = "/tmp/test_uploads"


class TestConfigNoDisclaimer:
    """Config without DEFAULT_INTAKE_DISCLAIMER_TEXT to test fallback."""
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    SUPPORTED_LOCALES = ["en", "es"]
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"


def _noop_log(*a, **kw):
    return None


def _create_tables():
    """Create tables explicitly, skipping AuditLog (uses JSONB)."""
    tables = [
        Company.__table__, Branch.__table__, Role.__table__, Customer.__table__,
        User.__table__, role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__,
        IntakeDisclaimerAcceptance.__table__, IntakeSignature.__table__,
        Attachment.__table__, PortalToken.__table__,
        Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        AppSetting.__table__, RepairChecklist.__table__, ChecklistItem.__table__,
        RepairService.__table__, Booking.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _setup(monkeypatch, role_name="Admin", config_class=TestConfig):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(config_class)
    with app.app_context():
        _create_tables()

        role = Role(name=role_name)
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com", is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        customer = Customer(full_name="John Doe", phone="555-0001", email="john@example.com", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14", serial_number="SN001")
        db.session.add(device)
        service = RepairService(name="Screen Repair", is_active=True, labour_minutes=45)
        db.session.add(service)
        db.session.flush()

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "service_id": service.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


# ===========================================================================
# A. Intake form GET (Create New Ticket path)
# ===========================================================================

def test_intake_form_get_returns_200(monkeypatch):
    """GET /intake/new should render the intake form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/new")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "intake-form" in html or "Device Intake" in html


def test_intake_form_get_contains_branch_choices(monkeypatch):
    """Intake form should contain available branches."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode()
    assert "HQ - Headquarters" in html


# ===========================================================================
# B. Intake form POST (Create New Ticket submission)
# ===========================================================================

def _intake_form_data(ids):
    """Minimum valid data for intake form submission."""
    return {
        "branch_id": str(ids["branch_id"]),
        "category": "phones",
        "customer_name": "John Doe",
        "customer_phone": "555-0001",
        "customer_email": "john@example.com",
        "device_brand": "Apple",
        "device_model": "iPhone 14",
        "serial_number": "SN001",
        "reported_fault": "Cracked screen",
        "accepted_disclaimer": "y",
    }


def test_intake_form_post_creates_intake(monkeypatch):
    """POST /intake/new with valid data should create an IntakeSubmission and redirect."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    # Should redirect to intake detail
    assert resp.status_code == 302
    assert "/intake/" in resp.headers["Location"]

    with app.app_context():
        intake = IntakeSubmission.query.first()
        assert intake is not None
        assert intake.reported_fault == "Cracked screen"
        assert intake.customer_name == "John Doe"
        # Disclaimer acceptance should be created
        disclaimers = IntakeDisclaimerAcceptance.query.filter_by(intake_submission_id=intake.id).all()
        assert len(disclaimers) == 1
        assert disclaimers[0].accepted is True


def test_intake_form_post_creates_customer_and_device(monkeypatch):
    """POST should create or find customer and device records."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    data["customer_name"] = "New Customer"
    data["customer_phone"] = "555-9999"
    data["customer_email"] = "new@example.com"
    data["device_brand"] = "Samsung"
    data["device_model"] = "Galaxy S24"
    data["serial_number"] = "SN-NEW-001"
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        customer = Customer.query.filter_by(email="new@example.com").first()
        assert customer is not None
        assert customer.full_name == "New Customer"
        device = Device.query.filter_by(serial_number="SN-NEW-001").first()
        assert device is not None
        assert device.brand == "Samsung"
        assert device.customer_id == customer.id


def test_intake_form_post_with_existing_customer(monkeypatch):
    """POST with existing_customer_id should use existing customer."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    data["existing_customer_id"] = str(ids["customer_id"])
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.first()
        assert intake is not None
        assert intake.customer_id == ids["customer_id"]


def test_intake_form_post_creates_portal_token(monkeypatch):
    """POST should create a portal token for the new intake."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.first()
        token = PortalToken.query.filter_by(intake_submission_id=intake.id).first()
        assert token is not None
        assert token.token_type == "public_status_lookup"


def test_intake_form_post_enriched_notes(monkeypatch):
    """POST with device condition, pre-checks, and diagnosis should enrich intake notes."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    data["device_condition"] = "Minor scratches"
    data["check_powers_on"] = "y"
    data["check_screen_condition"] = "y"
    data["initial_diagnosis"] = "LCD damaged"
    data["recommended_repair"] = "Replace screen assembly"
    data["intake_notes"] = "Customer in a hurry"
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.first()
        assert "Minor scratches" in intake.intake_notes
        assert "LCD damaged" in intake.intake_notes
        assert "Replace screen assembly" in intake.intake_notes
        assert "Customer in a hurry" in intake.intake_notes


def test_intake_form_post_missing_required_fields(monkeypatch):
    """POST with missing required fields should re-render form (not crash)."""
    app, client, ids = _setup(monkeypatch)
    data = {"branch_id": str(ids["branch_id"]), "category": "phones"}
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    # Should not redirect (validation fails), re-renders form
    assert resp.status_code == 200

    with app.app_context():
        assert IntakeSubmission.query.count() == 0


# ===========================================================================
# C. Intake form POST without config (fallback test)
# ===========================================================================

def test_intake_form_post_without_disclaimer_config(monkeypatch):
    """POST should work even without DEFAULT_INTAKE_DISCLAIMER_TEXT in config (uses fallback)."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigNoDisclaimer)
    data = _intake_form_data(ids)
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    # Should NOT crash with KeyError — should redirect successfully
    assert resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.first()
        assert intake is not None
        disclaimer = IntakeDisclaimerAcceptance.query.filter_by(intake_submission_id=intake.id).first()
        assert disclaimer is not None
        assert "accept" in disclaimer.disclaimer_text.lower()


# ===========================================================================
# D. Intake detail and receipt
# ===========================================================================

def test_intake_detail_page(monkeypatch):
    """GET /intake/<id> should show intake details after creation."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302
    detail_url = resp.headers["Location"]
    resp2 = client.get(detail_url)
    assert resp2.status_code == 200


def test_intake_receipt_page(monkeypatch):
    """GET /intake/<id>/receipt should render."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    client.post("/intake/new", data=data, follow_redirects=False)

    with app.app_context():
        intake = IntakeSubmission.query.first()
        resp = client.get(f"/intake/{intake.id}/receipt")
        assert resp.status_code == 200


# ===========================================================================
# E. Intake conversion to ticket
# ===========================================================================

def test_intake_conversion_to_ticket(monkeypatch):
    """POST /intake/<id>/convert should create a ticket."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    client.post("/intake/new", data=data, follow_redirects=False)

    with app.app_context():
        intake = IntakeSubmission.query.first()
        intake_id = intake.id

    resp = client.post(f"/intake/{intake_id}/convert", follow_redirects=False)
    assert resp.status_code == 302
    assert "/tickets/" in resp.headers["Location"]

    with app.app_context():
        intake = db.session.get(IntakeSubmission, intake_id)
        assert intake.status == "converted"
        assert intake.converted_ticket_id is not None
        ticket = db.session.get(Ticket, intake.converted_ticket_id)
        assert ticket is not None
        assert ticket.issue_summary == "Cracked screen"


# ===========================================================================
# F. Fast Check-In GET (/tickets/new)
# ===========================================================================

def test_fast_checkin_get_returns_200(monkeypatch):
    """GET /tickets/new should render the fast check-in form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/tickets/new")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Fast Check-In" in html or "Check In Device" in html


def test_fast_checkin_contains_branch_choices(monkeypatch):
    """Fast check-in form should contain available branches."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/tickets/new")
    html = resp.data.decode()
    assert "HQ" in html


# ===========================================================================
# G. Fast Check-In POST (/tickets/new)
# ===========================================================================

def _checkin_form_data(ids):
    """Minimum valid data for fast check-in submission."""
    return {
        "branch_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "device_id": str(ids["device_id"]),
        "priority": "normal",
        "issue_summary": "Battery drains fast",
    }


def test_fast_checkin_post_creates_ticket(monkeypatch):
    """POST /tickets/new with valid data should create a Ticket and redirect."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302
    assert "/tickets" in resp.headers["Location"]

    with app.app_context():
        ticket = Ticket.query.first()
        assert ticket is not None
        assert ticket.issue_summary == "Battery drains fast"
        assert ticket.customer_id == ids["customer_id"]
        assert ticket.device_id == ids["device_id"]
        assert ticket.priority == "normal"


def test_fast_checkin_post_creates_intake_note(monkeypatch):
    """POST with device condition/accessories creates an intake note on the ticket."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    data["device_condition"] = "Minor dents"
    data["accessories"] = "Charger, case"
    data["customer_notes"] = "Needs it by Friday"
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        note = TicketNote.query.filter_by(ticket_id=ticket.id).first()
        assert note is not None
        assert "Minor dents" in note.content
        assert "Charger, case" in note.content
        assert "Needs it by Friday" in note.content


def test_fast_checkin_post_with_technician(monkeypatch):
    """POST with assigned technician should set status to assigned."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    data["assigned_technician_id"] = ids["user_id"]
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        assert ticket.assigned_technician_id is not None
        assert ticket.internal_status == "assigned"


def test_fast_checkin_post_without_technician(monkeypatch):
    """POST without technician should set status to unassigned."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        assert ticket.assigned_technician_id is None
        assert ticket.internal_status == "unassigned"


def test_fast_checkin_post_creates_portal_token(monkeypatch):
    """POST should create a portal token for the new ticket."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        token = PortalToken.query.filter_by(ticket_id=ticket.id).first()
        assert token is not None
        assert token.token_type == "public_status_lookup"


def test_fast_checkin_post_missing_required_fields(monkeypatch):
    """POST with missing required fields should re-render form (not crash)."""
    app, client, ids = _setup(monkeypatch)
    data = {"branch_id": str(ids["branch_id"])}
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    # Should re-render form, not crash
    assert resp.status_code == 200

    with app.app_context():
        assert Ticket.query.count() == 0


def test_fast_checkin_post_with_service(monkeypatch):
    """POST with repair_service_id should record the service in the intake note."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    data["repair_service_id"] = str(ids["service_id"])
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        note = TicketNote.query.filter_by(ticket_id=ticket.id).first()
        assert note is not None
        assert "Screen Repair" in note.content


# ===========================================================================
# H. AJAX endpoints on tickets blueprint
# ===========================================================================

def test_tickets_customer_search(monkeypatch):
    """GET /tickets/customer-search should return customer results."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/tickets/customer-search?q=John")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) >= 1


def test_tickets_customer_search_min_length(monkeypatch):
    """GET /tickets/customer-search with short query returns empty."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/tickets/customer-search?q=J")
    data = resp.get_json()
    assert data["items"] == []


def test_tickets_customer_devices(monkeypatch):
    """GET /tickets/customer/<id>/devices returns device list."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/customer/{ids['customer_id']}/devices")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert "Apple" in data[0]["label"]


def test_tickets_device_search(monkeypatch):
    """GET /tickets/device-search should return matching devices."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/device-search?q=iPhone&customer_id={ids['customer_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) >= 1


def test_tickets_device_create_json(monkeypatch):
    """POST /tickets/device-create-json should create a new device."""
    app, client, ids = _setup(monkeypatch)
    payload = {
        "customer_id": str(ids["customer_id"]),
        "brand": "Samsung",
        "model": "Galaxy S24",
        "category": "phones",
    }
    resp = client.post("/tickets/device-create-json", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    with app.app_context():
        device = Device.query.filter_by(model="Galaxy S24").first()
        assert device is not None
        assert device.brand == "Samsung"


def test_tickets_device_create_json_missing_fields(monkeypatch):
    """POST /tickets/device-create-json with missing fields returns error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/tickets/device-create-json", json={"customer_id": str(ids["customer_id"])})
    assert resp.status_code == 400


# ===========================================================================
# I. AJAX endpoints on intake blueprint
# ===========================================================================

def test_intake_customer_search(monkeypatch):
    """GET /intake/customer-search should return results."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/customer-search?q=John")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) >= 1


def test_intake_customer_detail(monkeypatch):
    """GET /intake/customer/<id> should return customer info."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/intake/customer/{ids['customer_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["full_name"] == "John Doe"


# ===========================================================================
# J. Navigation links
# ===========================================================================

def test_nav_contains_all_entry_points(monkeypatch):
    """Dashboard/nav should contain New Booking, Create New Ticket, and Fast Check-In."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/new")  # Any page with base.html
    html = resp.data.decode()
    assert "Create New Ticket" in html
    assert "Fast Check-In" in html
    assert "New Booking" in html


def test_nav_create_ticket_links_to_intake(monkeypatch):
    """'Create New Ticket' should link to /intake/new."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode()
    assert "/intake/new" in html


def test_nav_fast_checkin_links_to_tickets_new(monkeypatch):
    """'Fast Check-In' should link to /tickets/new."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode()
    assert "/tickets/new" in html


# ===========================================================================
# K. Permission enforcement
# ===========================================================================

def test_intake_requires_login(monkeypatch):
    """GET /intake/new without login should redirect to login."""
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

    client = app.test_client()
    resp = client.get("/intake/new")
    assert resp.status_code in (302, 401)


def test_fast_checkin_requires_login(monkeypatch):
    """GET /tickets/new without login should redirect to login."""
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

    client = app.test_client()
    resp = client.get("/tickets/new")
    assert resp.status_code in (302, 401, 403)


# ===========================================================================
# L. Intake list
# ===========================================================================

def test_intake_list_returns_200(monkeypatch):
    """GET /intake/ should list intakes."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/")
    assert resp.status_code == 200


def test_intake_list_shows_created_intake(monkeypatch):
    """GET /intake/ should show an intake after creation."""
    app, client, ids = _setup(monkeypatch)
    data = _intake_form_data(ids)
    client.post("/intake/new", data=data, follow_redirects=False)

    resp = client.get("/intake/")
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "INT-" in html  # Reference format


# ===========================================================================
# M. End-to-end: Full Intake → Conversion → Ticket exists
# ===========================================================================

def test_full_intake_to_ticket_e2e(monkeypatch):
    """Full end-to-end: create intake, convert, verify ticket exists."""
    app, client, ids = _setup(monkeypatch)

    # Step 1: Create intake
    data = _intake_form_data(ids)
    data["device_condition"] = "Good condition"
    data["initial_diagnosis"] = "Screen digitizer broken"
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.first()
        intake_id = intake.id
        assert intake.status == "pre_check_in"

    # Step 2: Convert to ticket
    resp = client.post(f"/intake/{intake_id}/convert", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        intake = db.session.get(IntakeSubmission, intake_id)
        assert intake.status == "converted"
        ticket = db.session.get(Ticket, intake.converted_ticket_id)
        assert ticket is not None
        assert ticket.customer_status == "Received"
        assert ticket.branch_id == ids["branch_id"]

    # Step 3: Verify ticket detail is accessible
    with app.app_context():
        ticket = Ticket.query.first()
        ticket_id = ticket.id
    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200


# ===========================================================================
# N. End-to-end: Fast Check-In → Ticket → Detail
# ===========================================================================

def test_fast_checkin_to_ticket_e2e(monkeypatch):
    """Fast check-in: create ticket directly, then view it."""
    app, client, ids = _setup(monkeypatch)
    data = _checkin_form_data(ids)
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.first()
        assert ticket is not None
        ticket_id = ticket.id

    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Battery drains fast" in html or ticket.ticket_number in html
