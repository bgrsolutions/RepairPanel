import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Customer, Device, Diagnostic, IntakeSubmission, Part, PartOrder, PartOrderEvent, PartOrderLine,
    Quote, QuoteApproval, QuoteLine, QuoteOption, Role, StockLevel, StockLocation, StockMovement, StockReservation,
    Supplier, Ticket, TicketNote, User,
)
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
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
    DEFAULT_TICKET_SLA_DAYS = 4


def _create_tables():
    tables = [
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__, role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__, Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__, Supplier.__table__, Part.__table__, StockLocation.__table__,
        StockLevel.__table__, StockMovement.__table__, StockReservation.__table__, PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
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
    r = client.post('/auth/login', data={'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token}, follow_redirects=False)
    assert r.status_code == 302


def test_refinement_pass_a_workflows(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Flow Customer', phone='+34001', email='flow@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Apple', model='iPhone 13', serial_number='FLOW-1', imei='123456')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260312-7000', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='unassigned', customer_status='Received', priority='normal')
        db.session.add(ticket)

        part = Part(sku='LCD-001', name='LCD Screen', barcode='LCDBAR', supplier_sku='SUP-LCD', is_active=True)
        db.session.add(part)
        db.session.commit()
        ticket_id = ticket.id
        customer_id = customer.id
        device_id = device.id
        part_id = part.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    # User management create technician account
    page = client.get('/users/new')
    token = _csrf(page.data)
    with app.app_context():
        tech_role = Role.query.filter_by(name='Technician').first()
        branch = Branch.query.filter_by(code='HQ').first()
    create_resp = client.post('/users/new', data={
        'csrf_token': token,
        'full_name': 'Workflow Tech',
        'email': 'workflow-tech@example.com',
        'password': 'strongpass1',
        'preferred_language': 'en',
        'role_ids': [str(tech_role.id)],
        'branch_ids': [str(branch.id)],
        'is_active': 'y',
    }, follow_redirects=False)
    assert create_resp.status_code == 302

    # Assign and update status
    detail = client.get(f'/tickets/{ticket_id}')
    token2 = _csrf(detail.data)
    with app.app_context():
        tech = User.query.filter_by(email='workflow-tech@example.com').first()
    assign_resp = client.post(f'/tickets/{ticket_id}/assign', data={'csrf_token': token2, 'assigned_technician_id': str(tech.id)}, follow_redirects=False)
    assert assign_resp.status_code == 302

    detail2 = client.get(f'/tickets/{ticket_id}')
    token3 = _csrf(detail2.data)
    status_resp = client.post(f'/tickets/{ticket_id}/status', data={'csrf_token': token3, 'internal_status': 'in_repair'}, follow_redirects=False)
    assert status_resp.status_code == 302

    # Customer device filtering endpoint
    devices_resp = client.get(f'/tickets/customer/{customer_id}/devices')
    assert devices_resp.status_code == 200
    payload = devices_resp.get_json()
    assert len(payload) == 1
    assert payload[0]['id'] == str(device_id)


    new_page = client.get('/tickets/new')
    token_new = _csrf(new_page.data)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
    create_ticket_resp = client.post('/tickets/new', data={
        'csrf_token': token_new,
        'branch_id': str(branch.id),
        'customer_id': str(customer_id),
        'device_id': str(device_id),
        'priority': 'normal',
    }, follow_redirects=False)
    assert create_ticket_resp.status_code == 302

    # Parts search and deactivate
    parts_resp = client.get('/inventory/parts?q=LCD')
    assert parts_resp.status_code == 200
    assert 'LCD Screen' in parts_resp.data.decode('utf-8')

    toggle_resp = client.post(f'/inventory/parts/{part_id}/toggle-active', data={}, follow_redirects=False)
    assert toggle_resp.status_code == 302

    with app.app_context():
        refreshed_ticket = db.session.get(Ticket, ticket_id)
        assert str(refreshed_ticket.assigned_technician_id) == str(tech.id)
        assert refreshed_ticket.internal_status == 'in_repair'
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        assert len(notes) >= 2

        created = Ticket.query.filter(Ticket.ticket_number != 'HQ-20260312-7000').order_by(Ticket.created_at.desc()).first()
        assert created.sla_target_at is not None

        refreshed_part = db.session.get(Part, part_id)
        assert refreshed_part.is_active is False
