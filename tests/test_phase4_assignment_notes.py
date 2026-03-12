import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    IntakeSubmission,
    Part,
    PartOrder,
    PartOrderEvent,
    PartOrderLine,
    Quote,
    QuoteApproval,
    QuoteLine,
    QuoteOption,
    Role,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    Supplier,
    Ticket,
    TicketNote,
    User,
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
    assert m is not None
    return m.group(1).decode()


def _login(client):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token}, follow_redirects=False)
    assert r.status_code == 302


def test_assignment_and_notes_flow(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        tech_role = Role.query.filter_by(name='Technician').first()
        if tech_role is None:
            tech_role = Role(name='Technician', description='Tech')
            db.session.add(tech_role)
            db.session.flush()

        branch = Branch.query.filter_by(code='HQ').first()
        tech = User(full_name='Tech One', email='tech1@example.com', preferred_language='en', is_active=True, default_branch=branch)
        tech.set_password('admin1234')
        tech.roles.append(tech_role)
        tech.branches.append(branch)
        db.session.add(tech)

        customer = Customer(full_name='Assign Customer', phone='+3411111111', email='assign@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Apple', model='iPhone', serial_number='SNA', imei='111')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260312-3000', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='New', customer_status='Received', priority='normal')
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id
        tech_id = tech.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    detail = client.get(f'/tickets/{ticket_id}')
    token = _csrf(detail.data)
    assign_resp = client.post(f'/tickets/{ticket_id}/assign', data={'csrf_token': token, 'assigned_technician_id': str(tech_id)}, follow_redirects=False)
    assert assign_resp.status_code == 302

    detail2 = client.get(f'/tickets/{ticket_id}')
    token2 = _csrf(detail2.data)
    note_resp = client.post(f'/tickets/{ticket_id}/notes', data={'csrf_token': token2, 'note_type': 'internal', 'content': 'Initial bench note'}, follow_redirects=False)
    assert note_resp.status_code == 302

    with app.app_context():
        t = db.session.get(Ticket, ticket_id)
        assert str(t.assigned_technician_id) == str(tech_id)
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        assert len(notes) == 1
        assert notes[0].note_type == 'internal'
