"""Stripe Tax integration — feature-flagged scaffolding.

Stripe Tax automatically calculates VAT/GST/Sales-Tax on each checkout
session based on the buyer's billing address. We integrate it by passing
`automatic_tax: {enabled: true}` to the Checkout Session API.

Activation steps for the operator (do these BEFORE setting STRIPE_TAX_ENABLED=true):
  1. Stripe Dashboard → Tax → Activate Stripe Tax
  2. Add your company's tax registrations (countries you collect for)
  3. Set tax_behavior on the price/amount → "exclusive" (recommended) or "inclusive"
  4. Set env vars: STRIPE_TAX_ENABLED=true
                   STRIPE_TAX_BEHAVIOR=exclusive  (or "inclusive")

When enabled this module:
  - Adds a session-creation path that uses the raw `stripe` SDK with
    `automatic_tax.enabled=true` so Stripe collects the correct tax based
    on the buyer's address.
  - Records the collected tax on the booking as `tax_amount` and
    `tax_breakdown` (list of jurisdiction lines).
  - Excludes the tax from the organizer's payout (the platform is the
    merchant of record and remits tax separately).

This file is intentionally inert until `STRIPE_TAX_ENABLED=true`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stripe-tax"])


def stripe_tax_enabled() -> bool:
    """Single source of truth: whether the Stripe Tax feature is active."""
    return (os.environ.get("STRIPE_TAX_ENABLED", "").strip().lower() in {"1", "true", "yes"})


def stripe_tax_behavior() -> str:
    """`exclusive` (tax added on top of face value) or `inclusive` (already in)."""
    v = (os.environ.get("STRIPE_TAX_BEHAVIOR", "exclusive") or "exclusive").strip().lower()
    return v if v in {"exclusive", "inclusive"} else "exclusive"


async def build_checkout_session_with_tax(
    *,
    booking: dict,
    event: dict,
    success_url: str,
    cancel_url: str,
):
    """Use the raw `stripe` SDK (not the emergent wrapper) so we can pass
    `automatic_tax`. Called by payments.create_checkout_session when
    STRIPE_TAX_ENABLED is on. Returns a dict with {url, session_id}.
    """
    try:
        import stripe  # type: ignore
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    api_key = os.environ.get("STRIPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="STRIPE_API_KEY not configured")
    stripe.api_key = api_key

    currency = (event.get("currency") or "NZD").lower()
    title = (event.get("title") or "Event ticket")[:200]
    qty = int(booking.get("quantity") or 1)
    # Face_value is per-ticket. amount = grossed-up buyer total. For
    # tax-enabled flows we use face_value as the line-item price and let
    # Stripe Tax add VAT/GST on top. Service fees are billed separately
    # as a second line item so they're correctly taxable.
    face_value = float(booking.get("face_value") or booking.get("amount") or 0)
    service_fee = float(booking.get("service_fee") or 0)
    behavior = stripe_tax_behavior()

    line_items = [
        {
            "quantity": qty,
            "price_data": {
                "currency": currency,
                "product_data": {"name": title},
                "unit_amount": int(round(face_value * 100)),
                "tax_behavior": behavior,
            },
        },
    ]
    if service_fee > 0:
        line_items.append({
            "quantity": 1,
            "price_data": {
                "currency": currency,
                "product_data": {"name": "Service fee"},
                "unit_amount": int(round(service_fee * 100)),
                "tax_behavior": behavior,
            },
        })

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        automatic_tax={"enabled": True},
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=booking["booking_id"],
        metadata={
            "booking_id": booking["booking_id"],
            "event_id": booking["event_id"],
            "user_id": booking.get("user_id") or "",
        },
    )
    return {
        "url": session.url,
        "session_id": session.id,
        "amount_total_minor": session.amount_total,
        "currency": session.currency,
    }


async def record_tax_from_session(session_id: str, booking_id: str) -> Optional[dict]:
    """After a session is paid (in the webhook handler or status poll), fetch
    its tax breakdown and stamp it onto the booking. Idempotent.
    """
    if not stripe_tax_enabled():
        return None
    try:
        import stripe  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    api_key = os.environ.get("STRIPE_API_KEY")
    if not api_key:
        return None
    stripe.api_key = api_key
    try:
        sess = stripe.checkout.Session.retrieve(
            session_id,
            expand=["total_details.breakdown.taxes"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[stripe-tax] retrieve failed for {session_id}: {exc}")
        return None
    tax_minor = (getattr(sess, "total_details", None) or {}).get("amount_tax") or 0
    tax_amount = round(tax_minor / 100, 2)
    breakdown_obj = ((getattr(sess, "total_details", None) or {}).get("breakdown") or {}).get("taxes") or []
    breakdown = []
    for t in breakdown_obj:
        try:
            breakdown.append({
                "amount": round((t.get("amount") or 0) / 100, 2),
                "rate_id": (t.get("rate") or {}).get("id"),
                "country": (t.get("rate") or {}).get("country"),
                "percentage": (t.get("rate") or {}).get("percentage"),
                "display_name": (t.get("rate") or {}).get("display_name"),
            })
        except Exception:  # noqa: BLE001
            continue
    await db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "tax_amount": tax_amount,
            "tax_breakdown": breakdown,
            "tax_recorded_at": utc_now().isoformat(),
        }},
    )
    return {"tax_amount": tax_amount, "tax_breakdown": breakdown}


# ---------------------------------------------------------------------------
# Admin diagnostic
# ---------------------------------------------------------------------------

@router.get("/admin/stripe/tax-status")
async def tax_status(user: dict = Depends(get_current_user)):
    """Admin diagnostic — confirm Stripe Tax is wired correctly.

    Returns:
      - enabled (bool): the STRIPE_TAX_ENABLED env flag
      - behavior (str): exclusive | inclusive
      - api_account: Stripe account info (so admin can verify they're
        looking at the right Stripe account)
      - dashboard_url: deep link to the Stripe Tax settings page

    This does NOT enable or disable Stripe Tax — that's a dashboard action.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    info = {
        "enabled": stripe_tax_enabled(),
        "behavior": stripe_tax_behavior(),
        "dashboard_url": "https://dashboard.stripe.com/tax",
        "activation_checklist": [
            "Activate Stripe Tax in the Stripe Dashboard → Tax",
            "Add your tax registrations (each country you collect for)",
            "Set STRIPE_TAX_BEHAVIOR env var (exclusive | inclusive)",
            "Set STRIPE_TAX_ENABLED=true to activate the new checkout path",
        ],
    }
    if stripe_tax_enabled():
        try:
            import stripe  # type: ignore
            stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
            acct = stripe.Account.retrieve()
            info["api_account"] = {
                "id": acct.get("id") if isinstance(acct, dict) else getattr(acct, "id", None),
                "country": acct.get("country") if isinstance(acct, dict) else getattr(acct, "country", None),
                "email": acct.get("email") if isinstance(acct, dict) else getattr(acct, "email", None),
            }
        except Exception as exc:  # noqa: BLE001
            info["api_account_error"] = str(exc)[:200]
    return info


@router.get("/admin/stripe/tax-report")
async def tax_report(days: int = 30, user: dict = Depends(get_current_user)):
    """Rollup of tax collected over `days` days, grouped by jurisdiction.
    Pulls from the `tax_breakdown` we stamp on bookings post-payment."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    from datetime import timedelta
    days = max(1, min(365, int(days or 30)))
    since = (utc_now() - timedelta(days=days)).isoformat()

    rollup: dict = {}
    total_tax = 0.0
    total_paid_with_tax = 0
    async for bk in db.bookings.find(
        {"tax_recorded_at": {"$gte": since}, "status": "paid"},
        {"_id": 0, "tax_amount": 1, "tax_breakdown": 1, "currency": 1},
    ):
        total_tax += float(bk.get("tax_amount") or 0)
        total_paid_with_tax += 1
        for t in (bk.get("tax_breakdown") or []):
            key = f"{t.get('country','??')}:{t.get('display_name','?')}"
            entry = rollup.setdefault(key, {
                "country": t.get("country"),
                "name": t.get("display_name"),
                "rate": t.get("percentage"),
                "amount": 0.0,
            })
            entry["amount"] = round(entry["amount"] + float(t.get("amount") or 0), 2)
    return {
        "days": days,
        "total_tax": round(total_tax, 2),
        "total_paid_with_tax": total_paid_with_tax,
        "by_jurisdiction": list(rollup.values()),
    }
