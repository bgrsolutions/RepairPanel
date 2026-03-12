import re

from app import create_app
from app.extensions import db
from app.models import (
    Attachment,
    Branch,
    Customer,
    Device,
    IntakeDisclaimerAcceptance,
    IntakeSignature,
    IntakeSubmission,
    PortalToken,
    Role,
    Ticket,
    User,
)
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD, seed_phase1_data


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
    UPLOAD_ROOT = "/tmp/ironcore-test-uploads"
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "test disclaimer"


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
        IntakeDisclaimerAcceptance.__table__,
        IntakeSignature.__table__,
        Attachment.__table__,
        PortalToken.__table__,
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
    resp = client.post(
        "/auth/login",
        data={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD, "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_internal_intake_creation_and_conversion(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.blueprints.intake.routes.log_action", lambda *args, **kwargs: None)

    client = app.test_client()
    _login(client)

    form_page = client.get("/intake/new")
    token = _extract_csrf_token(form_page.data)

    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        assert branch is not None

    create_resp = client.post(
        "/intake/new",
        data={
            "csrf_token": token,
            "branch_id": str(branch.id),
            "category": "phones",
            "customer_name": "Intake Person",
            "customer_phone": "+34111111111",
            "customer_email": "intake.person@example.com",
            "device_brand": "Apple",
            "device_model": "iPhone 13",
            "serial_number": "SER123",
            "imei": "123456789012345",
            "reported_fault": "Screen not working",
            "accessories": "Case",
            "intake_notes": "Needs urgent turnaround",
            "accepted_disclaimer": "y",
            "signature_data": "signature-payload",
        },
        follow_redirects=False,
    )
    assert create_resp.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.filter_by(customer_email="intake.person@example.com").first()
        assert intake is not None
        assert intake.status == "pre_check_in"
        assert IntakeDisclaimerAcceptance.query.filter_by(intake_submission_id=intake.id).count() == 1
        assert IntakeSignature.query.filter_by(intake_submission_id=intake.id).count() == 1

    convert_resp = client.post(f"/intake/{intake.id}/convert", follow_redirects=False)
    assert convert_resp.status_code == 302

    with app.app_context():
        refreshed = db.session.get(IntakeSubmission, intake.id)
        assert refreshed is not None
        assert refreshed.converted_ticket_id is not None
        assert refreshed.status == "converted"


def test_public_intake_submission_creates_pre_check_in():
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code="HQ").first()

    client = app.test_client()
    form_page = client.get("/public/check-in")
    assert form_page.status_code == 200
    token = _extract_csrf_token(form_page.data)

    resp = client.post(
        "/public/check-in",
        data={
            "csrf_token": token,
            "branch_id": str(branch.id),
            "preferred_language": "en",
            "category": "laptops",
            "customer_name": "Portal User",
            "customer_phone": "+34122222222",
            "customer_email": "portal.user@example.com",
            "preferred_contact_method": "phone",
            "device_brand": "Dell",
            "device_model": "XPS 13",
            "serial_number": "SERPUBL1",
            "imei": "",
            "reported_fault": "No power",
            "accessories": "Charger",
            "intake_notes": "Submitted from portal",
            "accepted_disclaimer": "y",
            "signature_data": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/public/check-in/thank-you" in resp.headers["Location"]

    with app.app_context():
        intake = IntakeSubmission.query.filter_by(customer_email="portal.user@example.com").first()
        assert intake is not None
        assert intake.source == "public"
        assert intake.status == "pre_check_in"
        assert PortalToken.query.filter_by(intake_submission_id=intake.id).count() >= 1
