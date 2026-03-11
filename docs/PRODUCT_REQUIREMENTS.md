# IRONCore Product Requirements

## 1. Functional Requirements
- Multi-user authentication and role-based access control.
- Multi-branch operations with branch-scoped visibility and settings.
- Ticket creation, assignment, status management, reopening, and closure.
- Device check-in with category-specific forms and configurable custom fields.
- Customer and device history across all branches.
- Diagnostics capture, recommended actions, and QA checklist completion.
- Quote creation with revisions, options, expiry, and approval workflows.
- Parts and inventory management with reservations and stock movements.
- Ordered parts lifecycle tracking linked to tickets and suppliers.
- Label/receipt generation with QR/barcode output and print templates.
- Public pre-check-in portal + kiosk mode + branch-specific links/QRs.
- Public repair status portal with controlled external visibility.
- Reporting dashboards and exportable KPI views.
- Audit logging for sensitive and operational actions.
- Odoo export readiness for repair and quote outputs.

## 2. Non-Functional Requirements
- Availability target: 99.5%+ (single deployment), scaling path for higher.
- Responsive UX for desktop/tablet/mobile.
- Security: CSRF, secure sessions, sensitive field protection, file validation.
- Performance: primary list views should load in <2s under normal branch load.
- Observability: structured logs, audit events, reportable workflow metrics.
- Maintainability: modular blueprints, service layer, migration discipline.
- Portability: Dockerized environment and .env-driven configuration.

## 3. Device Categories
Mandatory categories:
- Phones
- Tablets
- Laptops
- Desktops
- Game Consoles
- Handheld Consoles
- Smart Watches
- Controllers
- Drones
- TVs
- Other (admin configurable)

## 4. Branch Support Requirements
- Branch-specific tickets, stock locations, label/printer profiles, and public portal URLs.
- Optional global visibility for privileged roles (admin/manager).
- Shared customer/device master records across branches.

## 5. Multilingual Requirements
- Minimum EN/ES for internal UI, customer portals, templates, and print documents.
- Translation architecture must support adding locales without schema redesign.
- Customer preferred language influences communication and document generation.

## 6. Ticket System Requirements
- Unique ticket code and branch-aware sequence strategy.
- Internal status + customer-facing status mapping.
- Priority, assignment, due dates, tags, warranty/repeat flags, timeline.
- Related records: diagnostics, quotes, parts reservations, part orders, QA, collection.

## 7. Repair Workflow Requirements
- Enforced flow: intake -> diagnosis -> quote/approval -> parts -> repair -> QA -> collection.
- Configurable exceptions (no quote path, no parts path, unrepairable path).
- Warranty return detection and linked ticket references.

## 8. Reporting Requirements
- Dashboard KPIs for queue health, parts delays, quote conversion, turnaround time.
- Branch/device/technician level reports.
- CSV/Excel export support.
