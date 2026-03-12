from datetime import datetime
from decimal import Decimal

from app.models import Quote


def compute_option_total(option) -> Decimal:
    total = Decimal("0")
    for line in option.lines:
        qty = Decimal(str(line.quantity or 0))
        unit = Decimal(str(line.unit_price or 0))
        total += qty * unit
    return total


def compute_quote_totals(quote: Quote):
    per_option = []
    for option in quote.options:
        per_option.append({"option": option, "total": compute_option_total(option)})
    quote_total = max((item["total"] for item in per_option), default=Decimal("0"))
    return per_option, quote_total


def set_quote_status(quote: Quote, status: str):
    quote.status = status
    if status == "sent":
        quote.sent_at = datetime.utcnow()
