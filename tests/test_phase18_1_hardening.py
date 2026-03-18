"""Phase 18.1 tests: Device Intelligence Hardening, Secure Access Fixes, and UI Completion.

Covers:
- Authenticated encryption (v1) for unlock values
- Legacy XOR decryption backward compatibility
- IMEI lookup UI/form behavior
- Pre-check UI/form behavior
- Quote service selection workflow
- Booking carry-through behavior
- Permissions
- Translation-sensitive rendering
"""

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
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
    SECRET_KEY = "test-secret-key-for-encryption-v1"
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
    DEVICE_UNLOCK_KEY = ""


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
# A. Authenticated encryption — v1 format
# ===========================================================================

def test_v1_encrypt_decrypt_roundtrip(monkeypatch):
    """New v1 format encrypts and decrypts correctly."""
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import encrypt_unlock_value, decrypt_unlock_value
    with app.test_request_context():
        for value in ["1234", "myP@ssw0rd!", "pattern123", "", "ab"]:
            encrypted = encrypt_unlock_value(value)
            decrypted = decrypt_unlock_value(encrypted)
            assert decrypted == value, f"Roundtrip failed for '{value}'"


def test_v1_format_has_version_byte(monkeypatch):
    """V1 encrypted value starts with version byte 0x01 after base64 decode."""
    import base64
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import encrypt_unlock_value
    with app.test_request_context():
        encrypted = encrypt_unlock_value("test")
        raw = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        assert raw[0] == 1, "First byte should be version 0x01"


def test_v1_different_nonces(monkeypatch):
    """Each encryption produces different ciphertext due to random nonce."""
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import encrypt_unlock_value
    with app.test_request_context():
        e1 = encrypt_unlock_value("same-value")
        e2 = encrypt_unlock_value("same-value")
        assert e1 != e2, "Two encryptions of the same value should differ"


def test_v1_tamper_detection(monkeypatch):
    """Tampering with ciphertext causes decryption to fall back to legacy (returns garbled)."""
    import base64
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import encrypt_unlock_value, decrypt_unlock_value
    with app.test_request_context():
        encrypted = encrypt_unlock_value("secret123")
        raw = bytearray(base64.urlsafe_b64decode(encrypted.encode("utf-8")))
        # Flip a byte in the ciphertext area
        raw[20] ^= 0xFF
        tampered = base64.urlsafe_b64encode(bytes(raw)).decode("utf-8")
        result = decrypt_unlock_value(tampered)
        # Should NOT return the original plaintext
        assert result != "secret123"


def test_v1_empty_values(monkeypatch):
    """Empty string encryption/decryption returns empty string."""
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import encrypt_unlock_value, decrypt_unlock_value
    with app.test_request_context():
        assert encrypt_unlock_value("") == ""
        assert decrypt_unlock_value("") == ""


# ===========================================================================
# B. Legacy backward compatibility
# ===========================================================================

def test_legacy_xor_decryption(monkeypatch):
    """Values encrypted with legacy XOR+base64 can still be decrypted."""
    import base64
    import hashlib
    app, _, _ = _setup(monkeypatch)
    with app.test_request_context():
        # Manually encrypt using the old XOR method
        plaintext = "1234"
        secret = app.config.get("SECRET_KEY", "dev-secret")
        key = hashlib.sha256(secret.encode("utf-8")).digest()
        key_cycle = (key * ((len(plaintext) // len(key)) + 1))[:len(plaintext)]
        obfuscated = bytes(a ^ b for a, b in zip(plaintext.encode("utf-8"), key_cycle))
        legacy_encrypted = base64.urlsafe_b64encode(obfuscated).decode("utf-8")

        from app.services.device_unlock_service import decrypt_unlock_value
        result = decrypt_unlock_value(legacy_encrypted)
        assert result == "1234", f"Legacy decrypt returned '{result}' instead of '1234'"


def test_new_writes_use_v1(monkeypatch):
    """set_device_unlock now writes v1 format, not legacy."""
    import base64
    app, _, ids = _setup(monkeypatch)
    from app.services.device_unlock_service import set_device_unlock
    with app.app_context():
        device = db.session.get(Device, ids["device_id"])
        set_device_unlock(device, "pin", "5678", "test notes")
        encrypted = device.unlock_value_encrypted
        raw = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        assert raw[0] == 1, "New writes should use v1 format"


# ===========================================================================
# C. Mask and display
# ===========================================================================

def test_mask_unlock_value(monkeypatch):
    """mask_unlock_value shows last 2 characters only."""
    app, _, _ = _setup(monkeypatch)
    from app.services.device_unlock_service import mask_unlock_value
    assert mask_unlock_value("123456") == "••••56"
    assert mask_unlock_value("ab") == "••"
    assert mask_unlock_value("") == ""
    assert mask_unlock_value("x") == "••"


def test_get_device_unlock_display(monkeypatch):
    """get_device_unlock_display returns properly masked data."""
    app, _, ids = _setup(monkeypatch)
    from app.services.device_unlock_service import set_device_unlock, get_device_unlock_display
    with app.app_context():
        device = db.session.get(Device, ids["device_id"])
        set_device_unlock(device, "pin", "9876", "Face ID enrolled")
        display = get_device_unlock_display(device)
        assert display["unlock_type"] == "pin"
        assert display["unlock_value_plain"] == "9876"
        assert display["unlock_value_masked"] == "••76"
        assert display["unlock_notes"] == "Face ID enrolled"
        assert display["has_unlock"] is True


# ===========================================================================
# D. IMEI lookup endpoints
# ===========================================================================

def test_imei_lookup_not_configured(monkeypatch):
    """IMEI lookup returns error when API key is not configured."""
    app, client, _ = _setup(monkeypatch)
    resp = client.post("/intake/imei-lookup",
                       json={"imei": "123456789012345"},
                       content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert "not configured" in data["error"]


def test_imei_lookup_empty_imei(monkeypatch):
    """IMEI lookup returns 400 for empty IMEI."""
    app, client, _ = _setup(monkeypatch)
    resp = client.post("/intake/imei-lookup",
                       json={"imei": ""},
                       content_type="application/json")
    assert resp.status_code == 400


def test_imei_lookup_tickets_endpoint(monkeypatch):
    """Tickets IMEI lookup endpoint works."""
    app, client, _ = _setup(monkeypatch)
    resp = client.post("/tickets/imei-lookup",
                       json={"imei": "123456789012345"},
                       content_type="application/json")
    data = resp.get_json()
    assert data["ok"] is False  # not configured


# ===========================================================================
# E. Pre-check endpoints
# ===========================================================================

def test_prechecks_phones(monkeypatch):
    """Pre-check endpoint returns checks for phones category."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/prechecks/phones")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "checks" in data
    assert len(data["checks"]) > 0
    assert data["category"] == "phones"
    # Verify check structure
    check = data["checks"][0]
    assert "check_key" in check
    assert "label" in check


def test_prechecks_spanish(monkeypatch):
    """Pre-check endpoint returns Spanish labels when requested."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/prechecks/phones?lang=es")
    data = resp.get_json()
    assert len(data["checks"]) > 0
    # Spanish fallback labels should contain Spanish text
    labels = [c["label"] for c in data["checks"]]
    assert any("dispositivo" in l.lower() for l in labels)


def test_prechecks_all_categories(monkeypatch):
    """Pre-check endpoint returns checks for all categories."""
    app, client, _ = _setup(monkeypatch)
    for cat in ["phones", "tablets", "laptops", "desktops", "game_consoles", "smartwatches", "other"]:
        resp = client.get(f"/intake/prechecks/{cat}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["checks"]) > 0, f"No checks for {cat}"


def test_prechecks_tickets_endpoint(monkeypatch):
    """Tickets blueprint also exposes prechecks endpoint."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/tickets/prechecks/phones")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["checks"]) > 0


# ===========================================================================
# F. Service detail JSON endpoint
# ===========================================================================

def test_service_detail_json(monkeypatch):
    """Service detail endpoint returns correct data."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/service-detail-json/{ids['service_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "Screen Repair"
    assert data["service_code"] == "SCR-REP"
    assert data["labour_price"] == 35.0
    assert data["labour_minutes"] == 45


def test_service_detail_json_not_found(monkeypatch):
    """Service detail returns 404 for nonexistent service."""
    app, client, _ = _setup(monkeypatch)
    fake_id = uuid.uuid4()
    resp = client.get(f"/tickets/service-detail-json/{fake_id}")
    assert resp.status_code == 404


# ===========================================================================
# G. Intake form rendering — device detail fields
# ===========================================================================

def test_intake_form_has_device_detail_fields(monkeypatch):
    """InternalIntakeForm has all Phase 18 device detail fields."""
    from app.forms.intake_forms import InternalIntakeForm
    for field in ["storage", "color", "carrier_lock", "fmi_status", "battery_health",
                  "cosmetic_condition", "cpu", "ram", "storage_type", "gpu", "os_info",
                  "unlock_type", "unlock_value", "unlock_notes", "precheck_results_json"]:
        assert hasattr(InternalIntakeForm, field), f"Missing field: {field}"


def test_intake_new_renders_imei_lookup(monkeypatch):
    """Intake form page includes IMEI lookup button for Admin users."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/new")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "imei-lookup-btn" in html


def test_intake_new_renders_category_fields(monkeypatch):
    """Intake form page includes category-dependent device fields."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode("utf-8")
    assert "phone-tablet-fields" in html
    assert "laptop-desktop-fields" in html
    assert "device-storage" in html


def test_intake_new_renders_unlock_fields(monkeypatch):
    """Intake form page includes secure access fields for authorized users."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode("utf-8")
    assert "Secure Access Data" in html or "unlock_type" in html


def test_intake_new_renders_dynamic_prechecks(monkeypatch):
    """Intake form page includes dynamic prechecks container."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode("utf-8")
    assert "dynamic-prechecks" in html


def test_intake_readonly_user_no_unlock_fields(monkeypatch):
    """Read Only user should not see secure access fields."""
    app, client, _ = _setup(monkeypatch, role_name="Read Only")
    resp = client.get("/intake/new")
    html = resp.data.decode("utf-8")
    assert "Secure Access Data" not in html


# ===========================================================================
# H. Quote service selection
# ===========================================================================

def test_quote_form_includes_services_data(monkeypatch):
    """Quote creation page includes services data for service selector."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number="TK-001",
            branch_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            internal_status="assigned",
            customer_status="Received",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    resp = client.get(f"/quotes/ticket/{ticket_id}/new")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "service-catalog-select" in html
    assert "Screen Repair" in html


# ===========================================================================
# I. Booking carry-through
# ===========================================================================

def test_booking_conversion_preserves_device_details(monkeypatch):
    """When a booking is converted, the ticket references the same device with rich details."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        # Set up rich device details
        device = db.session.get(Device, ids["device_id"])
        device.storage = "256GB"
        device.color = "Blue"
        device.carrier_lock = "Unlocked"
        db.session.commit()

        # Create a booking
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="arrived",
        )
        db.session.add(booking)
        db.session.commit()
        booking_id = booking.id

    # Convert the booking
    resp = client.post(f"/bookings/{booking_id}/convert", data={
        "device_id": str(ids["device_id"]),
        "issue_summary": "Broken screen",
        "device_condition": "Cracked",
        "accessories": "Charger",
    }, follow_redirects=False)
    # Should redirect to ticket detail
    assert resp.status_code in (302, 200)

    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.converted_ticket_id is not None
        ticket = db.session.get(Ticket, booking.converted_ticket_id)
        assert ticket is not None
        assert ticket.device_id == ids["device_id"]
        # The device retains rich details
        assert ticket.device.storage == "256GB"
        assert ticket.device.color == "Blue"


# ===========================================================================
# J. Permissions
# ===========================================================================

def _mock_role(role_name):
    """Create a mock role with proper name attribute."""
    role = MagicMock()
    role.name = role_name
    return role


def _mock_user(role_name):
    """Create a mock user with a specific role."""
    user = MagicMock()
    user.is_authenticated = True
    user.roles = [_mock_role(role_name)]
    return user


def test_permission_can_view_secure_access(monkeypatch):
    """Admin and Technician can view secure access, Read Only cannot."""
    from app.services.permission_service import can_view_secure_access

    app, _, _ = _setup(monkeypatch)
    with app.test_request_context():
        assert can_view_secure_access(_mock_user("Admin")) is True
        assert can_view_secure_access(_mock_user("Technician")) is True
        assert can_view_secure_access(_mock_user("Read Only")) is False


def test_permission_can_lookup_imei(monkeypatch):
    """IMEI lookup allowed for Admin, Front Desk, Technician."""
    from app.services.permission_service import can_lookup_imei

    app, _, _ = _setup(monkeypatch)
    with app.test_request_context():
        for role_name in ["Admin", "Front Desk", "Technician", "Manager"]:
            assert can_lookup_imei(_mock_user(role_name)) is True, f"Should allow {role_name}"
        assert can_lookup_imei(_mock_user("Read Only")) is False


def test_permission_can_manage_service_catalog(monkeypatch):
    """Only management roles can manage service catalog."""
    from app.services.permission_service import can_manage_service_catalog

    app, _, _ = _setup(monkeypatch)
    with app.test_request_context():
        for role_name in ["Admin", "Manager", "Super Admin"]:
            assert can_manage_service_catalog(_mock_user(role_name)) is True
        for role_name in ["Technician", "Front Desk", "Read Only"]:
            assert can_manage_service_catalog(_mock_user(role_name)) is False


# ===========================================================================
# K. Config
# ===========================================================================

def test_config_has_device_unlock_key():
    """Config class has DEVICE_UNLOCK_KEY."""
    from app.config import Config
    assert hasattr(Config, "DEVICE_UNLOCK_KEY")


def test_dedicated_unlock_key_used(monkeypatch):
    """When DEVICE_UNLOCK_KEY is set, it takes priority over SECRET_KEY."""
    import base64

    class CustomConfig(TestConfig):
        DEVICE_UNLOCK_KEY = "custom-dedicated-key-for-unlock"

    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(CustomConfig)
    from app.services.device_unlock_service import encrypt_unlock_value, decrypt_unlock_value
    with app.test_request_context():
        encrypted = encrypt_unlock_value("test-value")
        decrypted = decrypt_unlock_value(encrypted)
        assert decrypted == "test-value"

    # Ensure it's different from what SECRET_KEY would produce
    app2 = create_app(TestConfig)
    with app2.test_request_context():
        # Try decrypting with different key — should not get original value from v1
        result = decrypt_unlock_value(encrypted)
        # v1 HMAC check will fail, falls to legacy which will produce garbled output
        assert result != "test-value"


# ===========================================================================
# L. Precheck service functions
# ===========================================================================

def test_parse_precheck_results(monkeypatch):
    """parse_precheck_results correctly parses form data."""
    app, _, _ = _setup(monkeypatch)
    from app.services.precheck_service import parse_precheck_results
    with app.test_request_context():
        form_data = {
            "precheck_powers_on": "on",
            "precheck_screen_condition": "on",
            # charging not checked
        }
        results = parse_precheck_results(form_data, "phones")
        powers_on = next(r for r in results if r["check_key"] == "powers_on")
        assert powers_on["passed"] is True
        charging = next(r for r in results if r["check_key"] == "charging_port")
        assert charging["passed"] is False


def test_format_precheck_notes(monkeypatch):
    """format_precheck_notes produces readable text."""
    app, _, _ = _setup(monkeypatch)
    from app.services.precheck_service import format_precheck_notes
    results = [
        {"check_key": "powers_on", "label": "Powers on", "passed": True},
        {"check_key": "screen", "label": "Screen OK", "passed": False},
    ]
    text = format_precheck_notes(results)
    assert "[x] Powers on" in text
    assert "[ ] Screen OK" in text


# ===========================================================================
# M. Intake POST with new fields
# ===========================================================================

def test_intake_post_with_device_details_and_unlock(monkeypatch):
    """Intake POST processes richer device details and unlock data."""
    app, client, ids = _setup(monkeypatch)
    data = {
        "branch_id": str(ids["branch_id"]),
        "category": "phones",
        "customer_name": "Jane Smith",
        "customer_phone": "555-0099",
        "device_brand": "Samsung",
        "device_model": "Galaxy S24",
        "serial_number": "SN-NEW-001",
        "imei": "123456789012345",
        "storage": "256GB",
        "color": "Purple",
        "carrier_lock": "Unlocked",
        "fmi_status": "OFF",
        "battery_health": "92%",
        "unlock_type": "pin",
        "unlock_value": "1234",
        "unlock_notes": "Fingerprint also",
        "reported_fault": "Cracked screen",
        "accepted_disclaimer": "y",
    }
    resp = client.post("/intake/new", data=data, follow_redirects=False)
    assert resp.status_code in (302, 200)

    with app.app_context():
        device = Device.query.filter_by(serial_number="SN-NEW-001").first()
        assert device is not None
        assert device.storage == "256GB"
        assert device.color == "Purple"
        assert device.carrier_lock == "Unlocked"
        assert device.unlock_type == "pin"
        assert device.unlock_value_encrypted is not None
        assert device.unlock_value_encrypted != "1234"  # Not stored in plaintext


# ===========================================================================
# N. Translation rendering
# ===========================================================================

def test_intake_page_renders_in_english(monkeypatch):
    """Intake page renders English text by default."""
    app, client, _ = _setup(monkeypatch)
    resp = client.get("/intake/new")
    html = resp.data.decode("utf-8")
    assert "Device Intake" in html
    assert "Pre-Repair Quick Check" in html
