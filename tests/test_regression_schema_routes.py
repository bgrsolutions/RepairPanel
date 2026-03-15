"""Regression tests for schema/migration consistency and critical route availability.

These tests exist to catch the class of bug where:
- Model columns are added but migration is missing
- Routes crash due to schema mismatches
- Template rendering fails because of model/query issues

The key insight: standard tests create tables from the SQLAlchemy model
(which includes all columns), so they never catch cases where a migration
is missing for a new column. These tests validate schema completeness.
"""

import importlib
import os
import re

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


# ── R5.1: Schema/migration completeness ──

def test_migration_covers_all_quote_model_columns():
    """Verify that migration files create/alter all columns defined in the Quote model.

    This test parses migration files to check that every column in the Quote
    model is either created in the initial table or added via alter_column/add_column.
    This catches the exact class of bug where model columns are added without a migration.
    """
    from sqlalchemy import inspect as sa_inspect
    from app.models.quote import Quote

    # Get all column names from the Quote model
    mapper = sa_inspect(Quote)
    model_columns = {col.key for col in mapper.columns}

    # Parse migration files for quotes table operations
    migration_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    migration_columns = set()

    for fname in os.listdir(migration_dir):
        if not fname.endswith('.py'):
            continue
        filepath = os.path.join(migration_dir, fname)
        with open(filepath) as f:
            content = f.read()

        # Find columns in create_table("quotes", ...)
        # Match sa.Column("column_name", ...)
        if '"quotes"' in content or "'quotes'" in content:
            for match in re.finditer(r'sa\.Column\(["\'](\w+)["\']', content):
                migration_columns.add(match.group(1))
            # Also check add_column("quotes", sa.Column("xxx", ...))
            for match in re.finditer(r'add_column\(["\']quotes["\'],\s*sa\.Column\(["\'](\w+)["\']', content):
                migration_columns.add(match.group(1))

    missing = model_columns - migration_columns
    assert not missing, (
        f"Quote model columns missing from migrations: {missing}. "
        f"Model columns: {sorted(model_columns)}. "
        f"Migration columns: {sorted(migration_columns)}"
    )


def test_migration_covers_all_checklist_model_columns():
    """Verify migration files cover RepairChecklist and ChecklistItem columns."""
    from sqlalchemy import inspect as sa_inspect

    migration_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')

    for model_cls, table_name in [
        (RepairChecklist, "repair_checklists"),
        (ChecklistItem, "checklist_items"),
    ]:
        mapper = sa_inspect(model_cls)
        model_columns = {col.key for col in mapper.columns}

        migration_columns = set()
        for fname in os.listdir(migration_dir):
            if not fname.endswith('.py'):
                continue
            filepath = os.path.join(migration_dir, fname)
            with open(filepath) as f:
                content = f.read()
            if f'"{table_name}"' in content or f"'{table_name}'" in content:
                for match in re.finditer(r'sa\.Column\(["\'](\w+)["\']', content):
                    migration_columns.add(match.group(1))
                for match in re.finditer(rf'add_column\(["\'{table_name}["\'],\s*sa\.Column\(["\'](\w+)["\']', content):
                    migration_columns.add(match.group(1))

        missing = model_columns - migration_columns
        assert not missing, (
            f"{model_cls.__name__} columns missing from migrations: {missing}. "
            f"Model columns: {sorted(model_columns)}. "
            f"Migration columns: {sorted(migration_columns)}"
        )


def test_migration_chain_is_unbroken():
    """Verify that migrations form a valid chain (no orphan revisions)."""
    migration_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')

    revisions = {}  # revision_id -> down_revision
    for fname in os.listdir(migration_dir):
        if not fname.endswith('.py'):
            continue
        filepath = os.path.join(migration_dir, fname)
        with open(filepath) as f:
            content = f.read()
        rev_match = re.search(r'revision\s*=\s*["\'](\w+)["\']', content)
        down_match = re.search(r'down_revision\s*=\s*["\'](\w+)["\']', content)
        if rev_match:
            rev = rev_match.group(1)
            down_rev = down_match.group(1) if down_match else None
            revisions[rev] = down_rev

    # Find head (revision not referenced as down_revision by anyone)
    all_down = set(revisions.values())
    heads = [r for r in revisions if r not in all_down]
    assert len(heads) == 1, f"Expected exactly 1 migration head, found {len(heads)}: {heads}"

    # Walk the chain from head to root
    current = heads[0]
    visited = set()
    while current:
        assert current not in visited, f"Cycle detected at revision {current}"
        visited.add(current)
        current = revisions.get(current)

    # All revisions should have been visited
    assert visited == set(revisions.keys()), (
        f"Orphan revisions detected: {set(revisions.keys()) - visited}"
    )


def test_quote_ticket_id_nullable_in_migration():
    """Verify the migration makes quotes.ticket_id nullable for standalone quotes."""
    migration_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')

    found_nullable = False
    for fname in os.listdir(migration_dir):
        if not fname.endswith('.py'):
            continue
        filepath = os.path.join(migration_dir, fname)
        with open(filepath) as f:
            content = f.read()
        if 'alter_column' in content and 'ticket_id' in content and 'nullable=True' in content:
            found_nullable = True
            break

    assert found_nullable, (
        "No migration found that alters quotes.ticket_id to nullable=True. "
        "Standalone quotes require ticket_id to be nullable."
    )


# ── R5.2: Critical route availability ──

def _setup_app_and_login(monkeypatch):
    """Create app, seed data, login, return (app, client, ids)."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Route Test Customer', phone='+34555666777',
            email='routetest@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Samsung',
            model='Galaxy S24', serial_number='SN-RT', imei='IMEI-RT',
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-RT01', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        part = Part(sku='RT-001', name='Test Part', is_active=True, sale_price=50.00)
        db.session.add(part)
        db.session.commit()
        ids = {
            'branch_id': str(branch.id),
            'customer_id': str(customer.id),
            'device_id': str(device.id),
            'ticket_id': str(ticket.id),
            'part_id': str(part.id),
        }

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)
    return app, client, ids


def test_quotes_list_route(monkeypatch):
    """GET /quotes/list should return 200."""
    app, client, ids = _setup_app_and_login(monkeypatch)
    resp = client.get('/quotes/list')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b'Quotes' in resp.data


def test_ticket_detail_with_quote(monkeypatch):
    """Ticket detail should render when ticket has quotes."""
    app, client, ids = _setup_app_and_login(monkeypatch)

    # Create a quote for the ticket
    import uuid
    with app.app_context():
        quote = Quote(
            ticket_id=uuid.UUID(ids['ticket_id']),
            version=1, status='draft', terms_snapshot='Test',
        )
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Repair', position=1)
        db.session.add(option)
        db.session.commit()

    resp = client.get(f'/tickets/{ids["ticket_id"]}')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


def test_standalone_quote_on_list(monkeypatch):
    """Quotes list should handle standalone quotes (ticket_id=None)."""
    app, client, ids = _setup_app_and_login(monkeypatch)

    import uuid
    with app.app_context():
        quote = Quote(
            ticket_id=None,
            customer_name='Walk-in Client',
            device_description='Broken phone',
            version=1, status='draft', terms_snapshot='Test',
        )
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Quick Fix', position=1)
        db.session.add(option)
        db.session.commit()

    resp = client.get('/quotes/list')
    assert resp.status_code == 200
    assert b'Walk-in Client' in resp.data or b'Standalone' in resp.data


def test_intake_new_route(monkeypatch):
    """GET /intake/new should return 200."""
    app, client, ids = _setup_app_and_login(monkeypatch)
    resp = client.get('/intake/new')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b'Intake' in resp.data


def test_reports_dashboard_route(monkeypatch):
    """GET /reports/ should return 200."""
    app, client, ids = _setup_app_and_login(monkeypatch)
    resp = client.get('/reports/')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b'KPI' in resp.data or b'Report' in resp.data


def test_dashboard_route(monkeypatch):
    """GET / (dashboard) should return 200."""
    app, client, ids = _setup_app_and_login(monkeypatch)
    resp = client.get('/')
    assert resp.status_code == 200


def test_ticket_new_route(monkeypatch):
    """GET /tickets/new should return 200."""
    app, client, ids = _setup_app_and_login(monkeypatch)
    resp = client.get('/tickets/new')
    assert resp.status_code == 200
    assert b'Create Repair Ticket' in resp.data


def test_reports_with_quotes_in_db(monkeypatch):
    """Reports page should work when quotes exist in the database."""
    app, client, ids = _setup_app_and_login(monkeypatch)

    import uuid
    with app.app_context():
        # Create both ticket-linked and standalone quotes
        q1 = Quote(
            ticket_id=uuid.UUID(ids['ticket_id']),
            version=1, status='sent', terms_snapshot='Test',
        )
        q2 = Quote(
            ticket_id=None,
            customer_name='Phone Client',
            device_description='iPhone',
            version=1, status='approved', terms_snapshot='Test',
        )
        db.session.add_all([q1, q2])
        db.session.commit()

    resp = client.get('/reports/')
    assert resp.status_code == 200


def test_quote_detail_for_standalone(monkeypatch):
    """Quote detail page should work for standalone quotes."""
    app, client, ids = _setup_app_and_login(monkeypatch)

    import uuid
    with app.app_context():
        quote = Quote(
            ticket_id=None,
            customer_name='Detail Test',
            device_description='iPad Pro',
            version=1, status='draft', terms_snapshot='Terms',
        )
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Repair', position=1)
        db.session.add(option)
        db.session.commit()
        quote_id = str(quote.id)

    resp = client.get(f'/quotes/{quote_id}')
    assert resp.status_code == 200
