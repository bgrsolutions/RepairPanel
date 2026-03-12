# IRONCore Odoo Integration Plan

## 1. Strategy
- Build an internal export layer now; add direct API sync later.
- Keep integration isolated in dedicated services and mapping tables.
- Export events triggered by operational milestones (e.g., collected).

## 2. Export Payload Domains
- Customer: identity + contact + preferred language + tax identifiers.
- Ticket: ticket number, branch, statuses, dates, warranty flags.
- Device: category, model, serial/IMEI (where available).
- Labour: line descriptions, units/hours, cost/sell amounts.
- Parts: part usage lines and ordered/install references.
- Quote totals and accepted option metadata.
- Collection and external payment confirmation markers.

## 3. Mapping Approach
- Maintain internal-to-Odoo mapping keys (`integration_mappings`).
- Support idempotent export retries with export batch IDs.
- Track export status per record: pending/sent/acknowledged/failed.

## 4. Data Quality Rules
- Required export fields validated pre-export.
- Incomplete data held in exception queue with actionable reasons.
- Audit each export attempt with payload hash and response metadata.

## 5. Phased Integration
- Phase A: CSV/JSON manual export package.
- Phase B: scheduled API sync with retry queue.
- Phase C: near real-time event-driven sync and reconciliation.
