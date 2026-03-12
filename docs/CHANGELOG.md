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
