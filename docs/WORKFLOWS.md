# IRONCore Workflows

## 1. Ticket Lifecycle
New -> Checked In -> Awaiting Diagnosis -> Diagnosed -> Awaiting Quote Approval -> Quote Approved -> Awaiting Parts (optional) -> In Repair -> Testing/QA -> Ready for Collection -> Collected.

Alternative branches:
- Cancelled
- Unrepairable
- Referred Externally
- Warranty Return
- On Hold
- Archived -> closed state, hidden from default ticket list, can be reopened
- Reopened -> returns to appropriate active status (assigned/unassigned based on technician)

## 2. Device Check-In Workflow
1. Identify/create customer.
2. Identify/create device (or bind existing by serial/IMEI).
3. Complete category-specific intake fields.
4. Capture disclaimers and signature.
5. Capture media attachments.
6. Create pre-check-in or full ticket based on branch setting.
7. Print intake receipt + QR ticket label.

## 3. Quote Workflow
1. Add diagnostic findings + recommended actions.
2. Generate quote version with one or multiple options.
3. Set expiry and terms snapshot.
4. Send for approval (portal link/email/in-store).
5. Record outcome: approved/declined/expired. Staff can manually approve or decline from the quote detail page via the staff approval modal.
6. On approval, lock accepted lines and proceed workflow.

## 4. Repair Workflow
1. Assign technician and priority.
2. Reserve/use in-stock parts and/or create part orders.
3. Perform repair actions with technician notes.
4. Attach before/after evidence.
5. Complete post-repair tests.

## 5. Parts Ordering Workflow
1. Create linked part order line from ticket.
2. Assign supplier, qty, cost, ETA, reference.
3. Transition events: ordered -> shipped -> delayed/partial -> arrived.
4. Reserve arrival to ticket; mark installed when used.
5. Auto-update ticket status where branch rule allows.

## 6. QA Workflow
1. Load category-specific checklist template.
2. Execute mandatory checks.
3. Mark pass/fail and record corrective actions.
4. Gate `Ready for Collection` status behind required QA completion.

## 7. Device Collection Workflow
1. Confirm readiness and notification sent.
2. Verify identity/accessories returned.
3. Capture customer signature and handover confirmation.
4. Record external payment handled (Odoo side).
5. Mark ticket collected and finalize timeline event.
