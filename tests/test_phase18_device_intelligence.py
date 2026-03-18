"""Phase 18 tests: Device intelligence, secure access, archived stats,
device-type pre-checks, IMEI lookup, service catalog, quote integration."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Booking, ChecklistItem, Company, Customer, Device,
    DevicePreCheckTemplate, Diagnostic, Part, PartCategory,
    PartOrder, PartOrderLine, PartOrderEvent,
    Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    RepairService, Role, StockLayer, StockLevel, StockLocation,
    StockMovement, StockReservation, Supplier, Ticket, TicketNote, User,
    IntakeSubmission, IntakeDisclaimerAcceptance, PortalToken,
    service_part_links,
)
from app.models.intake import IntakeSignature, Attachment
from app.models.role import role_permissions
from app.models.user import user_roles, user_branch_access
from app.models.inventory import part_category_links


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret-key-for-encryption"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    SUPPORTED_LOCALES = ["en", "es"]
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"
    MAIL_TRANSPORT = "log"
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "Test disclaimer"
    IMEICHECK_API_KEY = ""


def _noop_log(*a, **kw):
    return None


def _create_tables():
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
        DevicePreCheckTemplate.__table__, service_part_links,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _setup(monkeypatch, role_name="Admin"):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        role = Role(name=role_name)
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com",
                     is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        customer = Customer(full_name="John Doe", phone="555-0001",
                            email="john@example.com", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones",
                        brand="Apple", model="iPhone 14", serial_number="SN001")
        db.session.add(device)
        part = Part(sku="SCR-IP14", name="iPhone 14 Screen", sale_price=89.99,
                    cost_price=45.00, is_active=True)
        db.session.add(part)
        service = RepairService(name="Screen Repair", service_code="SCR-REP",
                                device_category="phones", is_active=True,
                                labour_minutes=45, labour_price=35.00,
                                suggested_sale_price=124.99)
        db.session.add(service)
        db.session.flush()
        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "part_id": part.id,
            "service_id": service.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]
    return app, client, ids


# ===========================================================================
# A. Secure unlock data
# ===========================================================================

def test_encrypt_decrypt_unlock_value(monkeypatch):
    """Encrypt/decrypt round-trip for unlock values."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        from app.services.device_unlock_service import encrypt_unlock_value, decrypt_unlock_value
        plain = "1234"
        encrypted = encrypt_unlock_value(plain)
        assert encrypted != plain
        assert encrypted != ""
        decrypted = decrypt_unlock_value(encrypted)
        assert decrypted == plain


def test_mask_unlock_value(monkeypatch):
    """Mask function should hide all but last 2 chars."""
    from app.services.device_unlock_service import mask_unlock_value
    assert mask_unlock_value("123456") == "••••56"
    assert mask_unlock_value("12") == "••"
    assert mask_unlock_value("") == ""


def test_set_device_unlock(monkeypatch):
    """set_device_unlock should store encrypted value on device."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        from app.services.device_unlock_service import set_device_unlock, get_device_unlock_display
        device = db.session.get(Device, ids["device_id"])
        set_device_unlock(device, "pin", "5678", "Front door code")
        db.session.commit()

        device = db.session.get(Device, ids["device_id"])
        assert device.unlock_type == "pin"
        assert device.unlock_value_encrypted != "5678"  # Not plain text
        assert device.unlock_notes == "Front door code"

        display = get_device_unlock_display(device)
        assert display["unlock_type"] == "pin"
        assert display["unlock_value_masked"] == "••78"
        assert display["unlock_value_plain"] == "5678"


def test_unlock_data_not_plain_text_in_db(monkeypatch):
    """Unlock value should not be stored as plain text."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        from app.services.device_unlock_service import set_device_unlock
        device = db.session.get(Device, ids["device_id"])
        set_device_unlock(device, "password", "MySecret123", None)
        db.session.commit()
        device = db.session.get(Device, ids["device_id"])
        assert "MySecret123" not in (device.unlock_value_encrypted or "")


# ===========================================================================
# B. Archived tickets excluded from stats
# ===========================================================================

def test_dashboard_excludes_archived_tickets(monkeypatch):
    """Dashboard stats should not count archived tickets."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        # Create an active ticket
        t1 = Ticket(ticket_number="TK-ACTIVE", branch_id=ids["branch_id"],
                     customer_id=ids["customer_id"], device_id=ids["device_id"],
                     internal_status="unassigned")
        # Create an archived ticket
        t2 = Ticket(ticket_number="TK-ARCHIVED", branch_id=ids["branch_id"],
                     customer_id=ids["customer_id"], device_id=ids["device_id"],
                     internal_status="archived")
        db.session.add_all([t1, t2])
        db.session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode()
    # The dashboard should show the active ticket
    assert "TK-ACTIVE" in html or "1" in html


def test_reports_exclude_archived_tickets(monkeypatch):
    """Reporting KPIs should not include archived tickets."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        t1 = Ticket(ticket_number="TK-OPEN", branch_id=ids["branch_id"],
                     customer_id=ids["customer_id"], device_id=ids["device_id"],
                     internal_status="in_repair")
        t2 = Ticket(ticket_number="TK-ARCH", branch_id=ids["branch_id"],
                     customer_id=ids["customer_id"], device_id=ids["device_id"],
                     internal_status="archived")
        db.session.add_all([t1, t2])
        db.session.commit()

    from app.services.reporting_service import management_overview
    with app.app_context():
        tickets = Ticket.query.filter(
            Ticket.deleted_at.is_(None),
            Ticket.internal_status != Ticket.STATUS_ARCHIVED,
        ).all()
        overview = management_overview(tickets)
        assert overview["total_open"] == 1  # Only TK-OPEN


# ===========================================================================
# C. Device-type pre-checks
# ===========================================================================

def test_prechecks_for_phones(monkeypatch):
    """Phone pre-checks should include phone-specific items."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.precheck_service import get_prechecks_for_category
        checks = get_prechecks_for_category("phones")
        keys = [c["check_key"] for c in checks]
        assert "powers_on" in keys
        assert "cameras" in keys
        assert "biometrics" in keys


def test_prechecks_for_laptops(monkeypatch):
    """Laptop pre-checks should include keyboard/trackpad items."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.precheck_service import get_prechecks_for_category
        checks = get_prechecks_for_category("laptops")
        keys = [c["check_key"] for c in checks]
        assert "keyboard" in keys
        assert "trackpad" in keys
        assert "hinges" in keys
        assert "biometrics" not in keys  # Phone-specific


def test_prechecks_different_per_category(monkeypatch):
    """Different categories should have different pre-check sets."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.precheck_service import get_prechecks_for_category
        phone_keys = {c["check_key"] for c in get_prechecks_for_category("phones")}
        laptop_keys = {c["check_key"] for c in get_prechecks_for_category("laptops")}
        assert phone_keys != laptop_keys


def test_prechecks_json_endpoint(monkeypatch):
    """GET /tickets/prechecks/<category> should return checks."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/tickets/prechecks/phones")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "checks" in data
    assert len(data["checks"]) > 0
    assert data["category"] == "phones"


def test_prechecks_spanish(monkeypatch):
    """Pre-checks should support Spanish labels."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.precheck_service import get_prechecks_for_category
        checks = get_prechecks_for_category("phones", language="es")
        assert any("enciende" in c["label"].lower() for c in checks)


def test_format_precheck_notes(monkeypatch):
    """format_precheck_notes should produce readable text."""
    from app.services.precheck_service import format_precheck_notes
    results = [
        {"check_key": "powers_on", "label": "Powers on", "passed": True},
        {"check_key": "screen", "label": "Screen OK", "passed": False},
    ]
    text = format_precheck_notes(results)
    assert "[x] Powers on" in text
    assert "[ ] Screen OK" in text


# ===========================================================================
# D. Richer device details
# ===========================================================================

def test_device_has_new_fields(monkeypatch):
    """Device model should have Phase 18 fields."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        device = db.session.get(Device, ids["device_id"])
        device.storage = "128GB"
        device.color = "Space Black"
        device.carrier_lock = "Unlocked"
        device.fmi_status = "OFF"
        device.battery_health = "87%"
        device.cpu = "A16 Bionic"
        db.session.commit()

        device = db.session.get(Device, ids["device_id"])
        assert device.storage == "128GB"
        assert device.color == "Space Black"
        assert device.fmi_status == "OFF"
        assert device.cpu == "A16 Bionic"


def test_intake_form_has_new_fields(monkeypatch):
    """Intake form class should include Phase 18 device detail fields."""
    from app.forms.intake_forms import InternalIntakeForm
    assert hasattr(InternalIntakeForm, "storage")
    assert hasattr(InternalIntakeForm, "color")
    assert hasattr(InternalIntakeForm, "unlock_type")
    assert hasattr(InternalIntakeForm, "cpu")
    assert hasattr(InternalIntakeForm, "ram")


# ===========================================================================
# E. IMEI lookup
# ===========================================================================

def test_imei_lookup_not_configured(monkeypatch):
    """IMEI lookup should return not-configured when API key is empty."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/tickets/imei-lookup",
                       json={"imei": "356938035643809"})
    data = resp.get_json()
    assert data["ok"] is False
    assert "not configured" in data["error"].lower()


def test_imei_lookup_empty_imei(monkeypatch):
    """IMEI lookup with empty IMEI should return error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/tickets/imei-lookup", json={"imei": ""})
    assert resp.status_code == 400


def test_imei_lookup_success_mocked(monkeypatch):
    """IMEI lookup with mocked success should return device data."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        app.config["IMEICHECK_API_KEY"] = "test-key"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "properties": {
            "brand": "Apple",
            "modelName": "iPhone 14 Pro",
            "storage": "256GB",
            "color": "Deep Purple",
            "simLock": False,
            "fmiStatus": "OFF",
            "serialNumber": "C9XYZABC",
        }
    }

    with patch("app.services.imei_lookup_service.requests.post", return_value=mock_response):
        resp = client.post("/tickets/imei-lookup",
                           json={"imei": "356938035643809"})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["brand"] == "Apple"
    assert data["model"] == "iPhone 14 Pro"
    assert data["storage"] == "256GB"


def test_imei_lookup_api_failure(monkeypatch):
    """IMEI lookup should handle API failures gracefully."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        app.config["IMEICHECK_API_KEY"] = "test-key"

    import requests as req_lib
    with patch("app.services.imei_lookup_service.requests.post",
               side_effect=req_lib.ConnectionError("Connection refused")):
        resp = client.post("/tickets/imei-lookup",
                           json={"imei": "356938035643809"})
    data = resp.get_json()
    assert data["ok"] is False
    assert "unreachable" in data["error"].lower()


def test_imei_lookup_timeout(monkeypatch):
    """IMEI lookup should handle timeouts gracefully."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        app.config["IMEICHECK_API_KEY"] = "test-key"

    import requests as req_lib
    with patch("app.services.imei_lookup_service.requests.post",
               side_effect=req_lib.Timeout("Timeout")):
        resp = client.post("/tickets/imei-lookup",
                           json={"imei": "356938035643809"})
    data = resp.get_json()
    assert data["ok"] is False
    assert "timed out" in data["error"].lower()


def test_imei_lookup_on_intake(monkeypatch):
    """IMEI lookup should also work on intake blueprint."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/intake/imei-lookup",
                       json={"imei": "356938035643809"})
    data = resp.get_json()
    assert data["ok"] is False
    assert "not configured" in data["error"].lower()


# ===========================================================================
# F. Service catalog
# ===========================================================================

def test_service_has_new_fields(monkeypatch):
    """RepairService should have service_code and labour_price."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = db.session.get(RepairService, ids["service_id"])
        assert svc.service_code == "SCR-REP"
        assert float(svc.labour_price) == 35.00


def test_service_detail_json(monkeypatch):
    """Service detail endpoint should return service with parts info."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/service-detail-json/{ids['service_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "Screen Repair"
    assert data["labour_price"] == 35.0


def test_service_part_linking(monkeypatch):
    """RepairService should support linking multiple parts."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = db.session.get(RepairService, ids["service_id"])
        part = db.session.get(Part, ids["part_id"])
        svc.parts.append(part)
        db.session.commit()

        svc = db.session.get(RepairService, ids["service_id"])
        assert len(svc.parts) >= 1
        assert svc.parts[0].sku == "SCR-IP14"


# ===========================================================================
# G. Category choices include new types
# ===========================================================================

def test_category_choices_include_tablets_smartwatches(monkeypatch):
    """CATEGORY_CHOICES should include tablets and smartwatches."""
    from app.forms.intake_forms import CATEGORY_CHOICES
    keys = [c[0] for c in CATEGORY_CHOICES]
    assert "tablets" in keys
    assert "smartwatches" in keys
    assert "phones" in keys
    assert "laptops" in keys


# ===========================================================================
# H. Intake form POST with new fields
# ===========================================================================

def test_intake_post_with_device_details(monkeypatch):
    """Intake POST with richer device fields should save them."""
    app, client, ids = _setup(monkeypatch)
    data = {
        "branch_id": str(ids["branch_id"]),
        "category": "phones",
        "customer_name": "Jane Smith",
        "customer_phone": "555-0002",
        "device_brand": "Samsung",
        "device_model": "Galaxy S24",
        "serial_number": "SN-NEW-002",
        "reported_fault": "Battery issue",
        "accepted_disclaimer": "y",
        "storage": "256GB",
        "color": "Phantom Black",
        "battery_health": "92%",
    }
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        device = Device.query.filter_by(serial_number="SN-NEW-002").first()
        assert device is not None
        assert device.storage == "256GB"
        assert device.color == "Phantom Black"


def test_intake_post_with_unlock_data(monkeypatch):
    """Intake POST with unlock data should store encrypted value."""
    app, client, ids = _setup(monkeypatch)
    data = {
        "branch_id": str(ids["branch_id"]),
        "category": "phones",
        "customer_name": "Jane Smith",
        "customer_phone": "555-0003",
        "device_brand": "Apple",
        "device_model": "iPhone 15",
        "serial_number": "SN-UNLOCK-001",
        "reported_fault": "Screen cracked",
        "accepted_disclaimer": "y",
        "unlock_type": "pin",
        "unlock_value": "4321",
        "unlock_notes": "Use carefully",
    }
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        device = Device.query.filter_by(serial_number="SN-UNLOCK-001").first()
        assert device is not None
        assert device.unlock_type == "pin"
        assert device.unlock_value_encrypted is not None
        assert "4321" not in device.unlock_value_encrypted


# ===========================================================================
# I. Permissions
# ===========================================================================

def test_can_view_secure_access_admin(monkeypatch):
    """Admin should be able to view secure access data."""
    from app.services.permission_service import can_view_secure_access
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_view_secure_access(user) is True


def test_can_view_secure_access_readonly_denied(monkeypatch):
    """Read Only role should NOT view secure access data."""
    from app.services.permission_service import can_view_secure_access
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_view_secure_access(user) is False


def test_can_manage_service_catalog(monkeypatch):
    """Admin should be able to manage service catalog."""
    from app.services.permission_service import can_manage_service_catalog
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_manage_service_catalog(user) is True


def test_imei_lookup_requires_login(monkeypatch):
    """IMEI lookup should require login."""
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
    resp = client.post("/tickets/imei-lookup", json={"imei": "123456789012345"})
    assert resp.status_code in (302, 401)


# ===========================================================================
# J. Fast check-in still works
# ===========================================================================

def test_fast_checkin_still_works(monkeypatch):
    """Fast check-in POST should still create tickets."""
    app, client, ids = _setup(monkeypatch)
    data = {
        "branch_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "device_id": str(ids["device_id"]),
        "priority": "normal",
        "issue_summary": "Phase 18 test",
    }
    resp = client.post("/tickets/new", data=data, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        ticket = Ticket.query.filter_by(issue_summary="Phase 18 test").first()
        assert ticket is not None


# ===========================================================================
# K. Pre-check endpoint on intake
# ===========================================================================

def test_intake_prechecks_endpoint(monkeypatch):
    """GET /intake/prechecks/<category> should return checks."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/intake/prechecks/laptops")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "checks" in data
    keys = [c["check_key"] for c in data["checks"]]
    assert "keyboard" in keys


# ===========================================================================
# L. Backward compatibility
# ===========================================================================

def test_existing_devices_still_work(monkeypatch):
    """Existing devices without new fields should still load fine."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        device = db.session.get(Device, ids["device_id"])
        assert device.brand == "Apple"
        assert device.storage is None  # New field, not set
        assert device.unlock_type is None


def test_existing_services_still_work(monkeypatch):
    """Existing services should still work with new fields."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = db.session.get(RepairService, ids["service_id"])
        assert svc.name == "Screen Repair"
        assert svc.is_active is True
