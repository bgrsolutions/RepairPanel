import re

from app import create_app
from app.extensions import db
from app.models import Branch, Customer, Device, Role, Ticket, User
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import (
    DEMO_ADMIN_EMAIL,
    DEMO_ADMIN_PASSWORD,
    LEGACY_DEMO_ADMIN_EMAILS,
    seed_phase1_data,
)


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


def _create_core_tables():
    # Intentionally skip audit_logs in SQLite tests (JSONB-only column in current phase model).
    for table in [
        Branch.__table__,
        Role.__table__,
        Customer.__table__,
        User.__table__,
        role_permissions,
        user_roles,
        user_branch_access,
        Device.__table__,
        Ticket.__table__,
    ]:
        table.create(bind=db.engine, checkfirst=True)


def _extract_csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match is not None, "csrf token not found in login page"
    return match.group(1).decode("utf-8")


def test_seed_admin_normalization_and_login_flow(monkeypatch):
    app = create_app(TestConfig)

    with app.app_context():
        _create_core_tables()

        # Pre-create one legacy demo account to validate normalization/migration behavior.
        legacy = User(full_name="Legacy Admin", email="admin@ironcore.local", preferred_language="en", is_active=False)
        legacy.set_password("legacypass123")
        db.session.add(legacy)
        db.session.commit()

        # Run seed twice to verify deterministic idempotent behavior.
        seed_phase1_data()
        seed_phase1_data()

        canonical = User.query.filter_by(email=DEMO_ADMIN_EMAIL).first()
        assert canonical is not None
        assert canonical.is_active is True
        assert canonical.check_password(DEMO_ADMIN_PASSWORD)
        assert canonical.default_branch is not None
        assert len(canonical.roles) >= 1
        assert len(canonical.branches) >= 1

        for legacy_email in LEGACY_DEMO_ADMIN_EMAILS:
            assert User.query.filter_by(email=legacy_email).first() is None

    # Avoid audit log writes in this focused auth/seed test.
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)

    client = app.test_client()

    login_page = client.get("/auth/login")
    assert login_page.status_code == 200
    csrf_token = _extract_csrf_token(login_page.data)

    valid_resp = client.post(
        "/auth/login",
        data={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD, "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert valid_resp.status_code == 302
    assert valid_resp.headers["Location"].endswith("/")

    login_page_again = client.get("/auth/login")
    csrf_token_invalid = _extract_csrf_token(login_page_again.data)

    invalid_resp = client.post(
        "/auth/login",
        data={"email": DEMO_ADMIN_EMAIL, "password": "wrong-password", "csrf_token": csrf_token_invalid},
        follow_redirects=True,
    )
    assert invalid_resp.status_code == 200
    assert b"Invalid credentials" in invalid_resp.data
