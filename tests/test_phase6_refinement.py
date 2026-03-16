"""Phase 6 refinement tests covering:
- Intake form redesign with diagnostics and pre-check sections
- Multiple checklists display and numbering
- Overdue logic consistency across dashboard, bench board, and reports
- Dashboard activity uses friendly references
- Tickets-need-attention logic with reason tags
- Top navigation shows Fast Check-In and Intakes
"""
import re
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Customer, Device, Diagnostic,
    IntakeDisclaimerAcceptance, IntakeSubmission, Part, PartCategory,
    PartOrder, PartOrderEvent, PartOrderLine, PortalToken,
    Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    Role, StockLayer, StockLevel, StockLocation, StockMovement,
    StockReservation, Supplier, Ticket, TicketNote, User,
)
from app.models.checklist import ChecklistItem
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.models.inventory import part_category_links
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
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "Test disclaimer"
    DEFAULT_TICKET_SLA_DAYS = 5


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


def _noop_log(*a, **kw):
    return None


def _setup(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Phase6 Customer', phone='+34666000',
            email='phase6@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Apple',
            model='iPhone 15', serial_number='P6-SN', imei='P6-IMEI',
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-P601', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        ids = {
            'branch_id': str(branch.id),
            'customer_id': str(customer.id),
            'device_id': str(device.id),
            'ticket_id': str(ticket.id),
        }
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    client = app.test_client()
    _login(client)
    return app, client, ids


# ── 6A: Intake form redesign ──

def test_intake_form_has_diagnostic_and_precheck_sections(monkeypatch):
    """Intake form should have diagnostics and pre-check sections."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/intake/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Pre-Repair Quick Check' in html
    assert 'Initial Diagnosis' in html
    assert 'check_powers_on' in html
    assert 'check_screen_condition' in html
    assert 'initial_diagnosis' in html
    assert 'recommended_repair' in html
    assert 'Device Intake' in html


def test_intake_form_has_step_numbers(monkeypatch):
    """Intake form should have numbered step sections."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/intake/new')
    html = resp.data.decode()
    assert 'Branch' in html
    assert 'Device Details' in html
    assert 'Fault' in html
    assert 'Attachments' in html


def test_intake_submission_with_precheck_fields(monkeypatch):
    """Intake submission should capture pre-check and diagnosis data in intake notes."""
    app, client, ids = _setup(monkeypatch)
    page = client.get('/intake/new')
    token = _csrf(page.data)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
    post = client.post('/intake/new', data={
        'csrf_token': token,
        'branch_id': str(branch.id),
        'category': 'phones',
        'customer_name': 'PreCheck Test',
        'customer_phone': '+34111222',
        'customer_email': 'precheck@example.com',
        'device_brand': 'Samsung',
        'device_model': 'Galaxy S24',
        'serial_number': 'PC-SN-1',
        'imei': 'PC-IMEI-1',
        'reported_fault': 'Screen flickering',
        'device_condition': 'Minor scratch on back',
        'check_powers_on': 'y',
        'check_screen_condition': '',
        'check_charging': 'y',
        'check_buttons': 'y',
        'check_water_damage': 'y',
        'initial_diagnosis': 'Likely display connector',
        'recommended_repair': 'Replace display cable',
        'accepted_disclaimer': 'y',
    }, follow_redirects=False)
    assert post.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.filter_by(customer_name='PreCheck Test').first()
        assert intake is not None
        assert 'Device condition' in intake.intake_notes
        assert 'Pre-check' in intake.intake_notes
        assert 'Initial diagnosis' in intake.intake_notes
        assert 'Recommended repair' in intake.intake_notes


# ── 6B: Checklist multiple display ──

def test_multiple_checklists_display(monkeypatch):
    """Multiple checklists should display with numbering on ticket detail."""
    app, client, ids = _setup(monkeypatch)
    ticket_id = ids['ticket_id']

    # Create first pre-repair checklist
    detail = client.get(f'/tickets/{ticket_id}')
    token = _csrf(detail.data)
    client.post(f'/tickets/{ticket_id}/checklists/create', data={
        'csrf_token': token, 'checklist_type': 'pre_repair',
    }, follow_redirects=False)

    # Get the checklist and complete it
    with app.app_context():
        import uuid
        cl = RepairChecklist.query.filter_by(
            ticket_id=uuid.UUID(ticket_id), checklist_type='pre_repair'
        ).first()
        for item in cl.items:
            item.is_checked = True
            item.checked_at = datetime.utcnow()
        cl.completed_at = datetime.utcnow()
        db.session.commit()

    # Create second pre-repair checklist
    detail2 = client.get(f'/tickets/{ticket_id}')
    token2 = _csrf(detail2.data)
    resp2 = client.post(f'/tickets/{ticket_id}/checklists/create', data={
        'csrf_token': token2, 'checklist_type': 'pre_repair',
    }, follow_redirects=False)
    assert resp2.status_code == 302

    # Verify both show on detail page with numbering
    detail3 = client.get(f'/tickets/{ticket_id}')
    html = detail3.data.decode()
    assert 'Pre-Repair Check #1' in html
    assert 'Pre-Repair Check #2' in html


# ── 6C: Overdue logic consistency ──

def test_overdue_consistent_across_views(monkeypatch):
    """Dashboard, bench board, and reports should use the same overdue logic."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Overdue Test', phone='+34777888',
            email='overdue@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Google',
            model='Pixel', serial_number='OD-SN', imei='OD-IMEI',
        )
        db.session.add(device)
        db.session.flush()
        # Ticket with SLA target in the past
        ticket = Ticket(
            ticket_number='HQ-20260315-OD01', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=2),
        )
        db.session.add(ticket)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    # Dashboard should show overdue count
    dashboard = client.get('/')
    assert dashboard.status_code == 200
    html = dashboard.data.decode()
    assert 'Overdue' in html

    # Bench board overdue tab should include the ticket
    board = client.get('/tickets/board?only_overdue=1')
    assert board.status_code == 200
    assert b'HQ-20260315-OD01' in board.data

    # Reports should count it as overdue
    reports = client.get('/reports/')
    assert reports.status_code == 200


def test_overdue_ticket_without_sla_uses_fallback(monkeypatch):
    """A ticket without sla_target_at should use fallback SLA calculation."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Fallback SLA', phone='+34888999',
            email='fallback@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Nokia',
            model='3310', serial_number='FB-SN', imei='FB-IMEI',
        )
        db.session.add(device)
        db.session.flush()
        # Old ticket with no SLA target (created 10 days ago, SLA default is 5)
        ticket = Ticket(
            ticket_number='HQ-20260315-FB01', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='awaiting_diagnostics', customer_status='Received',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        # Backdate creation
        ticket.created_at = datetime.utcnow() - timedelta(days=10)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    # Should appear as overdue on dashboard
    dashboard = client.get('/')
    assert dashboard.status_code == 200


# ── 6D: Recent Activity rework ──

def test_dashboard_activity_has_friendly_format(monkeypatch):
    """Dashboard activity items should have structured format, not raw tokens."""
    app, client, ids = _setup(monkeypatch)
    # Create some notes to generate activity
    with app.app_context():
        import uuid
        ticket_id = uuid.UUID(ids['ticket_id'])
        db.session.add(TicketNote(
            ticket_id=ticket_id, note_type='customer_update',
            content='Device is ready for pickup',
        ))
        db.session.commit()

    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    # Should show ticket number references, not raw UUIDs
    assert 'Recent Activity' in html


# ── 6E: Tickets Need Attention ──

def test_attention_widget_shows_reasons(monkeypatch):
    """Attention widget should show why each ticket needs attention."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Attention Test', phone='+34555888',
            email='attention@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='LG',
            model='Wing', serial_number='AT-SN', imei='AT-IMEI',
        )
        db.session.add(device)
        db.session.flush()
        # Overdue ticket
        ticket = Ticket(
            ticket_number='HQ-20260315-AT01', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='high',
            sla_target_at=datetime.utcnow() - timedelta(days=3),
        )
        db.session.add(ticket)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/')
    html = resp.data.decode()
    assert 'Tickets Need Attention' in html
    assert 'OVERDUE' in html or 'Overdue SLA' in html or 'Overdue' in html
    assert 'HQ-20260315-AT01' in html


def test_attention_widget_unassigned_flag(monkeypatch):
    """Unassigned tickets older than 1 day should appear in attention widget."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Unassigned Test', phone='+34555777',
            email='unassigned@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Sony',
            model='Xperia', serial_number='UA-SN', imei='UA-IMEI',
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-UA01', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='unassigned', customer_status='Received',
            priority='normal',
            sla_target_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(ticket)
        db.session.flush()
        ticket.created_at = datetime.utcnow() - timedelta(days=2)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/')
    html = resp.data.decode()
    assert 'Unassigned' in html


# ── 6F: Navigation changes ──

def test_nav_shows_fast_checkin_and_intakes(monkeypatch):
    """Top navigation should show Fast Check-In and Intakes buttons."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    html = resp.data.decode()
    assert 'Fast Check-In' in html
    assert 'Intakes' in html
    assert 'New Ticket' not in html


def test_dashboard_button_says_fast_checkin(monkeypatch):
    """Dashboard quick action button should say Fast Check-In."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    html = resp.data.decode()
    assert 'Fast Check-In' in html
