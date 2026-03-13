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

## ADR-010: Part Orders Support Both Repair-Linked and General Stock Procurement
- **Status**: Accepted
- **Context**: Real operations require both ticket-specific purchasing and proactive stock replenishment.
- **Decision**: Make `PartOrder.ticket_id` optional and classify orders as `repair` or `stock` based on ticket linkage while keeping one supplier per order and many lines per order.
- **Consequences**: Prevents forced ticket coupling, supports multi-supplier procurement across a single repair via multiple orders, and keeps order context explicit in UI/export workflows.

## ADR-011: Receiving Updates Inventory via Stock Movements with Partial Receipt Support
- **Status**: Accepted
- **Context**: Receiving must preserve inventory auditability and cannot rely on silent quantity changes.
- **Decision**: Implement receiving against order lines using explicit inbound stock movements, line `received_quantity`, and derived order status transitions (`partially_received` / `received`).
- **Consequences**: Inventory integrity is preserved with traceable movement history; order progress reflects real-world partial deliveries and remains extensible for richer ASN/packing-slip flows later.

## ADR-012: Public Intake Uses Exact-Match Customer Linking
- **Status**: Accepted
- **Context**: Public intake should reduce duplicate customers without becoming a discoverable public customer lookup channel.
- **Decision**: Only perform public customer linkage on strict exact-match email/phone criteria (with minimal format/length sanity checks); otherwise create new intake customer data.
- **Consequences**: Maintains privacy-safe behavior while reducing duplicate records and preserving staff-side relinking control during internal conversion review.

## ADR-013: Device Ownership Reassignment Preserves Historical Ticket Integrity
- **Status**: Accepted
- **Context**: Devices can change ownership over time, but past repairs must remain auditable by original ticket/customer context.
- **Decision**: Allow current device owner transfer/unlink actions by updating `Device.customer_id` for future workflows, while keeping historical tickets unchanged (`Ticket.customer_id` remains immutable historical reference).
- **Consequences**: Supports real ownership lifecycle operations without rewriting historical repair accountability.


## ADR-014: FIFO Costing Foundation via Receipt Layers
- **Status**: Accepted
- **Context**: Inventory consumption/costing needed deterministic oldest-stock-first behavior without rewriting all movement workflows in one pass.
- **Decision**: Add `stock_layers` as receipt-layer records (`quantity_received`/`quantity_remaining`, optional unit cost) and consume outbound/install quantities from oldest remaining layers first.
- **Consequences**: Preserves stock movement history while enabling incremental FIFO costing maturity in later passes.

## ADR-015: Commercial Tax Default Uses IGIC 7%
- **Status**: Accepted
- **Context**: Commercial quote outputs require consistent Canary Islands tax defaults.
- **Decision**: Standardize quote/commercial totals to apply and display 7% IGIC by default (configurable via `DEFAULT_IGIC_RATE`).
- **Consequences**: Commercial totals are consistent and explicit; internal operational stock records remain untaxed.

## ADR-016: Part Master Supports Multiple Suppliers and Category Classification
- **Status**: Accepted
- **Context**: Operational procurement required alternate suppliers and stronger catalog browsing semantics.
- **Decision**: Keep one optional default supplier on `Part` and add supporting many-to-many-style link records (`part_suppliers`) plus category entities (`part_categories` + links).
- **Consequences**: Improves sourcing flexibility and inventory browse/filter UX while preserving existing single-order single-supplier procurement flow.
