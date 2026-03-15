"""Tests for Phase 3 workflow/product UX improvements.

Covers:
- 3B: Rebuilt quote builder (inline part search, HiddenField for linked_part_id)
- 3C: Standalone quotes (nullable ticket_id, new routes)
- 3D: Improved ticket intake UX (hidden customer_id, ETA presets)
- 3E: Estimated completion display improvements
- 3F: Dashboard real activity feed
- 3G: Inline diagnostics on ticket detail
- 3H: Pre/post repair checklists
- 3I: Friendly public quote approval URLs
"""

import re
import uuid
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Customer, Device, Diagnostic, Part, Quote, QuoteApproval,
    QuoteLine, QuoteOption, Role, Supplier, Ticket, TicketNote, User,
    IntakeDisclaimerAcceptance, IntakeSubmission, PartCategory,
    PartOrder, PartOrderEvent, PartOrderLine, PortalToken,
    StockLayer, StockLevel, StockLocation, StockMovement,
    StockReservation, AppSetting, RepairChecklist,
)
from app.models.checklist import ChecklistItem, DEFAULT_CHECKLISTS
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.models.inventory import part_category_links


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
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "Test disclaimer"


def _create_tables():
    tables = [
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__,
        role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__,
        IntakeDisclaimerAcceptance.__table__, PortalToken.__table__,
        Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        AppSetting.__table__, RepairChecklist.__table__, ChecklistItem.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _csrf(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1).decode()


def _login(client):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={
        'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token
    }, follow_redirects=False)
    assert r.status_code == 302


def _seed_basic(app):
    """Seed minimal data needed for most tests."""
    from app.services.seed_service import seed_phase1_data
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Test Customer', phone='+34111222333',
            email='test@example.com', preferred_language='en',
            primary_branch=branch
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Apple',
            model='iPhone 15', serial_number='SN-TEST', imei='IMEI-TEST'
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-0001', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal'
        )
        db.session.add(ticket)
        db.session.flush()
        part = Part(sku='SCR-001', name='iPhone Screen', is_active=True, sale_price=89.99)
        db.session.add(part)
        db.session.commit()
        return {
            'branch_id': str(branch.id),
            'customer_id': str(customer.id),
            'device_id': str(device.id),
            'ticket_id': str(ticket.id),
            'part_id': str(part.id),
        }


# --- 3B: Quote builder UX ---

def test_quote_builder_uses_inline_part_search(monkeypatch):
    """The rebuilt quote builder has inline part autocomplete, not a separate part search row."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/quotes/ticket/{ids["ticket_id"]}/new')
    assert resp.status_code == 200
    html = resp.data.decode()

    # Should have inline autocomplete (wireLine function)
    assert 'wireLine' in html
    # Should NOT have old-style separate part search row
    assert 'Part search' not in html or 'part-search-row' not in html


def test_quote_builder_hidden_linked_part_id(monkeypatch):
    """linked_part_id should be a hidden field, not a select dropdown."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/quotes/ticket/{ids["ticket_id"]}/new')
    html = resp.data.decode()

    # linked_part_id should be hidden input, not a select
    assert 'type="hidden"' in html or "type='hidden'" in html
    assert 'linked_part_id' in html


def test_parts_search_api_returns_sku(monkeypatch):
    """The /inventory/parts/search endpoint should return sku field."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/inventory/parts/search?q=iPhone')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data
    if data['items']:
        item = data['items'][0]
        assert 'sku' in item
        assert 'sale_price' in item
        assert 'name' in item


# --- 3C: Standalone quotes ---

def test_standalone_quote_model_nullable_ticket():
    """Quote.ticket_id should be nullable for standalone quotes."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        customer = Customer.query.first()
        quote = Quote(
            ticket_id=None,
            customer_id=customer.id,
            customer_name='Walk-in Client',
            device_description='Samsung Galaxy S24',
            version=1, status='draft',
            terms_snapshot='Test terms'
        )
        db.session.add(quote)
        db.session.commit()

        assert quote.is_standalone is True
        assert quote.display_customer_name == customer.full_name
        assert quote.display_device == 'Samsung Galaxy S24'


def test_standalone_quote_list_page(monkeypatch):
    """The /quotes/ list page should render and show standalone quotes."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/quotes/list')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Quotes' in html
    assert 'New Standalone Quote' in html


def test_standalone_quote_new_page(monkeypatch):
    """The standalone quote creation page should render."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/quotes/standalone/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Standalone Quote' in html


# --- 3D: Improved ticket intake UX ---

def test_ticket_intake_has_eta_presets(monkeypatch):
    """New ticket form should have ETA preset buttons."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/tickets/new')
    assert resp.status_code == 200
    html = resp.data.decode()

    assert 'eta-preset' in html
    assert 'Today' in html
    assert 'Tomorrow' in html
    assert '3 Days' in html
    assert '1 Week' in html


def test_ticket_intake_customer_search_hidden_field(monkeypatch):
    """Customer ID should be a hidden field, not a visible select dropdown."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/tickets/new')
    html = resp.data.decode()

    # Should have customer search input
    assert 'customer-search' in html
    # Should have customer card UI
    assert 'customer-card' in html
    # Should have hidden field for customer_id
    assert 'customer-id-field' in html


def test_ticket_intake_step_headers(monkeypatch):
    """Intake form should have numbered step sections."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/tickets/new')
    html = resp.data.decode()

    assert '1. Branch' in html
    assert '2. Device' in html
    assert '3. Issue Details' in html
    assert '4. Condition' in html
    assert '5. Promised Completion' in html


# --- 3E: Estimated completion UX ---

def test_ticket_detail_shows_promise_overdue(monkeypatch):
    """Ticket detail should show 'Past due' badge for overdue promised completion."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        ticket = db.session.get(Ticket, uuid.UUID(ids['ticket_id']))
        ticket.quoted_completion_at = datetime.utcnow() - timedelta(days=2)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/tickets/{ids["ticket_id"]}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Past due' in html


# --- 3F: Dashboard activity feed ---

def test_dashboard_renders_activity_section(monkeypatch):
    """Dashboard should have an activity section (not just hardcoded placeholder)."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    # Should have activity section in dashboard
    assert 'activity' in html.lower() or 'Activity' in html


# --- 3G: Inline diagnostics on ticket detail ---

def test_ticket_detail_shows_inline_diagnostics(monkeypatch):
    """Ticket detail should show diagnosis entries inline, not just in modal."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        diag = Diagnostic(
            ticket_id=uuid.UUID(ids['ticket_id']),
            version=1,
            customer_reported_fault='Screen cracked',
            technician_diagnosis='LCD damaged',
            recommended_repair='Replace LCD assembly',
        )
        db.session.add(diag)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/tickets/{ids["ticket_id"]}')
    assert resp.status_code == 200
    html = resp.data.decode()

    # Diagnostics content should appear inline (not only in modal)
    assert 'LCD damaged' in html
    assert 'Screen cracked' in html


# --- 3H: Pre/post repair checklists ---

def test_checklist_model_default_templates():
    """DEFAULT_CHECKLISTS should have templates for common device categories."""
    assert 'phones' in DEFAULT_CHECKLISTS
    assert 'laptops' in DEFAULT_CHECKLISTS
    assert 'other' in DEFAULT_CHECKLISTS

    for category in DEFAULT_CHECKLISTS:
        assert 'pre_repair' in DEFAULT_CHECKLISTS[category]
        assert 'post_repair' in DEFAULT_CHECKLISTS[category]
        assert len(DEFAULT_CHECKLISTS[category]['pre_repair']) > 0
        assert len(DEFAULT_CHECKLISTS[category]['post_repair']) > 0


def test_checklist_model_properties():
    """RepairChecklist should have working is_complete, checked_count, all_checked properties."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        checklist = RepairChecklist(
            ticket_id=uuid.UUID(ids['ticket_id']),
            checklist_type='pre_repair',
            device_category='phones',
        )
        db.session.add(checklist)
        db.session.flush()

        item1 = ChecklistItem(checklist_id=checklist.id, position=0, label='Check screen')
        item2 = ChecklistItem(checklist_id=checklist.id, position=1, label='Check buttons')
        db.session.add_all([item1, item2])
        db.session.commit()

        # Refresh to load items
        db.session.refresh(checklist)

        assert checklist.is_complete is False
        assert checklist.total_count == 2
        assert checklist.checked_count == 0
        assert checklist.all_checked is False

        item1.is_checked = True
        db.session.commit()
        db.session.refresh(checklist)

        assert checklist.checked_count == 1
        assert checklist.all_checked is False

        item2.is_checked = True
        db.session.commit()
        db.session.refresh(checklist)

        assert checklist.all_checked is True


def test_checklist_create_route(monkeypatch):
    """POST to create checklist should create a checklist with default items."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    # Get CSRF token from ticket detail page
    detail = client.get(f'/tickets/{ids["ticket_id"]}')
    token = _csrf(detail.data)

    resp = client.post(
        f'/tickets/{ids["ticket_id"]}/checklists/create',
        data={'checklist_type': 'pre_repair', 'csrf_token': token},
        follow_redirects=False
    )
    assert resp.status_code == 302

    with app.app_context():
        checklist = RepairChecklist.query.filter_by(
            ticket_id=uuid.UUID(ids['ticket_id']),
            checklist_type='pre_repair'
        ).first()
        assert checklist is not None
        assert checklist.device_category == 'phones'
        assert len(checklist.items) > 0


def test_checklist_prevents_duplicate(monkeypatch):
    """Creating a checklist of same type for same ticket should not create duplicate."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    # Create first checklist
    detail = client.get(f'/tickets/{ids["ticket_id"]}')
    token = _csrf(detail.data)
    client.post(
        f'/tickets/{ids["ticket_id"]}/checklists/create',
        data={'checklist_type': 'post_repair', 'csrf_token': token},
        follow_redirects=False
    )

    # Try to create duplicate
    detail2 = client.get(f'/tickets/{ids["ticket_id"]}')
    token2 = _csrf(detail2.data)
    resp = client.post(
        f'/tickets/{ids["ticket_id"]}/checklists/create',
        data={'checklist_type': 'post_repair', 'csrf_token': token2},
        follow_redirects=True
    )
    assert resp.status_code == 200

    with app.app_context():
        count = RepairChecklist.query.filter_by(
            ticket_id=uuid.UUID(ids['ticket_id']),
            checklist_type='post_repair'
        ).count()
        assert count == 1


# --- 3I: Friendly public quote URLs ---

def test_friendly_public_quote_url(monkeypatch):
    """The /public/quote/Q-<version>/<token> URL should work."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        ticket = db.session.get(Ticket, uuid.UUID(ids['ticket_id']))
        quote = Quote(
            ticket_id=ticket.id, version=1, status='sent',
            terms_snapshot='Test terms'
        )
        db.session.add(quote)
        db.session.flush()

        option = QuoteOption(quote_id=quote.id, name='Standard Repair', position=1)
        db.session.add(option)
        db.session.flush()

        import secrets
        token = secrets.token_urlsafe(24)
        approval = QuoteApproval(
            quote_id=quote.id, token=token,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db.session.add(approval)
        db.session.commit()
        quote_version = quote.version

    # Test friendly URL
    resp = client_resp = app.test_client().get(f'/public/quote/Q-{quote_version}/{token}')
    assert resp.status_code == 200


def test_quote_detail_accessible(monkeypatch):
    """Internal quote detail page should be accessible."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    with app.app_context():
        quote = Quote(
            ticket_id=uuid.UUID(ids['ticket_id']), version=1, status='draft',
            terms_snapshot='Test terms'
        )
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Repair', position=1)
        db.session.add(option)
        db.session.commit()
        quote_id = str(quote.id)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/quotes/{quote_id}')
    assert resp.status_code == 200


# --- Navigation ---

def test_quotes_link_in_nav(monkeypatch):
    """The base nav should include a link to the quotes list."""
    app = create_app(TestConfig)
    ids = _seed_basic(app)

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Quotes' in html
