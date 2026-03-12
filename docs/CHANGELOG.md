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
