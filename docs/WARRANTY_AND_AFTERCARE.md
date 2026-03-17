# Phase 17 — Warranty, Branded Communications & Customer Aftercare

## Overview

Phase 17 adds warranty tracking, branded email communications, and customer aftercare capabilities to IRONCore RepairPanel. Staff can record warranty terms when tickets are completed, track warranty status across customer and device history, and send professionally branded transactional emails.

## Warranty Model

### TicketWarranty

Stored in the `ticket_warranties` table, linked to a ticket, customer, device, and branch.

| Field | Type | Description |
|-------|------|-------------|
| `warranty_type` | string | `no_warranty`, `standard`, or `custom` |
| `warranty_days` | integer | Duration in days (default: 90) |
| `starts_at` | datetime | When the warranty begins (auto-set to completion date) |
| `expires_at` | datetime | Calculated: starts_at + warranty_days |
| `covers_labour` | boolean | Whether labour is covered |
| `covers_parts` | boolean | Whether parts are covered |
| `terms` | text | Warranty terms and exclusions |
| `repair_summary` | text | Summary of what was repaired |
| `parts_used` | text | Auto-populated from stock reservations |
| `status` | string | `active`, `expired`, `claimed`, `voided` |
| `claim_count` | integer | Number of warranty claims recorded |
| `email_sent` | boolean | Whether confirmation email was sent |

### Company Defaults

Companies can set default warranty configuration:
- `default_warranty_days` (default: 90)
- `default_warranty_terms` (free text)

These pre-fill the warranty form when completing a ticket.

## Warranty Capture Workflow

1. Staff completes or closes a ticket (status → `completed`, `ready_for_collection`, `cancelled`, or `archived`)
2. The ticket detail page shows a warranty capture form
3. Staff selects warranty type, days, coverage, and terms
4. On save, the warranty record is created with auto-calculated dates
5. Staff can optionally send a branded warranty confirmation email to the customer

### Warranty Types

- **Standard**: Default company warranty (pre-filled from company settings)
- **Custom**: Custom duration and terms for special cases
- **No Warranty**: Explicitly marks the repair as having no warranty coverage

## Warranty Evaluation

The warranty service provides reusable evaluation logic:

- `evaluate_warranty(ticket)` — Returns warranty status, days remaining, and prior repair history
- `check_device_under_warranty(device_id)` — Checks if a device currently has active warranty
- `get_device_warranty_history(device_id)` — Returns all warranties for a device
- `get_customer_warranties(customer_id)` — Returns all warranties for a customer
- `get_active_warranties(branch_id)` — Lists all active warranties
- `expire_warranties()` — Batch-expires warranties past their expiration date

### Status Logic

| Status | Condition |
|--------|-----------|
| Active | type ≠ no_warranty AND status = active AND now ≤ expires_at |
| Expired | type ≠ no_warranty AND (status = expired OR now > expires_at) |
| Claimed | Warranty has been claimed (warranty claim recorded) |
| Voided | Warranty has been explicitly voided with reason |
| No Warranty | type = no_warranty |

## Warranty Visibility

### Ticket Detail Page
- Full warranty section with type, period, coverage, dates, terms
- Status badge (Active / Expired / Claimed / Voided / No Warranty)
- Days remaining indicator
- Prior device warranties section
- Actions: Record Claim, Void Warranty, Send Warranty Email

### Customer Detail Page
- Warranty column in repair history table
- Badge showing warranty status for each ticket

### Device History
- Device warranty history accessible through customer detail
- Prior warranties shown on ticket detail for same device

## Warranty Claims and Voiding

### Claims
Staff can record warranty claims against active warranties. Each claim:
- Increments the claim count
- Records claim notes with timestamp
- Changes status to "claimed"
- Creates a ticket note for audit trail

### Voiding
Staff can void warranties with a reason. Voiding:
- Records the reason and timestamp
- Sets the voiding user
- Changes status to "voided"
- Creates a ticket note

## Branded Email Architecture

### Overview
The branded email service (`branded_email_service.py`) provides centralized, template-based email sending with:
- Company branding (name, logo, contact info, footer)
- Language-aware template selection (EN/ES)
- Safe fallback when no transport is configured
- Communication logging via ticket notes

### Transport Configuration
Set `MAIL_TRANSPORT` in app config:
- `log` (default): Logs email intent without sending — safe for development
- Future: SMTP, SendGrid, etc.

When transport is unavailable, the system logs the attempt and returns success so workflows are not blocked.

### Email Templates
Located in `app/templates/emails/{language}/`:
- `warranty_confirmation.html` — Warranty confirmation after ticket completion
- `warranty_expiry_reminder.html` — Reminder before warranty expiry
- `aftercare_followup.html` — General follow-up message
- `ticket_update.html` — Repair status update

All templates extend `emails/base_email.html` which provides:
- Branded header with company name
- Professional HTML email styling
- Footer with company contact details
- Responsive layout

### Sending Flow
1. Route handler calls branded email service function
2. Service retrieves company branding
3. Template is rendered with branding + context
4. Transport dispatches or logs the email
5. Communication note is added to the ticket
6. For warranty emails, `email_sent` flag is updated

## Permissions

| Permission | Roles | Purpose |
|-----------|-------|---------|
| `can_manage_warranty` | Super Admin, Admin, Manager, Technician | Create, claim, void warranties |
| `can_send_branded_email` | Super Admin, Admin, Manager, Front Desk, Technician | Send branded emails |

## Routes

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| POST | `/tickets/<id>/warranty` | can_manage_warranty | Create warranty record |
| POST | `/tickets/<id>/warranty/send-email` | can_send_branded_email | Send warranty email |
| POST | `/tickets/<id>/warranty/claim` | can_manage_warranty | Record warranty claim |
| POST | `/tickets/<id>/warranty/void` | can_manage_warranty | Void warranty |
| POST | `/tickets/<id>/send-branded-email` | can_send_branded_email | Send branded update email |

## Migration

**File**: `migrations/versions/a1b2c3d4e5f6_phase17_warranty_aftercare.py`

**Changes**:
- Creates `ticket_warranties` table
- Adds `default_warranty_days` and `default_warranty_terms` columns to `companies` table

## Internationalization

All warranty UI strings, flash messages, and email subjects are marked for translation with Flask-Babel. Both English and Spanish translations are included.

## Parts History Awareness

When viewing a warranted ticket, staff can see:
- The parts that were used on the repair (auto-populated from stock reservations)
- Prior warranties on the same device with their parts history
- This enables staff to quickly determine if a return issue is related to previously fitted parts

## Future Extensibility

The warranty architecture is designed to support future enhancements:
- **Return repair workflow**: Prior warranty visibility makes it easy to link new tickets to past repairs
- **Warranty reporting**: Active/expired warranties can be queried for dashboard KPIs
- **Automated expiry notifications**: The `expire_warranties()` function and expiry reminder email template are ready
- **SMTP/SendGrid integration**: The branded email service has clean extension points for real mail transports
