# IRONCore Public Portal Specification

## 1. Public Device Check-In Portal
### Entry Modes
- Generic public URL.
- Branch-specific URL.
- QR-code deep link to branch or campaign.

### Flow
1. Select language and branch.
2. Enter customer details and preferred contact method.
3. Select device category and complete basic intake.
4. Add fault description and optional photos.
5. Accept disclaimers and provide digital signature.
6. Submit and receive pre-check-in reference or ticket number.

## 2. Kiosk Tablet Mode
- Full-screen kiosk lock mode.
- Large controls and guided wizard steps.
- Auto-reset session after submission/timeout.
- Branch branding and multilingual welcome text.

## 3. Public Repair Status Page

### Access Methods
- **Ticket lookup**: `GET /public/status` — form requiring ticket number + verifier (email or phone).
- **Direct token link**: `GET /public/repair/<token>` — secure tokenized URL, no verifier needed. Token is generated automatically when a ticket is created.

### Content Displayed
- Ticket/reference number and device summary.
- Customer-friendly status label (mapped from internal workflow states via `customer_status_service.py`).
- Visual progress indicator (6 steps: Checked In → Diagnosing → Approved → Repairing → Quality Check → Ready).
- Contextual communication summary message explaining what is happening.
- Estimated completion date (if set).
- Quote status with "Review & approve quote" button when approval is pending.
- Customer-visible notes timeline (only `customer`, `customer_update`, `communication` note types).
- Quality checklists (pre-repair and post-repair) with item completion status.
- Contact update form for changing phone/email/collection instructions.

### Status Banners
- **Ready for collection**: Green banner with prominent collection prompt.
- **Pending quote approval**: Amber banner with "Your approval is needed" message and link to quote.
- **All other states**: Indigo summary with contextual explanation message.

### Security
- Internal notes (`note_type="internal"`) are never exposed.
- Technician names, assignment data, and inventory details are never shown.
- Tokens are URL-safe random 24-character strings via `secrets.token_urlsafe(24)`.
- Tokens are stored in `portal_tokens` table with `token_type="public_status_lookup"` and `ticket_id`.

### Staff Integration
- Ticket detail page shows a "Customer Portal" section with the public status URL and copy button.
- Staff can share this link via SMS, email, or on printed receipts.

## 4. Quote Approval Portal
- Tokenized approval links with expiry.
- Display quote options, totals, terms, and accepted method capture.
- Approve/decline with timestamp, IP metadata, language context.

## 5. Security Rules
- Rate limiting, CAPTCHA option for abuse patterns.
- Strict data minimization on all public responses.
- Signed/timed tokens for status and quote actions.
- File upload MIME/type/size validation and malware scanning hook.
- Full audit trail for public submissions and approvals.
