"""Phase 13 — Roles, Permissions & Staff Controls tests.

Covers:
- Permission service functions (role checks, permission helpers)
- Route protection (server-side enforcement via @permission_required)
- UI visibility by role (template-level conditional rendering)
- Safe defaults (unknown roles get no privilege)
- Permission proxy for templates
- Regression: existing Phase 12 behavior intact
"""
import re
import uuid
from datetime import datetime
from unittest.mock import patch

_noop = lambda *a, **kw: None

def _patch_log_action(fn):
    """Decorator that patches log_action in all modules that import it."""
    fn = patch("app.services.audit_service.log_action", _noop)(fn)
    fn = patch("app.services.auth_service.log_action", _noop)(fn)
    fn = patch("app.blueprints.tickets.routes.log_action", _noop)(fn)
    fn = patch("app.blueprints.quotes.routes.log_action", _noop)(fn)
    return fn

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Customer, Device, Diagnostic, Part, PartOrder,
    PortalToken, Quote, RepairChecklist, RepairService, Role,
    StockMovement, StockReservation, StockLayer, Supplier, Ticket,
    TicketNote, User, Booking, IntakeSubmission, IntakeDisclaimerAcceptance,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, PartCategory, StockLevel, StockLocation
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.permission_service import (
    _user_roles, is_admin, is_management, is_workshop, is_frontdesk,
    is_inventory_staff, can_manage_settings, can_manage_users,
    can_manage_inventory, can_delete_part, can_create_quote,
    can_manage_quote, can_create_ticket, can_progress_workflow,
    can_manage_checklists, can_consume_reservation,
    can_manage_customer_portal, can_send_customer_updates,
    can_view_inventory, can_view_reports, permission_context,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_FRONT_DESK,
    ROLE_TECHNICIAN, ROLE_INVENTORY, ROLE_READ_ONLY,
)
from app.services.seed_service import seed_phase1_data


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    SUPPORTED_LOCALES = ['en', 'es']
    DEFAULT_BRANCH_CODE = 'HQ'
    DEFAULT_INTAKE_DISCLAIMER_TEXT = 'Test disclaimer'
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07


def _create_tables():
    tables = [
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__,
        role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, TicketNote.__table__,
        Diagnostic.__table__,
        IntakeSubmission.__table__, IntakeDisclaimerAcceptance.__table__, PortalToken.__table__,
        Quote.__table__, QuoteOption.__table__, QuoteLine.__table__, QuoteApproval.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, PartSupplier.__table__,
        StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        RepairChecklist.__table__, ChecklistItem.__table__,
        RepairService.__table__, Booking.__table__,
        AppSetting.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _csrf(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1).decode()
    # Fallback: look for value="..." name="csrf_token" order
    m2 = re.search(rb'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert m2, "No csrf_token found in page"
    return m2.group(1).decode()


def _get_csrf(client):
    """Get a CSRF token from the login page (always has a form)."""
    # After login, re-fetch login page to get a fresh csrf token from the form
    # This works because Flask-WTF generates tokens based on session
    p = client.get('/auth/login')
    try:
        return _csrf(p.data)
    except AssertionError:
        # If no form is found (e.g. redirected), try the tickets/new page
        p = client.get('/tickets/new')
        return _csrf(p.data)


def _login(client, email='admin@ironcore.com', password='admin1234'):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={
        'email': email, 'password': password, 'csrf_token': token,
    }, follow_redirects=True)
    return r


def _create_user_with_role(role_name, email, password='test1234'):
    """Create a user with a specific role. Must be called in app context."""
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, description=role_name)
        db.session.add(role)
        db.session.flush()
    user = User(
        email=email,
        full_name=f"Test {role_name}",
        is_active=True,
    )
    user.set_password(password)
    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


def _setup_ticket(app, status="in_repair"):
    """Create a ticket and return its ID."""
    with app.app_context():
        branch = Branch.query.first()
        customer = Customer.query.first()
        if not customer:
            customer = Customer(full_name="Test Customer", email="cust@test.com")
            db.session.add(customer)
            db.session.flush()
        device = Device.query.first()
        if not device:
            device = Device(customer_id=customer.id, brand="Apple", model="iPhone 14", category="smartphone")
            db.session.add(device)
            db.session.flush()
        ticket = Ticket(
            ticket_number=f"HQ-{Ticket.query.count() + 1:05d}",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status=status,
            customer_status="In Progress",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.commit()
        return str(ticket.id)


# ─── Permission service unit tests ───────────────────────────────


@_patch_log_action
def test_user_roles_unauthenticated():
    """_user_roles returns empty set for unauthenticated users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = False
            roles = []

        assert _user_roles(FakeUser()) == set()


@_patch_log_action
def test_user_roles_none_user():
    """_user_roles returns empty set for None user."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        assert _user_roles(None) == set()


@_patch_log_action
def test_is_admin_check():
    """is_admin returns True only for Super Admin and Admin."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        assert is_admin(FakeUser(["Admin"])) is True
        assert is_admin(FakeUser(["Super Admin"])) is True
        assert is_admin(FakeUser(["Manager"])) is False
        assert is_admin(FakeUser(["Technician"])) is False
        assert is_admin(FakeUser(["Read Only"])) is False


@_patch_log_action
def test_is_management_check():
    """is_management includes Super Admin, Admin, Manager."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        assert is_management(FakeUser(["Manager"])) is True
        assert is_management(FakeUser(["Admin"])) is True
        assert is_management(FakeUser(["Technician"])) is False
        assert is_management(FakeUser(["Front Desk"])) is False


@_patch_log_action
def test_is_workshop_check():
    """is_workshop includes Super Admin, Admin, Manager, Technician."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        assert is_workshop(FakeUser(["Technician"])) is True
        assert is_workshop(FakeUser(["Manager"])) is True
        assert is_workshop(FakeUser(["Front Desk"])) is False
        assert is_workshop(FakeUser(["Read Only"])) is False
        assert is_workshop(FakeUser(["Inventory"])) is False


@_patch_log_action
def test_is_frontdesk_check():
    """is_frontdesk includes Super Admin, Admin, Manager, Front Desk."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        assert is_frontdesk(FakeUser(["Front Desk"])) is True
        assert is_frontdesk(FakeUser(["Admin"])) is True
        assert is_frontdesk(FakeUser(["Technician"])) is False


@_patch_log_action
def test_is_inventory_staff_check():
    """is_inventory_staff includes Super Admin, Admin, Manager, Inventory."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        assert is_inventory_staff(FakeUser(["Inventory"])) is True
        assert is_inventory_staff(FakeUser(["Admin"])) is True
        assert is_inventory_staff(FakeUser(["Technician"])) is False


@_patch_log_action
def test_specific_permission_functions():
    """Test specific permission check functions map to correct role groups."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True

            def __init__(self, role_names):
                self.roles = [type('R', (), {'name': n})() for n in role_names]

        admin = FakeUser(["Admin"])
        manager = FakeUser(["Manager"])
        tech = FakeUser(["Technician"])
        frontdesk = FakeUser(["Front Desk"])
        inventory = FakeUser(["Inventory"])
        readonly = FakeUser(["Read Only"])

        # can_manage_settings = admin only
        assert can_manage_settings(admin) is True
        assert can_manage_settings(manager) is False

        # can_manage_users = management
        assert can_manage_users(admin) is True
        assert can_manage_users(manager) is True
        assert can_manage_users(tech) is False

        # can_manage_inventory = inventory staff
        assert can_manage_inventory(admin) is True
        assert can_manage_inventory(inventory) is True
        assert can_manage_inventory(tech) is False

        # can_delete_part = management
        assert can_delete_part(admin) is True
        assert can_delete_part(manager) is True
        assert can_delete_part(inventory) is False

        # can_create_quote = management or frontdesk
        assert can_create_quote(admin) is True
        assert can_create_quote(frontdesk) is True
        assert can_create_quote(tech) is False

        # can_manage_quote = management
        assert can_manage_quote(admin) is True
        assert can_manage_quote(frontdesk) is False

        # can_create_ticket = management, frontdesk, or workshop
        assert can_create_ticket(admin) is True
        assert can_create_ticket(frontdesk) is True
        assert can_create_ticket(tech) is True
        assert can_create_ticket(readonly) is False

        # can_progress_workflow = workshop
        assert can_progress_workflow(tech) is True
        assert can_progress_workflow(frontdesk) is False

        # can_manage_checklists = workshop
        assert can_manage_checklists(tech) is True
        assert can_manage_checklists(readonly) is False

        # can_consume_reservation = workshop
        assert can_consume_reservation(tech) is True
        assert can_consume_reservation(inventory) is False

        # can_manage_customer_portal = management
        assert can_manage_customer_portal(admin) is True
        assert can_manage_customer_portal(tech) is False

        # can_send_customer_updates = management, frontdesk, or workshop
        assert can_send_customer_updates(admin) is True
        assert can_send_customer_updates(frontdesk) is True
        assert can_send_customer_updates(tech) is True
        assert can_send_customer_updates(readonly) is False

        # can_view_inventory = all staff
        assert can_view_inventory(readonly) is True
        assert can_view_inventory(tech) is True

        # can_view_reports = management
        assert can_view_reports(admin) is True
        assert can_view_reports(tech) is False


@_patch_log_action
def test_safe_default_unknown_role():
    """Users with unknown roles get no privileged access."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True
            roles = [type('R', (), {'name': 'Unknown Role'})()]

        user = FakeUser()
        assert is_admin(user) is False
        assert is_management(user) is False
        assert is_workshop(user) is False
        assert is_frontdesk(user) is False
        assert is_inventory_staff(user) is False
        assert can_manage_settings(user) is False
        assert can_create_ticket(user) is False
        assert can_view_reports(user) is False


@_patch_log_action
def test_safe_default_no_roles():
    """Users with empty roles get no privileged access."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        class FakeUser:
            is_authenticated = True
            roles = []

        user = FakeUser()
        assert is_admin(user) is False
        assert can_manage_settings(user) is False
        assert can_create_ticket(user) is False


# ─── Permission proxy tests ─────────────────────────────────


@_patch_log_action
def test_permission_proxy_returns_dict_with_perms():
    """permission_context returns a dict with a perms proxy."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        ctx = permission_context()
        assert "perms" in ctx
        proxy = ctx["perms"]
        # proxy attributes should exist
        assert hasattr(proxy, "is_admin")
        assert hasattr(proxy, "can_manage_settings")
        assert hasattr(proxy, "can_create_ticket")


# ─── Route protection integration tests ─────────────────────


@_patch_log_action
def test_settings_route_blocked_for_non_admin():
    """Settings routes return 403 for non-admin users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    # Settings index should be blocked
    r = client.get('/settings/')
    assert r.status_code == 403


@_patch_log_action
def test_settings_route_allowed_for_admin():
    """Settings routes return 200 for admin users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    _login(client)

    r = client.get('/settings/')
    assert r.status_code == 200


@_patch_log_action
def test_create_ticket_blocked_for_readonly():
    """Create ticket route returns 403 for Read Only users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "readonly@test.com")

    client = app.test_client()
    _login(client, 'readonly@test.com', 'test1234')

    r = client.get('/tickets/new')
    assert r.status_code == 403


@_patch_log_action
def test_create_ticket_allowed_for_technician():
    """Create ticket route returns 200 for Technician users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    r = client.get('/tickets/new')
    assert r.status_code == 200


@_patch_log_action
def test_quick_status_blocked_for_frontdesk():
    """Quick status route returns 403 for Front Desk (not workshop)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Front Desk", "fd@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'fd@test.com', 'test1234')

    # Get csrf
    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/quick-status', data={
        'csrf_token': csrf, 'action': 'start_repair',
    })
    assert r.status_code == 403


@_patch_log_action
def test_quick_status_allowed_for_technician():
    """Quick status route works for Technician users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app, status="assigned")

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/quick-status', data={
        'csrf_token': csrf, 'action': 'start_repair',
    })
    # Should redirect (302) on success, not 403
    assert r.status_code == 302


@_patch_log_action
def test_regenerate_token_blocked_for_technician():
    """Regenerate portal token blocked for Technician (needs management)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/regenerate-portal-token', data={
        'csrf_token': csrf,
    })
    assert r.status_code == 403


@_patch_log_action
def test_regenerate_token_allowed_for_admin():
    """Regenerate portal token allowed for Admin."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client)

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/regenerate-portal-token', data={
        'csrf_token': csrf,
    })
    assert r.status_code == 302


@_patch_log_action
def test_checklist_create_blocked_for_readonly():
    """Checklist creation blocked for Read Only users."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/checklists/create', data={
        'csrf_token': csrf, 'checklist_type': 'pre_repair',
    })
    assert r.status_code == 403


@_patch_log_action
def test_checklist_create_allowed_for_technician():
    """Checklist creation allowed for Technician."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/checklists/create', data={
        'csrf_token': csrf, 'checklist_type': 'pre_repair',
    }, follow_redirects=True)
    assert r.status_code == 200


@_patch_log_action
def test_inventory_new_part_blocked_for_readonly():
    """New part route blocked for Read Only."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    r = client.get('/inventory/parts/new')
    assert r.status_code == 403


@_patch_log_action
def test_inventory_new_part_allowed_for_inventory_role():
    """New part route allowed for Inventory role."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Inventory", "inv@test.com")

    client = app.test_client()
    _login(client, 'inv@test.com', 'test1234')

    r = client.get('/inventory/parts/new')
    assert r.status_code == 200


@_patch_log_action
def test_quote_create_blocked_for_technician():
    """Quote creation blocked for Technician (needs management or frontdesk)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    r = client.get(f'/quotes/ticket/{ticket_id}/new')
    assert r.status_code == 403


@_patch_log_action
def test_quote_create_allowed_for_frontdesk():
    """Quote creation allowed for Front Desk."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Front Desk", "fd@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'fd@test.com', 'test1234')

    r = client.get(f'/quotes/ticket/{ticket_id}/new')
    assert r.status_code == 200


@_patch_log_action
def test_quote_send_blocked_for_frontdesk():
    """Quote send blocked for Front Desk (needs management)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Front Desk", "fd@test.com")
        ticket_id = _setup_ticket(app)
        # Create a quote
        ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
        quote = Quote(ticket_id=ticket.id, version=1, status="draft")
        db.session.add(quote)
        db.session.flush()
        approval = QuoteApproval(quote_id=quote.id, status="pending", language="en")
        db.session.add(approval)
        db.session.commit()
        quote_id = str(quote.id)

    client = app.test_client()
    _login(client, 'fd@test.com', 'test1234')

    # Get csrf from ticket detail page (has forms)
    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/quotes/{quote_id}/send', data={'csrf_token': csrf})
    assert r.status_code == 403


@_patch_log_action
def test_quote_send_allowed_for_admin():
    """Quote send allowed for Admin."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        ticket_id = _setup_ticket(app)
        ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
        quote = Quote(ticket_id=ticket.id, version=1, status="draft")
        db.session.add(quote)
        db.session.flush()
        approval = QuoteApproval(quote_id=quote.id, status="pending", language="en")
        db.session.add(approval)
        db.session.commit()
        quote_id = str(quote.id)

    client = app.test_client()
    _login(client)

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/quotes/{quote_id}/send', data={'csrf_token': csrf})
    assert r.status_code == 302


# ─── UI visibility tests ────────────────────────────────────


@_patch_log_action
def test_admin_sees_settings_in_nav():
    """Admin user sees Settings link in navigation."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    _login(client)

    r = client.get('/')
    assert b'Settings' in r.data


@_patch_log_action
def test_readonly_does_not_see_settings_in_nav():
    """Read Only user does not see Settings link in navigation."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    r = client.get('/')
    # The Settings link is inside the Admin dropdown which is hidden for non-admin
    assert b'>Settings<' not in r.data


@_patch_log_action
def test_readonly_does_not_see_fast_checkin():
    """Read Only user does not see Fast Check-In button."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    r = client.get('/')
    assert b'Fast Check-In' not in r.data


@_patch_log_action
def test_admin_sees_fast_checkin():
    """Admin user sees Fast Check-In button."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    _login(client)

    r = client.get('/')
    assert b'Fast Check-In' in r.data


@_patch_log_action
def test_technician_sees_quick_actions_on_ticket():
    """Technician sees Quick Actions on ticket detail."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    r = client.get(f'/tickets/{ticket_id}')
    assert b'Quick Actions' in r.data


@_patch_log_action
def test_readonly_no_quick_actions_on_ticket():
    """Read Only does not see Quick Actions on ticket detail."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    r = client.get(f'/tickets/{ticket_id}')
    assert b'Quick Actions' not in r.data


@_patch_log_action
def test_readonly_no_new_ticket_button_on_list():
    """Read Only does not see New Ticket button on ticket list."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    r = client.get('/tickets/')
    assert b'+ New Ticket' not in r.data


@_patch_log_action
def test_admin_sees_new_ticket_button_on_list():
    """Admin sees New Ticket button on ticket list."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    _login(client)

    r = client.get('/tickets/')
    assert b'+ New Ticket' in r.data


# ─── Unauthenticated access tests ───────────────────────────


@_patch_log_action
def test_unauthenticated_redirected_from_settings():
    """Unauthenticated users get redirected from settings."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    r = client.get('/settings/')
    assert r.status_code == 302
    assert '/auth/login' in r.headers.get('Location', '')


@_patch_log_action
def test_unauthenticated_redirected_from_tickets_new():
    """Unauthenticated users get redirected from ticket creation."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    client = app.test_client()
    r = client.get('/tickets/new')
    assert r.status_code == 302
    assert '/auth/login' in r.headers.get('Location', '')


# ─── Role constants tests ───────────────────────────────────


def test_role_constants_defined():
    """All 7 role constants are defined."""
    assert ROLE_SUPER_ADMIN == "Super Admin"
    assert ROLE_ADMIN == "Admin"
    assert ROLE_MANAGER == "Manager"
    assert ROLE_FRONT_DESK == "Front Desk"
    assert ROLE_TECHNICIAN == "Technician"
    assert ROLE_INVENTORY == "Inventory"
    assert ROLE_READ_ONLY == "Read Only"


# ─── Quick-note route protection test ───────────────────────


@_patch_log_action
def test_quick_note_blocked_for_readonly():
    """Quick note blocked for Read Only."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/quick-note', data={
        'csrf_token': csrf, 'content': 'Test note',
    })
    assert r.status_code == 403


@_patch_log_action
def test_quick_note_allowed_for_technician():
    """Quick note allowed for Technician."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/quick-note', data={
        'csrf_token': csrf, 'content': 'Bench note from tech',
    })
    assert r.status_code == 302


# ─── Generate message route protection ──────────────────────


@_patch_log_action
def test_generate_message_blocked_for_readonly():
    """Generate message blocked for Read Only."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Read Only", "ro@test.com")
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client, 'ro@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/generate-message',
                    json={'template_key': 'received', 'csrf_token': csrf},
                    headers={'X-CSRFToken': csrf})
    assert r.status_code == 403


# ─── Consume reservation route protection ───────────────────


@_patch_log_action
def test_consume_reservation_blocked_for_frontdesk():
    """Consume reservation blocked for Front Desk (needs workshop)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Front Desk", "fd@test.com")
        ticket_id = _setup_ticket(app)
        fake_reservation_id = str(uuid.uuid4())

    client = app.test_client()
    _login(client, 'fd@test.com', 'test1234')

    page = client.get(f'/tickets/{ticket_id}')
    csrf = _csrf(page.data)

    r = client.post(f'/tickets/{ticket_id}/consume-reservation/{fake_reservation_id}', data={
        'csrf_token': csrf,
    })
    assert r.status_code == 403


# ─── Settings POST routes protection ────────────────────────


@_patch_log_action
def test_settings_create_branch_blocked_for_manager():
    """Create branch blocked for Manager (needs admin)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Manager", "mgr@test.com")

    client = app.test_client()
    _login(client, 'mgr@test.com', 'test1234')

    csrf = _get_csrf(client)

    r = client.post('/settings/branches', data={
        'csrf_token': csrf, 'code': 'TST', 'name': 'Test Branch',
    })
    assert r.status_code == 403


# ─── Inventory create-json route protection ──────────────────


@_patch_log_action
def test_create_part_json_blocked_for_technician():
    """Create part JSON blocked for Technician (needs inventory staff)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Technician", "tech@test.com")

    client = app.test_client()
    _login(client, 'tech@test.com', 'test1234')

    csrf = _get_csrf(client)

    r = client.post('/inventory/parts/create-json',
                    json={'sku': 'TST-001', 'name': 'Test Part'},
                    headers={'X-CSRFToken': csrf})
    assert r.status_code == 403


@_patch_log_action
def test_create_part_json_allowed_for_inventory():
    """Create part JSON allowed for Inventory role."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        _create_user_with_role("Inventory", "inv@test.com")

    client = app.test_client()
    _login(client, 'inv@test.com', 'test1234')

    csrf = _get_csrf(client)

    r = client.post('/inventory/parts/create-json',
                    json={'sku': 'TST-001', 'name': 'Test Part'},
                    headers={'X-CSRFToken': csrf})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


# ─── Regression: admin can still do everything ──────────────


@_patch_log_action
def test_admin_can_access_all_protected_routes():
    """Admin user can access settings, create tickets, manage inventory."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        ticket_id = _setup_ticket(app)

    client = app.test_client()
    _login(client)

    # Settings
    assert client.get('/settings/').status_code == 200
    # Create ticket form
    assert client.get('/tickets/new').status_code == 200
    # Inventory new part form
    assert client.get('/inventory/parts/new').status_code == 200
    # Ticket detail
    assert client.get(f'/tickets/{ticket_id}').status_code == 200
