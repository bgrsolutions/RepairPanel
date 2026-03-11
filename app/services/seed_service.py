from app.config import Config
from app.extensions import db
from app.models import Branch, Customer, Device, Role, Ticket, User
from app.utils.ticketing import generate_ticket_number


def seed_phase1_data():
    role_names = [
        "Super Admin",
        "Admin",
        "Manager",
        "Front Desk",
        "Technician",
        "Inventory",
        "Read Only",
    ]

    for role_name in role_names:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name, description=f"Seeded role: {role_name}"))

    branch = Branch.query.filter_by(code=Config.DEFAULT_BRANCH_CODE).first()
    if not branch:
        branch = Branch(code=Config.DEFAULT_BRANCH_CODE, name="Main Branch")
        db.session.add(branch)
        db.session.flush()

    admin = User.query.filter_by(email="admin@ironcore.local").first()
    if not admin:
        admin = User(full_name="IRONCore Admin", email="admin@ironcore.local", preferred_language="en")
        admin.set_password("admin1234")
        admin.default_branch = branch
        admin.branches.append(branch)
        db.session.add(admin)
        db.session.flush()

    admin_role = Role.query.filter_by(name="Admin").first()
    if admin_role and admin_role not in admin.roles:
        admin.roles.append(admin_role)

    customer = Customer.query.filter_by(email="customer@demo.local").first()
    if not customer:
        customer = Customer(
            full_name="Demo Customer",
            phone="+10000000000",
            email="customer@demo.local",
            preferred_language="es",
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()

    device = Device.query.filter_by(serial_number="DEMO-SN-001").first()
    if not device:
        device = Device(
            category="phones",
            brand="DemoBrand",
            model="X1",
            serial_number="DEMO-SN-001",
            imei="123456789012345",
            customer=customer,
        )
        db.session.add(device)
        db.session.flush()

    existing_ticket = Ticket.query.filter_by(customer_id=customer.id).first()
    if not existing_ticket:
        ticket = Ticket(
            ticket_number=generate_ticket_number(branch.code, 1),
            branch=branch,
            customer=customer,
            device=device,
            internal_status="New",
            customer_status="Received",
            priority="normal",
            assigned_technician=None,
        )
        db.session.add(ticket)

    db.session.commit()
