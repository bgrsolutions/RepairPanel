"""Shared document/print helpers for quotes, tickets, labels."""
import base64
import io

from app.extensions import db
from app.models import Branch, Company


def resolve_branch_identity(branch):
    """Return a dict with branch + company identity for document rendering."""
    if not branch:
        return {
            "company_name": "IRONCore Repairs",
            "trading_name": "",
            "cif_nif": "",
            "branch_name": "",
            "branch_code": "",
            "address": "",
            "phone": "",
            "email": "",
            "quote_terms": "",
            "repair_terms": "",
            "document_footer": "",
        }

    company = branch.company if branch.company_id else None
    return {
        "company_name": company.display_name if company else "IRONCore Repairs",
        "legal_name": company.legal_name if company else "",
        "trading_name": company.trading_name if company else "",
        "cif_nif": company.cif_nif if company else "",
        "branch_name": branch.name,
        "branch_code": branch.code,
        "address": branch.full_address,
        "phone": branch.phone or (company.phone if company else ""),
        "email": branch.email or (company.email if company else ""),
        "website": company.website if company else "",
        "quote_terms": company.default_quote_terms if company else "",
        "repair_terms": company.default_repair_terms if company else "",
        "document_footer": company.document_footer if company else "",
        "ticket_prefix": branch.ticket_prefix or "",
        "quote_prefix": branch.quote_prefix or "",
    }


def generate_qr_data_uri(text, box_size=4, border=1):
    """Generate a QR code as a base64 data URI for embedding in HTML."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=box_size, border=border)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return None


def customer_block(customer):
    """Return a dict with customer identity for document rendering."""
    if not customer:
        return {"name": "Walk-in Customer", "is_business": False}

    result = {
        "name": customer.full_name,
        "display_name": customer.display_name,
        "phone": customer.phone or "",
        "email": customer.email or "",
        "is_business": customer.is_business,
    }
    if customer.is_business:
        result.update({
            "company_name": customer.company_name or "",
            "cif_vat": customer.cif_vat or "",
            "billing_address": customer.billing_address,
            "billing_email": customer.billing_email or "",
            "billing_phone": customer.billing_phone or "",
        })
    return result
