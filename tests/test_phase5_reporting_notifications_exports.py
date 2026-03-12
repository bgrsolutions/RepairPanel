import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    ExportQueueItem,
    IntakeSubmission,
    NotificationDelivery,
    NotificationEvent,
    NotificationTemplate,
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
from app.services.export_service import build_ticket_export_payload
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
        NotificationTemplate.__table__, NotificationEvent.__table__, NotificationDelivery.__table__, ExportQueueItem.__table__,
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


def test_phase5_foundations(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='P5 Cust', phone='+34002', email='p5@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='laptops', brand='Lenovo', model='T14', serial_number='P5', imei=None)
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260312-9000', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='Awaiting Quote Approval', customer_status='Waiting quote', priority='normal')
        db.session.add(ticket)
        db.session.flush()
        quote = Quote(ticket_id=ticket.id, version=1, status='sent', currency='EUR', language='en')
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Standard', position=1)
        db.session.add(option)
        db.session.flush()
        db.session.add(QuoteLine(option_id=option.id, line_type='labour', description='Bench labour', quantity=1, unit_price=25))
        db.session.commit()

        payload = build_ticket_export_payload(ticket)
        assert payload['ticket']['ticket_number'] == 'HQ-20260312-9000'
        assert payload['payment_handled_externally'] is True

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    assert client.get('/reports/').status_code == 200
    assert client.get('/notifications/templates').status_code == 200
    assert client.get('/notifications/events').status_code == 200
    assert client.get('/settings/').status_code == 200
    assert client.get('/settings/portal').status_code == 200
    assert client.get('/integrations/exports').status_code == 200

    with app.app_context():
        ticket = Ticket.query.filter_by(ticket_number='HQ-20260312-9000').first()

    queue_resp = client.post(f'/integrations/exports/ticket/{ticket.id}/queue', follow_redirects=False)
    assert queue_resp.status_code == 302

    with app.app_context():
        assert ExportQueueItem.query.filter_by(ticket_id=ticket.id).count() == 1
