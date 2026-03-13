# Changelog

## [0.1.0] - 2026-03-11
### Added
- Initial governance documentation set for IRONCore.
- Scope, requirements, architecture, schema, workflow, role model, portal specs.
- Parts/inventory, quotes/approvals, labels/printing, Odoo readiness plans.
- Phased implementation roadmap and decision register bootstrap.

## [0.2.0] - 2026-03-11
### Added
- Implemented Phase 1 application scaffold with Flask app factory, modular blueprints, SQLAlchemy models, Flask-Migrate setup, Flask-Login auth flow, and Flask-Babel multilingual foundation.
- Added core Phase 1 data models: User, Role, Branch, Customer, Device, Ticket, AuditLog.
- Added initial Alembic migration and seed command for baseline roles/branch/admin/demo records.
- Added Dockerfile and docker-compose configuration for Flask + PostgreSQL local development.
- Added dashboard shell, base layout, login view, ticket list/create views, and Tailwind-ready static structure.

## [0.2.1] - 2026-03-11
### Added
- Internal operations UI pass with RepairDesk-inspired dark dashboard shell enhancements.
- New internal templates for ticket detail shell, technician My Queue, and repair bench board views.
- Reusable UI component macros for status/priority badges, stat cards, ticket cards, section cards, and empty states.

### Changed
- Upgraded base layout/navbar, dashboard, ticket list, and new ticket pages for premium spacing, hierarchy, and responsive behavior.
- Kept Tailwind CDN strategy and minimal custom CSS approach while improving dark-theme polish.

## [0.2.2] - 2026-03-11
### Fixed
- Login form email validation now supports local demo domains (`*.local`) by disabling deliverability checks for login input validation.
- Authentication now rejects inactive or soft-deleted users before login.
- Seed logic is now deterministic/idempotent for demo admin setup, including active flag, default branch, branch access, role assignment, and documented demo password reset in dev/demo/testing environments.

### Added
- Automated auth/seed integration test covering seed idempotency, working demo credentials, successful login redirect, and invalid-credential error handling.

## [0.2.3] - 2026-03-12
### Fixed
- Canonical demo admin is now `admin@ironcore.com` with deterministic seed normalization from legacy demo addresses (`admin@ironcore.local`, `admin@ironcore.test`).
- Seed process now enforces active canonical admin state, role linkage, default branch, and branch access on every run in dev/demo/testing.
- Local host-based setup defaults now point Flask to `127.0.0.1:5432` for PostgreSQL when DB runs in Docker.

### Added
- Auth/seed integration coverage now includes CSRF-backed login POST validation, canonical seed normalization checks, successful login redirect assertions, and invalid credential behavior.

## [0.3.0] - 2026-03-12
### Added
- Phase 2 intake foundations: internal intake workflow, public check-in portal, kiosk mode entrypoint, intake detail/review, and pre-check-in to ticket conversion flow.
- New intake domain models for intake submissions, disclaimer acceptance records, signatures, attachments, and portal tokens.
- Intake/public forms for required Phase 2 categories (phones, laptops, desktops, game consoles, other).
- Attachment upload utility with safe filename handling and image extension allowlist.
- Printable intake receipt foundation with reference and device/customer summary.
- Phase 2 migration introducing intake-related tables and indexes.
- Automated tests for internal intake creation+conversion and public pre-check-in submission (including CSRF-backed flows).

### Changed
- Base navigation now exposes intake management to internal staff users.
- App configuration expanded with upload/disclaimer defaults for intake workflows.

## [0.3.1] - 2026-03-12
### Changed
- Added isolated public-facing layout for `/public/check-in`, `/public/kiosk/check-in`, and public thank-you flow to remove internal staff navigation from kiosk/public screens.
- Added customer-centered internal workflow UI with searchable customers list and customer profile pages showing linked devices and ticket/repair history.
- Updated internal navigation to include Customers and added direct customer profile links from dashboard, ticket, and intake views.
- Improved intake detail page linkage visibility for linked customer, linked device, and converted ticket status/actions.

## [0.4.0] - 2026-03-12
### Added
- Phase 3 repair workflow foundations: ticket diagnostics capture with versioned diagnostic history, quote modeling (header/options/lines), and quote approval records.
- New staff quote module with quote creation, quote detail, send-for-approval action, manual in-store approval/decline placeholder, and expiry status controls.
- Public customer status lookup page (`/public/status`) with safe verifier-based lookup (`ticket number + phone/email`) and customer-facing data minimization.
- Public quote approval page (`/public/quote/<token>`) with tokenized decision flow (approve/decline), method metadata, and timestamp capture.
- Automated Phase 3 tests for diagnostics/quote lifecycle and public status/quote approval flows.

### Changed
- Ticket detail page now integrates diagnosis form/history, quote summaries, quote approval status visibility, and direct quote creation links.
- Internal/public route registration expanded with dedicated diagnostics and quotes blueprints.

## [0.5.0] - 2026-03-12
### Added
- Phase 4 operational workflow foundation for technician assignment and ticket notes (`internal`, `customer`, `communication`) with author/timestamp capture.
- Inventory foundation models and UI for parts catalog, suppliers, stock locations, stock levels, stock movements, and stock reservations.
- Ordered parts tracking foundation with ticket-linked part orders, order lines, and order event/status timeline (`ordered`, `shipped`, `delayed`, `partially_arrived`, `arrived`, `installed`).
- New blueprints/modules for inventory, suppliers, and orders, plus stock/order service helpers.
- Phase 4 migration introducing ticket notes and inventory/order schema tables.
- Automated tests for assignment/notes, inventory/reservations, and order creation/status transitions.

### Changed
- Ticket detail now includes technician assignment controls, structured note entry, reserved parts section, and ordered parts visibility.
- Ticket list, bench board, and my queue views now surface technician ownership more clearly.
- Internal navigation now exposes Inventory, Suppliers, and Orders operational pages.

## [0.6.0] - 2026-03-12
### Added
- Phase 5 foundation modules for reports (`/reports`), notifications (`/notifications`), settings (`/settings`), and export readiness (`/integrations/exports`).
- KPI dashboard widgets for status/branch distribution, aging tickets, technician workload, most-used parts, and parts awaiting arrival.
- Notification foundation schema and UI placeholders for templates, events, and delivery logs.
- Odoo export readiness foundation with ticket payload preview and export queue logging.
- Migration adding notification and export queue tables.
- Automated Phase 5 integration test covering new pages and export queue flow.

### Changed
- Internal navigation and dashboard quick actions now link to Reports, Notifications, Exports, and Settings.


## [0.6.1] - 2026-03-12
### Added
- Staff user management module (`/users`) with list/create/edit flows for login-capable users, role assignment, branch access, and active/inactive control.
- Ticket workflow status update endpoint/UI and SLA target foundation (`tickets.sla_target_at`) with overdue/aging calculations used across dashboard and bench board.
- Ticket creation customer-device usability improvement via customer-scoped device filtering endpoint and dynamic form behavior.
- Inventory parts operational improvements: multi-field search (name/SKU/barcode/supplier SKU) and safe activate/deactivate action instead of destructive delete behavior.
- Refinement pass integration test coverage for user management, assignment/status lifecycle, customer-device filtering, and parts deactivate flow.

### Changed
- Bench board now groups operational buckets (Unassigned, Assigned, Awaiting Diagnostics, Awaiting Parts, In Repair, Ready for Collection, Overdue, Aging) using real status + assignment + SLA logic.
- Dashboard metrics now expose distinct aging and overdue counters based on SLA foundations.
- Internal navigation reorganized into grouped operations menus with persistent New Ticket CTA and added Users/Staff access.

## [0.6.2] - 2026-03-12
### Added
- Ticket create/check-in workflow improvements: searchable customer finder pattern, create-time technician assignment, create-time operational status selection, issue summary capture, and promised completion datetime capture.
- Ticket detail metadata edit flow for issue summary + promised completion, with continued SLA visibility side-by-side.
- Quote workflow upgrades for practical multi-line quoting including optional part-linked quote lines and draft quote editing.
- Part order workflow upgrades for multi-line orders with line-level metadata, supplier reference/tracking/ETA fields, optional ticket linkage for general stock orders, and order edit flow.
- Receiving workflow for part orders that records inbound stock movements, supports partial receipts, and updates order/line statuses.
- New integration coverage for Pass B+ (ticket create assignment/ETA, multi-line quote, stock order without ticket, and partial receiving behavior).

### Changed
- Global and ticket-context order creation now uses explicit ticket selection (optional) to prevent stale/incorrect ticket associations.
- Order list/detail screens now expose repair-vs-stock context, ETA/tracking metadata, and overdue operational visibility.
- Intake conversion now supports optional technician assignment and promised completion datetime propagation into created tickets.

## [0.6.3] - 2026-03-13
### Added
- Unified internal searchable lookup endpoints for customers/tickets/parts to support intake, ticket creation, reservations, and order workflows without long static dropdown scrolling.
- Internal intake existing-customer search/select flow with safe prefill and persisted `existing_customer_id` linking behavior.
- Device ownership lifecycle actions in customer profile for transfer-to-another-customer and unlink operations while preserving historical ticket ownership context.
- Pass C automated coverage for unified search endpoints, public exact-match intake linking behavior, and device transfer/unlink workflows.

### Changed
- Public check-in customer matching now uses explicit exact-match policy for email/phone before creating a new customer, without exposing customer directory data publicly.
- Ticket create and part-order create screens now use server-backed search suggestion patterns for customer/ticket lookup consistency.
- Ticket detail reserve-part workflow now includes searchable part lookup and improved ordered-part ETA/tracking visibility cues.
- Parts catalog now surfaces operational supplier + lead-time + stock availability context for better procurement decisions.

## [0.6.4] - 2026-03-13
### Changed
- Ticket detail hierarchy is now more operationally compact: assignment + workflow controls are surfaced near the top and common updates (ticket details, notes, diagnostics) are collapsed into quick-action panels to reduce scrolling.
- Ticket ordered-parts visibility now highlights ETA/status scanability with clearer overdue cues for orders past ETA and not yet received/cancelled.
- Part-order create/edit UI now supports practical dynamic line add/remove behavior (no fixed 3-line reveal limit) while keeping server-side blank-line ignore behavior intact.

### Fixed
- Ticket detail reserve-part search prompt now explicitly aligns with supported part matching fields (name/SKU/barcode/supplier SKU).

## [0.7.0] - 2026-03-13
### Added
- Pass D ticket-detail modal workflow: read-only top summary with modal dialogs for ticket meta updates, note capture, and diagnostics entry.
- Inventory product record expansion with dedicated part detail page, category management pages, multi-supplier linkage support, and richer parts filtering (category/supplier/stock state).
- FIFO costing foundation via stock receipt layers (`stock_layers`) and oldest-layer consumption hooks in inventory movement service.
- Quote workflow enhancements for dynamic line add/remove and part-price autofill endpoint (`/quotes/part-price/<id>`).

### Changed
- Quotes now display commercial totals with default 7% IGIC (subtotal, IGIC, grand total) and expose IGIC policy in quote builder UX.
- Receiving workflow can now maintain/update part cost and sale prices at receive time.
- Parts list and stock overview now surface clickable part records with expanded pricing/lead-time/supplier visibility.

## [0.7.1] - 2026-03-13
### Added
- Bench board reworked into a tabbed workshop view (Unassigned, Assigned, Awaiting Diagnostics, Awaiting Parts, In Repair, Ready for Collection, Overdue, Aging) with lightweight in-page tab switching.
- Supplier detail/edit flow with clickable supplier records from supplier and inventory screens.
- Part edit page for operational product maintenance (pricing, lead time, suppliers, categories, metadata).

### Changed
- Ticket detail actions now include modal entry points for Create Quote and Reserve Part, with clearer ordered/reserved part visibility and restored note type color differentiation.
- My Queue now highlights waiting-on-parts, overdue-parts, and overdue-ticket buckets for technician actionability.
- Intake conversion now accepts both promised completion and explicit SLA target inputs, keeping customer-facing ETA and internal SLA distinct.
- Dashboard attention list now focuses on exception tickets (overdue SLA and overdue part ETA blockers).
- Quote builder adds searchable part lookup per line while preserving sale-price autofill and manual override behavior.
- Parts list adds lead-time presence/range filtering and supplier links to supplier detail pages.
