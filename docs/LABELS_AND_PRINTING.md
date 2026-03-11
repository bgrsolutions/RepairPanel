# IRONCore Labels and Printing

## 1. Label Types
- Device label
- Repair ticket label
- Intake receipt
- Ordered-parts label
- Shelf/bin label
- Collection label
- Customer drop-off receipt

## 2. Standard Label Data Fields
- Ticket number
- Barcode + QR code
- Customer name
- Device model/category
- Fault summary
- Branch name
- Date/time
- Assigned technician (optional)

## 3. Intake Receipts & Print Documents
- Intake summary with disclaimers and signature references.
- Quote PDFs with multilingual terms snapshot.
- Collection handover confirmation printout.

## 4. QR/Barcode Strategy
- QR default payload: signed URL or encoded ticket key.
- Barcode default: ticket code and optional part SKU labels.
- Scanning opens ticket/part record directly in staff UI.

## 5. Printer Abstraction
- Printer profile model supports Zebra/Brother/Dymo/A4 fallback.
- Template renderer outputs target format by profile capability.
- Deferred queue-ready print jobs for future worker support.

## 6. Template System
- Versioned templates per branch + language.
- Template variables mapped from context providers.
- Safe preview mode before publishing template revisions.
