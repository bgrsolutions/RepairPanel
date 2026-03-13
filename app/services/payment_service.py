from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode


def create_quote_checkout_session(*, quote_id: str, amount_total: Decimal, currency: str, success_url: str, cancel_url: str, stripe_secret_key: str | None = None) -> dict:
    """Foundation-only Stripe session creator.

    Returns a consistent payload structure so routes can store intent safely.
    If Stripe SDK/keys are unavailable, returns a deterministic placeholder URL.
    """
    if stripe_secret_key:
        try:
            import stripe  # type: ignore

            stripe.api_key = stripe_secret_key
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": currency.lower(),
                            "unit_amount": int((amount_total * Decimal("100")).quantize(Decimal("1"))),
                            "product_data": {"name": f"Repair quote {quote_id}"},
                        },
                        "quantity": 1,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"quote_id": quote_id},
            )
            return {"provider": "stripe", "session_id": session.id, "checkout_url": session.url, "is_live": True}
        except Exception:
            pass

    qs = urlencode({"quote": quote_id, "amount": str(amount_total), "currency": currency.upper()})
    return {
        "provider": "stripe",
        "session_id": f"placeholder_{quote_id}",
        "checkout_url": f"/public/quote-payment-placeholder?{qs}",
        "is_live": False,
    }
