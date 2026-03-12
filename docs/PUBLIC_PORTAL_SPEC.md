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
- Secure lookup via ticket number + secondary verifier (phone/email/token).
- Show only customer-facing status, ETA, branch, and public notes.
- Indicate quote approval needed / waiting for parts / ready for collection.

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
