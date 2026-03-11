# IRONCore Project Scope

## 1. Project Summary
IRONCore is a production-grade repair operations platform for electronics repair businesses. The system will centralize ticket management, intake, diagnostics, quote approvals, parts operations, branch workflows, and customer-facing tracking while remaining integration-ready for future invoicing workflows in Odoo.

## 2. Business Goals
- Reduce repair turnaround time through structured workflows and technician queues.
- Improve front-desk speed and consistency during intake.
- Increase quote approval conversion through clear customer approvals.
- Improve parts availability and ordered-parts traceability.
- Provide branch-level operational visibility with shared customer/device history.
- Establish an auditable and secure process for sensitive repair operations.

## 3. System Scope
### In Scope
- Multi-branch repair ticket operations.
- Internal staff dashboard and role-based access.
- Device intake (internal + public + kiosk mode).
- Diagnostics, quote management, approval flows, and QA workflows.
- Parts inventory, reservations, and ordered-parts lifecycle tracking.
- Label generation, barcode/QR support, and printable documents.
- Customer-facing status portal and quote approval portal.
- Audit logs, soft deletes, multilingual support (EN/ES), and Dockerized deployment.
- Odoo integration readiness via export/integration layer (no accounting engine).

### Out of Scope (Initial Product)
- Full accounting, tax engine, invoicing, and payment reconciliation.
- Native mobile apps (web responsive app only in initial phases).
- Marketplace/e-commerce storefront.
- Supplier API auto-ordering automation (planned extension).

## 4. Constraints
- Flask-based architecture is mandatory.
- Data model must support PostgreSQL and MariaDB compatibility.
- Initial file storage local; must abstract to S3/MinIO later.
- Internationalization from day one (minimum English and Spanish).
- Production security controls required from first implementation phase.

## 5. Non-Goals
- Replacing ERP responsibilities (accounting remains in Odoo).
- Building generalized CRM/ERP beyond repair operations.
- Supporting unstructured/no-audit repair workflows.

## 6. Success Criteria
- End-to-end ticket lifecycle operational across branches.
- <3 minute average reception check-in for common devices.
- Full ordered-parts traceability from request to installation.
- Quote revision and approval history auditable and customer-visible where required.
- High-confidence data export payloads for future Odoo sync.
- Documentation-driven governance adopted by team before coding starts.

## 7. Assumptions
- Repair shops have stable network access for branch operations.
- Staff can use browser-based tablet/desktop interfaces.
- Existing customer/device data migration is out of scope for initial MVP unless separately scoped.
- Email infrastructure is available before notification go-live.

## 8. Risks and Open Questions
- **Risk**: Sensitive credentials handling may require stricter compliance controls depending on jurisdiction.
- **Risk**: Label printer protocol differences may increase integration complexity.
- **Risk**: Public portal abuse/spam requires anti-automation controls tuning.
- **Open Question**: Should branch ticket numbering be globally unique or branch-prefixed?
- **Open Question**: Is offline intake mode needed for intermittent connectivity sites?
- **Open Question**: What exact Odoo target objects and version will integration use?
