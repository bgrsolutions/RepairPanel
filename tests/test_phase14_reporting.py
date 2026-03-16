"""Phase 14 — Reporting, KPIs & Management Dashboards tests.

Covers:
- Reporting service functions (management overview, workload, throughput, quotes, inventory, comms)
- Route protection (server-side enforcement via @permission_required(can_view_reports))
- Reporting filters (date range, branch, technician)
- Drill-down links in templates
- Role-aware access (management roles only)
"""
import re
import uuid
from datetime import datetime, timedelta
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
    AuditLog,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, PartCategory, StockLevel, StockLocation
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.reporting_service import (
    _apply_ticket_filters,
    _parse_date_range,
    communication_report,
    inventory_report,
    management_overview,
    quote_report,
    technician_workload,
    ticket_throughput,
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
    # AuditLog uses JSONB which isn't supported in SQLite — create manually
    from sqlalchemy import text
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id CHAR(32) PRIMARY KEY,
                actor_user_id CHAR(32) REFERENCES users(id),
                action VARCHAR(120) NOT NULL,
                entity_type VARCHAR(80) NOT NULL,
                entity_id VARCHAR(64),
                ip_address VARCHAR(64),
                user_agent VARCHAR(255),
                details TEXT,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _csrf(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1).decode()
    m2 = re.search(rb'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert m2, "No csrf_token found in page"
    return m2.group(1).decode()


def _login(client, email='admin@ironcore.com', password='admin1234'):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={
        'email': email, 'password': password, 'csrf_token': token,
    }, follow_redirects=True)
    return r


def _create_user_with_role(role_name, email, password='test1234'):
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


def _setup_app_and_data():
    """Create app, tables, seed data, and some test tickets."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
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

        now = datetime.utcnow()
        # Create technician user
        tech_role = Role.query.filter_by(name="Technician").first()
        if not tech_role:
            tech_role = Role(name="Technician", description="Tech")
            db.session.add(tech_role)
            db.session.flush()
        tech_user = User.query.filter_by(email="tech@test.com").first()
        if not tech_user:
            tech_user = User(email="tech@test.com", full_name="Test Tech", is_active=True)
            tech_user.set_password("test1234")
            tech_user.roles.append(tech_role)
            db.session.add(tech_user)
            db.session.flush()

        statuses = [
            Ticket.STATUS_UNASSIGNED,
            Ticket.STATUS_IN_REPAIR,
            Ticket.STATUS_IN_REPAIR,
            Ticket.STATUS_COMPLETED,
            Ticket.STATUS_AWAITING_PARTS,
        ]
        for i, status in enumerate(statuses):
            t = Ticket(
                ticket_number=f"HQ-RPT-{i:05d}",
                branch_id=branch.id,
                customer_id=customer.id,
                device_id=device.id,
                internal_status=status,
                customer_status="In Progress",
                priority="normal",
                assigned_technician_id=tech_user.id if status != Ticket.STATUS_UNASSIGNED else None,
                created_at=now - timedelta(days=i),
                updated_at=now - timedelta(days=max(i - 1, 0)),
            )
            db.session.add(t)
        db.session.commit()
    return app


# ─── Reporting service unit tests ─────────────────────────────────


@_patch_log_action
def test_parse_date_range_today():
    """_parse_date_range returns correct bounds for 'today'."""
    now = datetime(2025, 6, 15, 14, 30, 0)
    start, end = _parse_date_range("today", now)
    assert start == datetime(2025, 6, 15, 0, 0, 0)
    assert end == now


@_patch_log_action
def test_parse_date_range_last_7_days():
    """_parse_date_range returns 7-day window."""
    now = datetime(2025, 6, 15, 14, 30, 0)
    start, end = _parse_date_range("last_7_days", now)
    assert start == now - timedelta(days=7)
    assert end == now


@_patch_log_action
def test_parse_date_range_none():
    """_parse_date_range returns None,None for empty input."""
    start, end = _parse_date_range(None)
    assert start is None
    assert end is None


@_patch_log_action
def test_parse_date_range_this_month():
    """_parse_date_range returns first of month to now for 'this_month'."""
    now = datetime(2025, 6, 15, 14, 30, 0)
    start, end = _parse_date_range("this_month", now)
    assert start == datetime(2025, 6, 1, 0, 0, 0)
    assert end == now


@_patch_log_action
def test_parse_date_range_last_month():
    """_parse_date_range returns previous month range for 'last_month'."""
    now = datetime(2025, 6, 15, 14, 30, 0)
    start, end = _parse_date_range("last_month", now)
    assert start.month == 5
    assert start.day == 1
    assert end.month == 5


@_patch_log_action
def test_apply_ticket_filters_by_branch():
    """_apply_ticket_filters correctly filters by branch_id."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        branch = Branch.query.first()
        filtered = _apply_ticket_filters(tickets, branch_id=str(branch.id))
        assert len(filtered) == len(tickets)  # all tickets belong to same branch

        # Filter by non-existent branch
        filtered = _apply_ticket_filters(tickets, branch_id="nonexistent")
        assert len(filtered) == 0


@_patch_log_action
def test_management_overview():
    """management_overview returns correct counts."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        now = datetime.utcnow()
        overview = management_overview(tickets, now=now, sla_days=5)

        assert overview["total_open"] >= 4  # 1 unassigned + 2 in_repair + 1 awaiting_parts (+ seed data)
        assert overview["unassigned"] >= 1
        assert isinstance(overview["overdue"], int)
        assert isinstance(overview["created_today"], int)
        assert isinstance(overview["completed_today"], int)


@_patch_log_action
def test_technician_workload():
    """technician_workload returns per-technician breakdown."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        now = datetime.utcnow()
        workload = technician_workload(tickets, now=now, sla_days=5)

        assert isinstance(workload, list)
        assert len(workload) >= 1  # At least Unassigned + Test Tech
        tech_names = [w["technician_name"] for w in workload]
        assert "Test Tech" in tech_names
        assert "Unassigned" in tech_names

        tech_entry = next(w for w in workload if w["technician_name"] == "Test Tech")
        assert tech_entry["in_repair"] == 2
        assert tech_entry["completed"] == 1
        assert tech_entry["total"] >= 3


@_patch_log_action
def test_ticket_throughput():
    """ticket_throughput returns lifecycle KPIs."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        now = datetime.utcnow()
        tp = ticket_throughput(tickets, now=now, sla_days=5)

        assert isinstance(tp["avg_age_days"], float)
        assert isinstance(tp["avg_turnaround_days"], float)
        assert isinstance(tp["status_counts"], dict)
        assert isinstance(tp["stalled_count"], int)
        assert isinstance(tp["created_this_week"], int)


@_patch_log_action
def test_ticket_throughput_status_counts():
    """ticket_throughput status_counts includes all ticket statuses."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        tp = ticket_throughput(tickets, now=datetime.utcnow(), sla_days=5)
        # We created tickets in: unassigned, in_repair(x2), completed, awaiting_parts
        assert tp["status_counts"].get("In Repair", 0) == 2
        assert tp["status_counts"].get("Completed", 0) == 1


@_patch_log_action
def test_quote_report_empty():
    """quote_report returns zeros when no quotes exist."""
    app = _setup_app_and_data()
    with app.app_context():
        result = quote_report()
        assert result["total_quotes"] == 0
        assert result["approval_rate"] == 0.0
        assert result["by_status"] == {}


@_patch_log_action
def test_quote_report_with_data():
    """quote_report computes approval rate correctly."""
    app = _setup_app_and_data()
    with app.app_context():
        ticket = Ticket.query.first()
        customer = Customer.query.first()
        now = datetime.utcnow()

        # Create quotes: 2 sent, 1 approved, 1 draft
        q1 = Quote(ticket_id=ticket.id, customer_id=customer.id, status="approved", sent_at=now - timedelta(days=2))
        q2 = Quote(ticket_id=ticket.id, customer_id=customer.id, status="sent", sent_at=now - timedelta(days=1))
        q3 = Quote(ticket_id=ticket.id, customer_id=customer.id, status="draft")
        db.session.add_all([q1, q2, q3])
        db.session.commit()

        result = quote_report()
        assert result["total_quotes"] == 3
        assert result["by_status"]["approved"] == 1
        assert result["by_status"]["sent"] == 1
        assert result["by_status"]["draft"] == 1
        # Approval rate: 1 approved / 2 (sent+approved) = 50%
        assert 49.0 <= result["approval_rate"] <= 51.0


@_patch_log_action
def test_inventory_report_empty():
    """inventory_report returns empty data when no reservations."""
    app = _setup_app_and_data()
    with app.app_context():
        result = inventory_report()
        assert result["most_used"] == []
        assert result["consumed_count"] == 0
        assert result["reserved_count"] == 0


@_patch_log_action
def test_communication_report():
    """communication_report counts portal tokens."""
    app = _setup_app_and_data()
    with app.app_context():
        ticket = Ticket.query.first()
        now = datetime.utcnow()

        # Active token (not expired, not used)
        t1 = PortalToken(
            token="active-token-1",
            token_type="status_check",
            ticket_id=ticket.id,
            expires_at=now + timedelta(days=7),
        )
        # Expired token
        t2 = PortalToken(
            token="expired-token-1",
            token_type="status_check",
            ticket_id=ticket.id,
            expires_at=now - timedelta(days=1),
        )
        db.session.add_all([t1, t2])
        db.session.commit()

        result = communication_report(now=now)
        assert result["active_tokens"] == 1
        assert result["total_tokens"] == 2
        assert result["expired_tokens"] == 1


@_patch_log_action
def test_apply_ticket_filters_by_technician():
    """_apply_ticket_filters filters by technician_id."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        tech = User.query.filter_by(email="tech@test.com").first()
        filtered = _apply_ticket_filters(tickets, technician_id=str(tech.id))
        # All non-unassigned tickets are assigned to tech
        assert all(str(t.assigned_technician_id) == str(tech.id) for t in filtered)
        assert len(filtered) == 4  # 2 in_repair + 1 completed + 1 awaiting_parts


@_patch_log_action
def test_apply_ticket_filters_by_date():
    """_apply_ticket_filters filters by date range."""
    app = _setup_app_and_data()
    with app.app_context():
        tickets = Ticket.query.filter(Ticket.deleted_at.is_(None)).all()
        now = datetime.utcnow()
        # Only tickets created today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        filtered = _apply_ticket_filters(tickets, date_start=today_start, date_end=now)
        # First ticket was created now - 0 days = today
        assert len(filtered) >= 1


# ─── Route access tests ───────────────────────────────────────────


@_patch_log_action
def test_reports_dashboard_requires_login():
    """GET /reports/ redirects unauthenticated users."""
    app = _setup_app_and_data()
    with app.test_client() as client:
        r = client.get('/reports/')
        assert r.status_code in (302, 401)


@_patch_log_action
def test_reports_dashboard_requires_management_role():
    """GET /reports/ returns 403 for non-management roles."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Read Only", "readonly@test.com")
    client = app.test_client()
    _login(client, "readonly@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 403


@_patch_log_action
def test_reports_dashboard_accessible_for_admin():
    """GET /reports/ returns 200 for Admin role."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)  # admin@ironcore.com has Admin role
    r = client.get('/reports/')
    assert r.status_code == 200
    assert b"KPI Dashboard" in r.data


@_patch_log_action
def test_reports_dashboard_accessible_for_manager():
    """GET /reports/ returns 200 for Manager role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Manager", "manager@test.com")
    client = app.test_client()
    _login(client, "manager@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 200


@_patch_log_action
def test_reports_dashboard_forbidden_for_technician():
    """GET /reports/ returns 403 for Technician role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Technician", "tech2@test.com")
    client = app.test_client()
    _login(client, "tech2@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 403


@_patch_log_action
def test_reports_dashboard_forbidden_for_front_desk():
    """GET /reports/ returns 403 for Front Desk role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Front Desk", "fd@test.com")
    client = app.test_client()
    _login(client, "fd@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 403


@_patch_log_action
def test_reports_dashboard_forbidden_for_inventory():
    """GET /reports/ returns 403 for Inventory role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Inventory", "inv@test.com")
    client = app.test_client()
    _login(client, "inv@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 403


@_patch_log_action
def test_technician_workload_route_protected():
    """GET /reports/technician-workload requires management role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Technician", "tech3@test.com")
    client = app.test_client()
    _login(client, "tech3@test.com", "test1234")
    r = client.get('/reports/technician-workload')
    assert r.status_code == 403


@_patch_log_action
def test_technician_workload_route_accessible():
    """GET /reports/technician-workload returns 200 for Admin."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/technician-workload')
    assert r.status_code == 200
    assert b"Technician Workload" in r.data


@_patch_log_action
def test_quote_reporting_route_protected():
    """GET /reports/quotes requires management role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Front Desk", "fd2@test.com")
    client = app.test_client()
    _login(client, "fd2@test.com", "test1234")
    r = client.get('/reports/quotes')
    assert r.status_code == 403


@_patch_log_action
def test_quote_reporting_route_accessible():
    """GET /reports/quotes returns 200 for Admin."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/quotes')
    assert r.status_code == 200
    assert b"Quote Pipeline Report" in r.data


@_patch_log_action
def test_inventory_reporting_route_protected():
    """GET /reports/inventory requires management role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Inventory", "inv2@test.com")
    client = app.test_client()
    _login(client, "inv2@test.com", "test1234")
    r = client.get('/reports/inventory')
    assert r.status_code == 403


@_patch_log_action
def test_inventory_reporting_route_accessible():
    """GET /reports/inventory returns 200 for Admin."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/inventory')
    assert r.status_code == 200
    assert b"Inventory" in r.data


# ─── Filter integration tests ─────────────────────────────────────


@_patch_log_action
def test_reports_dashboard_with_date_filter():
    """GET /reports/?date_range=today applies date filter."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/?date_range=today')
    assert r.status_code == 200


@_patch_log_action
def test_reports_dashboard_with_branch_filter():
    """GET /reports/?branch_id=<id> applies branch filter."""
    app = _setup_app_and_data()
    with app.app_context():
        branch = Branch.query.first()
        branch_id = str(branch.id)
    client = app.test_client()
    _login(client)
    r = client.get(f'/reports/?branch_id={branch_id}')
    assert r.status_code == 200


@_patch_log_action
def test_reports_dashboard_with_all_filters():
    """GET /reports/ with all filters applied returns 200."""
    app = _setup_app_and_data()
    with app.app_context():
        branch = Branch.query.first()
        tech = User.query.filter_by(email="tech@test.com").first()
    client = app.test_client()
    _login(client)
    r = client.get(f'/reports/?date_range=last_7_days&branch_id={branch.id}&technician_id={tech.id}')
    assert r.status_code == 200


# ─── Template content tests ───────────────────────────────────────


@_patch_log_action
def test_dashboard_contains_overview_tiles():
    """Dashboard template renders overview metric tiles."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert "Total Open" in html
    assert "Overdue" in html
    assert "Unassigned" in html


@_patch_log_action
def test_dashboard_contains_throughput_metrics():
    """Dashboard template renders throughput KPI section."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert "Avg Age" in html
    assert "Avg Turnaround" in html
    assert "Stalled" in html


@_patch_log_action
def test_dashboard_contains_drill_down_links():
    """Dashboard has drill-down links to sub-reports and ticket lists."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert "technician-workload" in html
    assert "Quote Report" in html or "/reports/quotes" in html
    assert "Inventory Report" in html or "/reports/inventory" in html


@_patch_log_action
def test_dashboard_contains_communication_section():
    """Dashboard template renders communication & portal metrics."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert "Communication" in html or "Portal" in html
    assert "Active Tokens" in html


@_patch_log_action
def test_dashboard_contains_quote_pipeline():
    """Dashboard template renders quote pipeline section."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert "Quote Pipeline" in html
    assert "Approval Rate" in html


@_patch_log_action
def test_dashboard_contains_filter_form():
    """Dashboard template has a filter form with date range, branch, technician."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    assert 'name="date_range"' in html
    assert 'name="branch_id"' in html
    assert 'name="technician_id"' in html


@_patch_log_action
def test_technician_workload_template_has_view_tickets_link():
    """Technician workload page has drill-down link to ticket list."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/technician-workload')
    html = r.data.decode()
    assert "View Tickets" in html


@_patch_log_action
def test_dashboard_status_breakdown_has_drill_down():
    """Status breakdown items in dashboard link to filtered ticket list."""
    app = _setup_app_and_data()
    client = app.test_client()
    _login(client)
    r = client.get('/reports/')
    html = r.data.decode()
    # Status items should link to ticket list with status filter
    assert "/tickets" in html


# ─── Inventory report with data ───────────────────────────────────


@_patch_log_action
def test_inventory_report_with_reservations():
    """inventory_report counts consumed and reserved parts."""
    app = _setup_app_and_data()
    with app.app_context():
        ticket = Ticket.query.first()
        branch = Branch.query.first()

        # Create a part and stock location
        supplier = Supplier(name="Test Supplier")
        db.session.add(supplier)
        db.session.flush()

        part = Part(sku="TST-001", name="Test Screen", is_active=True)
        db.session.add(part)
        db.session.flush()

        loc = StockLocation(branch_id=branch.id, code="BIN-1", name="Bin 1", location_type="shelf")
        db.session.add(loc)
        db.session.flush()

        # Create reservations
        r1 = StockReservation(
            ticket_id=ticket.id, part_id=part.id, branch_id=branch.id,
            location_id=loc.id, quantity=2.0, status="reserved",
        )
        r2 = StockReservation(
            ticket_id=ticket.id, part_id=part.id, branch_id=branch.id,
            location_id=loc.id, quantity=1.0, status="consumed",
        )
        db.session.add_all([r1, r2])
        db.session.commit()

        result = inventory_report()
        assert result["reserved_count"] == 1
        assert result["consumed_count"] == 1
        assert len(result["most_used"]) >= 1
        assert result["most_used"][0]["sku"] == "TST-001"
        assert result["most_used"][0]["quantity"] == 3.0


# ─── Super Admin access ──────────────────────────────────────────


@_patch_log_action
def test_reports_accessible_for_super_admin():
    """GET /reports/ returns 200 for Super Admin role."""
    app = _setup_app_and_data()
    with app.app_context():
        _create_user_with_role("Super Admin", "superadmin@test.com")
    with app.test_client() as client:
        _login(client, "superadmin@test.com", "test1234")
    r = client.get('/reports/')
    assert r.status_code == 200


# ─── Management overview edge cases ──────────────────────────────


@_patch_log_action
def test_management_overview_empty():
    """management_overview handles empty ticket list."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        result = management_overview([], now=datetime.utcnow(), sla_days=5)
        assert result["total_open"] == 0
        assert result["overdue"] == 0
        assert result["unassigned"] == 0


@_patch_log_action
def test_ticket_throughput_empty():
    """ticket_throughput handles empty ticket list."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        result = ticket_throughput([], now=datetime.utcnow(), sla_days=5)
        assert result["avg_age_days"] == 0.0
        assert result["avg_turnaround_days"] == 0.0
        assert result["stalled_count"] == 0


@_patch_log_action
def test_technician_workload_empty():
    """technician_workload handles empty ticket list."""
    result = technician_workload([], now=datetime.utcnow(), sla_days=5)
    assert result == []
