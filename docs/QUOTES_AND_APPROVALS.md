# IRONCore Quotes and Approvals

## 1. Quote Structure
- Quote header linked to ticket, customer, device, branch, currency, language.
- One quote can contain multiple options (e.g., compatible vs OEM part).
- Quote lines support `labour`, `part`, `fixed`, `discount`, `fee`.

## 2. Quote Revisions
- Revisions are immutable snapshots with incremental version number.
- New revision generated for material changes after customer-visible release.
- Full revision history retained for audit and reporting.

## 3. Approval Workflow
- States: draft -> issued -> approved/declined/expired.
- Approval methods:
  - staff manual confirmation,
  - in-store signature,
  - secure portal token link,
  - email approval link (future channel).
- Approval writes timeline event and audit entry.

## 4. Expiry Logic
- Per-quote expiry date required.
- Expired quotes cannot be approved unless manager reopens or reissues revision.
- Ticket workflow responds based on expiry outcome (hold/cancel/requote path).

## 5. Customer Approval Data
- Capture approver name, method, timestamp, IP (public approvals), language.
- Persist accepted terms snapshot and final agreed total.
- Optional decline reason capture for analytics.
