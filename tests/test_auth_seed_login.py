from app import create_app
from app.extensions import db
from app.models import Branch, Customer, Device, Role, Ticket, User
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD, seed_phase1_data


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
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


def test_seed_admin_and_login_flow(monkeypatch):
    app = create_app(TestConfig)

    with app.app_context():
        _create_core_tables()

        # Run seed twice to verify deterministic idempotent behavior.
        seed_phase1_data()
        seed_phase1_data()

        admin = User.query.filter_by(email=DEMO_ADMIN_EMAIL).first()
        assert admin is not None
        assert admin.is_active is True
        assert admin.check_password(DEMO_ADMIN_PASSWORD)
        assert admin.default_branch is not None
        assert len(admin.roles) >= 1
        assert len(admin.branches) >= 1

    # Avoid audit log writes in this focused auth/seed test.
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *args, **kwargs: None)

    client = app.test_client()

    valid_resp = client.post(
        "/auth/login",
        data={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert valid_resp.status_code == 302
    assert valid_resp.headers["Location"].endswith("/")

    invalid_resp = client.post(
        "/auth/login",
        data={"email": DEMO_ADMIN_EMAIL, "password": "wrong-password"},
        follow_redirects=True,
    )
    assert invalid_resp.status_code == 200
    assert b"Invalid credentials" in invalid_resp.data
