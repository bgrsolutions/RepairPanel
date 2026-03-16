"""Phase 8 — Workshop Operations & Bench Board tests.

Covers:
- Bench board loads and displays correct columns
- Workflow status transitions (valid + invalid)
- Blocker detection (quote, parts, checklist, SLA)
- Technician assignment (quick-assign AJAX)
- Overdue detection
- Dashboard workshop metrics
- Ticket detail workflow panel
"""
import re
import uuid
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Customer, Device, Diagnostic, IntakeSubmission,
    IntakeDisclaimerAcceptance, PartOrder, PortalToken, Quote, RepairChecklist,
    Role, StockMovement, StockReservation, StockLayer, Supplier, Ticket, TicketNote, User,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, Part, PartCategory
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.models import StockLocation, StockLevel
from app.services.seed_service import seed_phase1_data
from app.services.workflow_service import (
    Blocker, allowed_transitions, detect_blockers, is_valid_transition,
    next_recommended_action, workshop_metrics,
)
from app.utils.ticketing import is_ticket_overdue


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
        AppSetting.__table__,
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
        'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token,
    }, follow_redirects=False)
    assert r.status_code == 302


def _setup(monkeypatch):
    """Create app with seeded data and return (app, ids_dict)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Workshop Customer', phone='+34555000000',
            email='workshop@test.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer_id=customer.id, category='phones',
            brand='Samsung', model='S24', serial_number='WS-SN-001',
        )
        db.session.add(device)
        db.session.flush()
        ids = {
            'branch_id': branch.id,
            'customer_id': customer.id,
            'device_id': device.id,
        }
        db.session.commit()
    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    return app, ids


# ──────────────────────────────────────────────────
# Phase 8B: Workflow Transitions (unit tests, no DB)
# ──────────────────────────────────────────────────

class TestWorkflowTransitions:
    def test_valid_transitions_from_unassigned(self):
        assert is_valid_transition('unassigned', 'assigned')
        assert is_valid_transition('unassigned', 'awaiting_diagnostics')
        assert is_valid_transition('unassigned', 'cancelled')

    def test_invalid_transition_from_unassigned(self):
        assert not is_valid_transition('unassigned', 'completed')
        assert not is_valid_transition('unassigned', 'ready_for_collection')
        assert not is_valid_transition('unassigned', 'in_repair')

    def test_valid_repair_to_testing(self):
        assert is_valid_transition('in_repair', 'testing_qa')

    def test_valid_testing_to_ready(self):
        assert is_valid_transition('testing_qa', 'ready_for_collection')

    def test_valid_ready_to_completed(self):
        assert is_valid_transition('ready_for_collection', 'completed')

    def test_invalid_backwards_transition(self):
        assert not is_valid_transition('completed', 'in_repair')
        assert not is_valid_transition('testing_qa', 'unassigned')

    def test_archived_has_no_transitions(self):
        assert allowed_transitions('archived') == []

    def test_allowed_transitions_returns_sorted_list(self):
        result = allowed_transitions('in_repair')
        assert isinstance(result, list)
        assert 'testing_qa' in result
        assert 'awaiting_parts' in result


# ──────────────────────────────────────────────────
# Phase 8C: Blocker Detection
# ──────────────────────────────────────────────────

def test_no_blockers_on_closed_ticket(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BLK-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='completed', customer_status='Completed',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        blockers = detect_blockers(ticket)
        assert blockers == []


def test_sla_blocker_on_overdue(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BLK-002', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=2),
        )
        db.session.add(ticket)
        db.session.commit()
        blockers = detect_blockers(ticket, sla_days=5)
        kinds = [b.kind for b in blockers]
        assert 'sla' in kinds


def test_quote_blocker_when_sent(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BLK-003', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='awaiting_quote_approval',
            customer_status='Waiting', priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        quote = Quote(
            ticket_id=ticket.id, version=1, status='sent',
            currency='EUR', language='en',
        )
        db.session.add(quote)
        db.session.commit()
        blockers = detect_blockers(ticket)
        kinds = [b.kind for b in blockers]
        assert 'quote' in kinds


def test_parts_blocker_on_open_order(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        supplier = Supplier(name='Test Supplier', email='s@test.com')
        db.session.add(supplier)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-BLK-004', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='awaiting_parts',
            customer_status='Waiting Parts', priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        order = PartOrder(
            ticket_id=ticket.id, supplier_id=supplier.id,
            branch_id=ids['branch_id'], reference='PO-TEST-001',
            status='ordered',
            estimated_arrival_at=datetime.utcnow() + timedelta(days=2),
        )
        db.session.add(order)
        db.session.commit()
        blockers = detect_blockers(ticket)
        kinds = [b.kind for b in blockers]
        assert 'parts' in kinds


def test_parts_overdue_blocker(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        supplier = Supplier(name='Test Supplier 2', email='s2@test.com')
        db.session.add(supplier)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-BLK-005', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='awaiting_parts',
            customer_status='Waiting Parts', priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        order = PartOrder(
            ticket_id=ticket.id, supplier_id=supplier.id,
            branch_id=ids['branch_id'], reference='PO-TEST-002',
            status='ordered',
            estimated_arrival_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(order)
        db.session.commit()
        blockers = detect_blockers(ticket)
        labels = [b.label for b in blockers]
        assert 'PARTS OVERDUE' in labels


def test_checklist_blocker_on_testing(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BLK-006', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='testing_qa', customer_status='Testing',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        checklist = RepairChecklist(
            ticket_id=ticket.id, checklist_type='post_repair',
            device_category='phones',
        )
        db.session.add(checklist)
        db.session.flush()
        item = ChecklistItem(
            checklist_id=checklist.id, position=1,
            label='Test screen', is_checked=False,
        )
        db.session.add(item)
        db.session.commit()
        blockers = detect_blockers(ticket)
        kinds = [b.kind for b in blockers]
        assert 'checklist' in kinds


# ──────────────────────────────────────────────────
# Phase 8A: Bench Board
# ──────────────────────────────────────────────────

def test_bench_board_loads(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BB-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() + timedelta(days=3),
        )
        db.session.add(ticket)
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/board')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Repair Bench Board' in html
    assert 'Awaiting Diagnosis' in html
    assert 'Ready For Repair' in html
    assert 'Testing / QA' in html
    assert 'Ready For Collection' in html
    assert 'HQ-BB-001' in html


def test_bench_board_shows_blocker_badges(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BB-002', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='urgent',
            sla_target_at=datetime.utcnow() - timedelta(days=2),
        )
        db.session.add(ticket)
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/board')
    html = resp.data.decode()
    assert 'OVERDUE' in html


def test_bench_board_filters_by_technician(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        tech = User.query.filter_by(email='admin@ironcore.com').first()
        ticket = Ticket(
            ticket_number='HQ-BB-003', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal', assigned_technician_id=tech.id,
        )
        db.session.add(ticket)
        db.session.commit()
        tech_id = str(tech.id)

    client = app.test_client()
    _login(client)
    resp = client.get(f'/tickets/board?technician_id={tech_id}')
    assert 'HQ-BB-003' in resp.data.decode()
    fake_id = str(uuid.uuid4())
    resp = client.get(f'/tickets/board?technician_id={fake_id}')
    assert 'HQ-BB-003' not in resp.data.decode()


def test_bench_board_overdue_filter(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        t1 = Ticket(
            ticket_number='HQ-BB-OD1', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=2),
        )
        t2 = Ticket(
            ticket_number='HQ-BB-OD2', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add_all([t1, t2])
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/board?only_overdue=1')
    html = resp.data.decode()
    assert 'HQ-BB-OD1' in html
    assert 'HQ-BB-OD2' not in html


def test_bench_board_excludes_closed(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-BB-CL1', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='completed', customer_status='Completed',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/board')
    assert 'HQ-BB-CL1' not in resp.data.decode()


# ──────────────────────────────────────────────────
# Phase 8D: Technician Quick-Assign
# ──────────────────────────────────────────────────

def test_quick_assign_technician(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        tech = User.query.filter_by(email='admin@ironcore.com').first()
        ticket = Ticket(
            ticket_number='HQ-QA-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='unassigned', customer_status='Received',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = str(ticket.id)
        ticket_uuid = ticket.id
        tech_id = str(tech.id)

    client = app.test_client()
    _login(client)
    token = _csrf(client.get(f'/tickets/{ticket_id}').data)
    resp = client.post(f'/tickets/{ticket_id}/quick-assign', data={
        'technician_id': tech_id, 'csrf_token': token,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True

    with app.app_context():
        t = db.session.get(Ticket, ticket_uuid)
        assert str(t.assigned_technician_id) == tech_id


# ──────────────────────────────────────────────────
# Phase 8F: Overdue Detection
# ──────────────────────────────────────────────────

def test_overdue_detection_respects_sla(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        t1 = Ticket(
            ticket_number='HQ-OD-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=1),
        )
        t2 = Ticket(
            ticket_number='HQ-OD-002', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add_all([t1, t2])
        db.session.commit()
        assert is_ticket_overdue(t1) is True
        assert is_ticket_overdue(t2) is False


def test_overdue_not_flagged_for_closed(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        t = Ticket(
            ticket_number='HQ-OD-003', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='completed', customer_status='Completed',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=10),
        )
        db.session.add(t)
        db.session.commit()
        assert is_ticket_overdue(t) is False


# ──────────────────────────────────────────────────
# Phase 8G/I: Dashboard and Metrics
# ──────────────────────────────────────────────────

def test_dashboard_shows_workshop_metrics(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        tickets = [
            Ticket(ticket_number='HQ-DM-001', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='awaiting_diagnostics', customer_status='Received', priority='normal'),
            Ticket(ticket_number='HQ-DM-002', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='in_repair', customer_status='In Repair', priority='normal'),
            Ticket(ticket_number='HQ-DM-003', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='ready_for_collection', customer_status='Ready', priority='normal'),
        ]
        db.session.add_all(tickets)
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/')
    html = resp.data.decode()
    assert resp.status_code == 200
    assert 'In Diagnosis' in html
    assert 'In Repair' in html


def test_dashboard_overdue_widget(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-DM-OD1', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=3),
        )
        db.session.add(ticket)
        db.session.commit()

    client = app.test_client()
    _login(client)
    resp = client.get('/')
    html = resp.data.decode()
    assert 'Overdue Tickets' in html
    assert 'HQ-DM-OD1' in html


def test_workshop_metrics_counts(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        tickets = [
            Ticket(ticket_number='HQ-WM-001', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='awaiting_diagnostics', customer_status='R', priority='normal'),
            Ticket(ticket_number='HQ-WM-002', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='in_repair', customer_status='R', priority='normal'),
            Ticket(ticket_number='HQ-WM-003', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='testing_qa', customer_status='R', priority='normal'),
            Ticket(ticket_number='HQ-WM-004', branch_id=ids['branch_id'],
                   customer_id=ids['customer_id'], device_id=ids['device_id'],
                   internal_status='completed', customer_status='Done', priority='normal'),
        ]
        db.session.add_all(tickets)
        db.session.commit()
        m = workshop_metrics(tickets)
        assert m['in_diagnosis'] == 1
        assert m['in_repair'] == 1
        assert m['in_testing'] == 1
        assert m['ready_for_collection'] == 0


# ──────────────────────────────────────────────────
# Phase 8H: Ticket Detail Workflow Panel
# ──────────────────────────────────────────────────

def test_ticket_detail_shows_workflow_panel(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-WP-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='in_repair', customer_status='In Repair',
            priority='normal',
            sla_target_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = str(ticket.id)

    client = app.test_client()
    _login(client)
    resp = client.get(f'/tickets/{ticket_id}')
    html = resp.data.decode()
    assert resp.status_code == 200
    assert 'Workflow Status' in html
    assert 'Next Recommended Action' in html
    assert 'OVERDUE' in html


def test_next_action_recommends_correctly(monkeypatch):
    """Unit test: next_recommended_action returns sensible advice."""
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-NA-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='awaiting_parts', customer_status='Waiting',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        parts_blocker = Blocker('parts', 'WAITING PARTS', 'Part order PO-001 not yet received')
        action = next_recommended_action(ticket, [parts_blocker])
        assert 'parts' in action.lower() or 'PO-001' in action


# ──────────────────────────────────────────────────
# Phase 8B: Status Transition Enforcement via Route
# ──────────────────────────────────────────────────

def test_invalid_status_transition_rejected(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-TR-001', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='unassigned', customer_status='Received',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = str(ticket.id)
        ticket_uuid = ticket.id

    client = app.test_client()
    _login(client)
    token = _csrf(client.get(f'/tickets/{ticket_id}').data)
    resp = client.post(f'/tickets/{ticket_id}/status', data={
        'internal_status': 'completed', 'csrf_token': token,
    }, follow_redirects=True)
    html = resp.data.decode()
    assert 'Invalid status transition' in html

    with app.app_context():
        t = db.session.get(Ticket, ticket_uuid)
        assert t.internal_status == 'unassigned'


def test_valid_status_transition_accepted(monkeypatch):
    app, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = Ticket(
            ticket_number='HQ-TR-002', branch_id=ids['branch_id'],
            customer_id=ids['customer_id'], device_id=ids['device_id'],
            internal_status='unassigned', customer_status='Received',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = str(ticket.id)
        ticket_uuid = ticket.id

    client = app.test_client()
    _login(client)
    token = _csrf(client.get(f'/tickets/{ticket_id}').data)
    resp = client.post(f'/tickets/{ticket_id}/status', data={
        'internal_status': 'awaiting_diagnostics', 'csrf_token': token,
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        t = db.session.get(Ticket, ticket_uuid)
        assert t.internal_status == 'awaiting_diagnostics'
