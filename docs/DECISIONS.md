# Architectural Decisions (ADR Log)

## ADR-001: Flask as Core Framework
- **Status**: Accepted
- **Context**: Project requirement mandates Flask.
- **Decision**: Use Flask with blueprint modularization and service layer.
- **Consequences**: Fast iteration and Python ecosystem leverage; must enforce structure discipline.

## ADR-002: PostgreSQL Preferred, MariaDB Compatible
- **Status**: Accepted
- **Context**: Need robust relational model and optional MariaDB support.
- **Decision**: Optimize for PostgreSQL features while keeping SQLAlchemy portability.
- **Consequences**: Avoid overreliance on DB-specific features in core schema.

## ADR-003: Server-Rendered UI with HTMX/Alpine Enhancements
- **Status**: Accepted
- **Context**: Need modern UX without SPA overhead.
- **Decision**: Use Jinja + Tailwind, add HTMX/Alpine for dynamic interactions.
- **Consequences**: Simpler deployment; careful component consistency needed.

## ADR-004: Integration-Ready, Not Accounting-Capable
- **Status**: Accepted
- **Context**: Odoo will handle invoicing.
- **Decision**: Build exports/integration boundary now, defer accounting engine.
- **Consequences**: Clear scope boundary and reduced implementation risk.

## ADR-005: Multi-Branch + i18n from Day One
- **Status**: Accepted
- **Context**: Core operational requirement.
- **Decision**: Branch scoping and translation architecture are foundational, not optional.
- **Consequences**: Higher initial complexity but avoids expensive retrofit.

## ADR-006: PostgreSQL as Phase 1 Default Database
- **Status**: Accepted
- **Context**: Documentation allows PostgreSQL or MariaDB; implementation request prefers PostgreSQL.
- **Decision**: Phase 1 uses PostgreSQL and `psycopg2`, with migration and docker defaults aligned to PostgreSQL.
- **Consequences**: Faster path for JSONB/audit flexibility and consistent local/prod parity; MariaDB compatibility can be evaluated in later phases.

## ADR-007: Shared Customer/Device Records with Optional Branch Affinity
- **Status**: Accepted
- **Context**: Governance requires shared customer/device history across branches.
- **Decision**: Keep customer/device as global entities; include optional customer primary branch but avoid hard branch partitioning at model level.
- **Consequences**: Supports cross-branch service continuity while preserving branch-aware ticket ownership.

## ADR-008: Ticket Operational Status + SLA Foundation
- **Status**: Accepted
- **Context**: Operational workflow required consistent ticket lifecycle buckets and overdue logic before future expansion.
- **Decision**: Normalize internal ticket statuses to controlled snake_case states and add a ticket-level `sla_target_at` timestamp set on creation from configurable default SLA days.
- **Consequences**: Bench board/dashboard can compute actionable overdue and aging queues; quote workflow remains separate and compatible via `awaiting_quote_approval` status.

## ADR-009: Parts Deactivation over Hard Delete
- **Status**: Accepted
- **Context**: Parts are linked to stock, reservations, and order history, making hard-delete unsafe for operational integrity.
- **Decision**: Keep `Part.is_active` as the operational archive mechanism and expose manager/admin toggle actions in UI; default lists hide inactive parts.
- **Consequences**: Historical links remain intact while day-to-day workflows are protected from accidental reuse of retired SKUs.
