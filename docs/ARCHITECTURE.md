# IRONCore Architecture

## 1. System Architecture
- **Presentation layer**: Flask + Jinja + Tailwind + Alpine.js/HTMX.
- **Application layer**: Flask blueprints + service layer (business logic orchestration).
- **Domain/data layer**: SQLAlchemy models + repository-style query helpers.
- **Infrastructure layer**: PostgreSQL (preferred), Alembic migrations, local file storage abstraction, Docker.
- **Integration layer**: export adapters for Odoo payload generation (future sync-ready).

## 2. Module Structure
1. Dashboard
2. Tickets
3. Customers
4. Devices
5. Intake/Check-in
6. Diagnostics
7. Quotes
8. Parts & Inventory
9. Ordered Parts
10. Suppliers
11. Technician Queue
12. Labels & Printing
13. Public Check-in Portal
14. Public Status Portal
15. Reports
16. Settings/Admin
17. Audit Logs
18. Notifications
19. Integration (Odoo)

## 3. Flask Blueprint Structure
- `core` (layout, dashboard shell, common UI)
- `auth`
- `tickets`
- `customers`
- `devices`
- `intake`
- `diagnostics`
- `quotes`
- `inventory`
- `orders`
- `suppliers`
- `labels`
- `public_portal`
- `reports`
- `settings`
- `audit`
- `notifications`
- `integrations`

## 4. Service Layer Structure
- `ticket_service`: lifecycle transitions, validations, status mapping.
- `intake_service`: category form schemas, disclaimers, signatures.
- `quote_service`: revisions/options, approval token lifecycle.
- `inventory_service`: reservations, stock moves, low-stock checks.
- `parts_order_service`: supplier orders, ETA and arrival transitions.
- `print_service`: template render context, PDF/label generation.
- `notification_service`: event-to-template channel dispatch.
- `portal_service`: public token validation and safe data projection.
- `audit_service`: immutable event writes for critical actions.
- `odoo_export_service`: build outbound normalized payloads.

## 5. Storage Architecture
- Files stored via `storage_provider` abstraction:
  - Local provider (phase 1-2 default).
  - S3/MinIO provider (future via config switch).
- Upload classes: ticket media, signatures, generated PDFs, supplier docs.

## 6. Deployment Architecture
- Dockerized Flask app container.
- Reverse proxy (Nginx/Caddy) for TLS termination in production.
- Database container/service (PostgreSQL preferred).
- Optional worker container later for async notifications/report tasks.

## 7. Security Architecture
- Flask-Login session auth + password hashing + secure session cookies.
- CSRF protections for forms; strict validation for uploads.
- Branch-aware authorization middleware.
- Sensitive fields (passcodes/passwords) encrypted at rest.
- Public endpoints tokenized + rate-limited.
- Audit logging for privileged actions, status changes, data exports.

## 8. Proposed Repository Structure
```text
/docs
/app
  /blueprints
  /models
  /services
  /forms
  /templates
  /static
    /css
    /js
    /images
  /utils
  /translations
/tests
/migrations
/docker
```
