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
