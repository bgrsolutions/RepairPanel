# Workshop Operations & Bench Board (Phase 8)

This document describes the workshop workflow system, bench board, ticket lifecycle, status transitions, and blocker detection introduced in Phase 8.

## Bench Board

The **Repair Bench Board** (`/tickets/board`) is the primary view for technicians and front desk staff. It displays all active tickets grouped by workflow stage:

| Column | Statuses Included |
|--------|------------------|
| Awaiting Diagnosis | `unassigned`, `assigned`, `awaiting_diagnostics` |
| Awaiting Quote Approval | `awaiting_quote_approval` |
| Awaiting Parts | `awaiting_parts` |
| Ready For Repair | `in_repair` |
| Testing / QA | `testing_qa` |
| Ready For Collection | `ready_for_collection` |

### Card Information

Each ticket card displays:
- Ticket number (clickable link to detail)
- Customer name
- Device brand and model
- Issue summary (truncated)
- Assigned technician
- SLA target date and promised completion date
- Blocker badges (OVERDUE, WAITING PARTS, WAITING QUOTE, CHECKLIST INCOMPLETE, etc.)

### Filters

The board supports filtering by:
- **Sort order**: Oldest first, Newest first, Promise due soonest, SLA due soonest
- **Technician**: Filter by assigned technician
- **Branch / Location**: Filter by store branch
- **Date range**: Today, This week, This month
- **Waiting on parts**: Show only tickets with open part orders
- **Waiting on quote**: Show only tickets with unapproved quotes
- **Overdue only**: Show only tickets past SLA target

## Ticket Lifecycle

### Status States

| Status | Description |
|--------|-------------|
| `unassigned` | New ticket, no technician assigned |
| `assigned` | Technician assigned but work not started |
| `awaiting_diagnostics` | Pending device diagnosis |
| `awaiting_quote_approval` | Quote sent, waiting for customer approval |
| `awaiting_parts` | Required parts on order |
| `in_repair` | Active repair work in progress |
| `testing_qa` | Post-repair testing and quality assurance |
| `ready_for_collection` | Repair complete, awaiting customer pickup |
| `completed` | Repair done and collected |
| `cancelled` | Work cancelled |
| `archived` | Historical record |

### Valid Transitions

```
unassigned ──> assigned, awaiting_diagnostics, cancelled
assigned ──> unassigned, awaiting_diagnostics, in_repair, cancelled
awaiting_diagnostics ──> awaiting_quote_approval, in_repair, awaiting_parts, cancelled
awaiting_quote_approval ──> awaiting_parts, in_repair, cancelled
awaiting_parts ──> in_repair, cancelled
in_repair ──> testing_qa, awaiting_parts, cancelled
testing_qa ──> in_repair, ready_for_collection, cancelled
ready_for_collection ──> completed, in_repair
completed ──> archived
cancelled ──> archived
```

Invalid transitions are rejected by the system with an error message.

### Automatic Status Updates

- Assigning a technician moves `unassigned` tickets to `assigned`
- Removing a technician moves `assigned` tickets to `unassigned`
- Quote approval can trigger move to `awaiting_parts` or `in_repair`
- Parts received can trigger move to `in_repair`

## Blocker Detection

The system automatically detects blockers on active tickets. Blockers are surfaced on:
- Bench board ticket cards (as badge labels)
- Ticket detail page (in the Workflow Status panel)
- Dashboard attention widget

### Blocker Types

| Kind | Badge | Trigger |
|------|-------|---------|
| `quote` | WAITING QUOTE / QUOTE DRAFT | Unapproved quote exists (sent or draft) |
| `parts` | WAITING PARTS / PARTS OVERDUE | Open part orders not yet received |
| `checklist` | CHECKLIST INCOMPLETE | Post-repair checklist not completed (on testing/ready status) |
| `sla` | OVERDUE | Ticket past SLA target date |

### Workflow Status Panel (Ticket Detail)

The ticket detail page includes a **Workflow Status** sidebar panel showing:
- Current status badge
- Next recommended action (context-aware suggestion)
- Active blockers with details

## Workshop Metrics

The dashboard displays operational metrics in a compact row:
- In Diagnosis
- Awaiting Quote
- Awaiting Parts
- In Repair
- Testing / QA
- Unassigned

These metrics update live from the ticket database.

## Technician Assignment

Technicians can be assigned:
1. From the **ticket detail page** sidebar (Technician & Workflow panel)
2. Via the **quick-assign AJAX endpoint** (`POST /tickets/<id>/quick-assign`)
3. During **ticket creation**

The bench board can be filtered by technician to show a specific technician's workload.

## SLA & Overdue Visibility

SLA visibility is enforced across the system:
- **Dashboard**: Dedicated "Overdue Tickets" widget lists all overdue tickets
- **Bench Board**: OVERDUE badge on affected cards, "Overdue only" filter
- **Ticket Detail**: SLA & Promise panel shows overdue indicators

## Service Module

The workflow logic is in `app/services/workflow_service.py`:

| Function | Purpose |
|----------|---------|
| `is_valid_transition(from, to)` | Check if a status transition is allowed |
| `allowed_transitions(from)` | List all valid next statuses |
| `detect_blockers(ticket)` | Detect all blockers on a ticket |
| `next_recommended_action(ticket, blockers)` | Suggest the next action |
| `workshop_metrics(tickets)` | Compute operational counts |
