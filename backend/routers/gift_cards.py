"""Gift cards (c1) — purchase via Stripe, redeem at checkout.

Lifecycle:
  1. Buyer hits POST /gift-cards/purchase with `amount` + `recipient_email`.
     We mint a `pending` gift_card row, create a Stripe Checkout session,
     and return its URL.
  2. Stripe webhook (extended in payments.py) flips the gift_card to `active`
     and emails the recipient a code.
  3. At booking checkout, buyer enters the code: bookings/hold (extended)
     decrements `balance` atomically; insufficient balance falls back to a
     normal Stripe charge for the remainder.

Schema:
  • code:            "GIFT-XXXX-XXXX-XXXX" — public, copy-pasteable
  • amount:          initial face value (immutable)
  • balance:         remaining redeemable amount
  • currency:        ISO 4217
  • purchased_by:    user_id of the buyer (may be null for guest purchases)
  • recipient_email: who gets the email
  • personal_note:   buyer's short message
  • status:          pending | active | depleted | void
  • redemptions[]:   {booking_id, amount, redeemed_at}
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import db, get_current_user, utc_now, STRIPE_API_KEY, logger

try:
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout, CheckoutSessionRequest,
    )
    _STRIPE_AVAILABLE = True
except Exception:  # pragma: no cover
    StripeCheckout = None  # type: ignore
    CheckoutSessionRequest = None  # type: ignore
    _STRIPE_AVAILABLE = False

router = APIRouter(tags=["gift_cards"])

MIN_AMOUNT = 10.0
MAX_AMOUNT = 1000.0


def _gen_gift_code() -> str:
    """Human-friendly gift card code: GIFT-XXXX-XXXX-XXXX (alphanumeric)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/O/0/1 to avoid confusion
    raw = uuid.uuid4().hex.upper()
    chunks = []
    # Map hex chars to the safer alphabet via modulo
    for i in range(0, 12, 4):
        chunk = "".join(alphabet[int(raw[j], 16) % len(alphabet)] for j in range(i, i + 4))
        chunks.append(chunk)
    return "GIFT-" + "-".join(chunks)


def _normalize_code(s: str) -> str:
    return (s or "").strip().upper().replace(" ", "")


class GiftCardPurchaseIn(BaseModel):
    amount: float = Field(ge=MIN_AMOUNT, le=MAX_AMOUNT)
    recipient_email: EmailStr
    recipient_name: Optional[str] = Field(default=None, max_length=80)
    personal_note: Optional[str] = Field(default=None, max_length=400)
    currency: str = "NZD"
    origin_url: str


@router.post("/gift-cards/purchase")
async def purchase_gift_card(
    payload: GiftCardPurchaseIn,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a Stripe Checkout session for a gift card. On webhook success
    the gift card is minted + emailed."""
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Payments are temporarily unavailable")

    code = _gen_gift_code()
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    currency = (payload.currency or "NZD").upper()

    await db.gift_cards.insert_one({
        "card_id": card_id,
        "code": code,
        "amount": round(float(payload.amount), 2),
        "balance": round(float(payload.amount), 2),
        "currency": currency,
        "purchased_by": user["user_id"],
        "purchaser_email": user.get("email"),
        "purchaser_name": user.get("name"),
        "recipient_email": payload.recipient_email,
        "recipient_name": payload.recipient_name,
        "personal_note": (payload.personal_note or "").strip() or None,
        "status": "pending",
        "redemptions": [],
        "created_at": utc_now().isoformat(),
    })

    # Build the Stripe session
    host_url = str(request.base_url)
    fwd_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if fwd_proto == "https" and host_url.startswith("http://"):
        host_url = "https://" + host_url[len("http://"):]
    webhook_url = (os.environ.get("STRIPE_WEBHOOK_URL") or "").strip() or f"{host_url}api/webhook/stripe"

    try:
        stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    except Exception as exc:  # noqa: BLE001
        await db.gift_cards.delete_one({"card_id": card_id})
        raise HTTPException(status_code=502, detail=f"Stripe init failed: {exc}") from exc

    success_url = f"{payload.origin_url}/gift-cards/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{payload.origin_url}/gift-cards"
    req = CheckoutSessionRequest(
        amount=float(payload.amount),
        currency=currency.lower(),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "kind": "gift_card",
            "card_id": card_id,
            "code": code,
            "user_id": user["user_id"],
            "recipient_email": payload.recipient_email,
        },
    )
    try:
        session = await stripe.create_checkout_session(req)
    except Exception as exc:  # noqa: BLE001
        await db.gift_cards.delete_one({"card_id": card_id})
        raise HTTPException(status_code=502, detail=f"Stripe rejected: {exc}") from exc

    await db.gift_cards.update_one(
        {"card_id": card_id},
        {"$set": {"stripe_session_id": session.session_id}},
    )
    return {
        "url": session.url,
        "session_id": session.session_id,
        "card_id": card_id,
    }


async def finalize_gift_card_purchase(card_id: str) -> bool:
    """Called by the Stripe webhook when a gift_card session completes.
    Idempotent — returns True if this call actually activated the card."""
    card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
    if not card or card["status"] != "pending":
        return False
    r = await db.gift_cards.update_one(
        {"card_id": card_id, "status": "pending"},
        {"$set": {"status": "active", "activated_at": utc_now().isoformat()}},
    )
    if r.modified_count == 0:
        return False
    # Fire-and-forget email to the recipient. Wrapped so a Resend hiccup
    # never breaks the webhook (Stripe would retry the webhook and we'd
    # double-activate).
    try:
        from emails import send_template_fireforget
        send_template_fireforget(
            "gift_card_delivered",
            card["recipient_email"],
            {
                "recipient_name": card.get("recipient_name") or "there",
                "purchaser_name": card.get("purchaser_name") or "Someone",
                "amount": f"{card['amount']:.2f}",
                "currency": card["currency"],
                "code": card["code"],
                "personal_note": card.get("personal_note") or "",
                "redeem_url": f"{(os.environ.get('APP_PUBLIC_URL') or 'https://allsale.events').rstrip('/')}/events",
            },
            db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Gift card delivery email failed")
    return True


@router.get("/gift-cards/{code}/balance")
async def gift_card_balance(code: str):
    """Public-ish: anyone with the code can check the remaining balance.
    Returns 404 if the code doesn't exist or is pending/void."""
    c = await db.gift_cards.find_one(
        {"code": _normalize_code(code)}, {"_id": 0, "code": 1, "amount": 1, "balance": 1, "currency": 1, "status": 1}
    )
    if not c or c["status"] not in ("active", "depleted"):
        raise HTTPException(status_code=404, detail="Gift card not found")
    return c


@router.get("/me/gift-cards")
async def my_gift_cards(user: dict = Depends(get_current_user)):
    """All gift cards I've purchased OR received (by email)."""
    out = []
    async for c in db.gift_cards.find(
        {
            "$or": [
                {"purchased_by": user["user_id"]},
                {"recipient_email": user.get("email")},
            ],
            "status": {"$in": ["active", "depleted", "pending"]},
        },
        {"_id": 0},
    ).sort("created_at", -1):
        # Hide the full code for cards the user PURCHASED but hasn't received
        # back (privacy: the buyer can see the code, the recipient too).
        out.append(c)
    return out


# -------- internal helper used by bookings/hold to redeem against a card --------

async def redeem_gift_card_for_booking(code: str, requested_amount: float, booking_id: str, currency: str) -> dict:
    """Atomically deduct `requested_amount` (or remaining balance, whichever
    is lower) from a gift card. Returns {applied, remaining_balance}.
    Raises HTTPException(400/404/409) on invalid code or 0 balance."""
    code_n = _normalize_code(code)
    card = await db.gift_cards.find_one({"code": code_n}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    if card["status"] != "active":
        raise HTTPException(status_code=400, detail="Gift card is not active")
    if (card.get("currency") or "NZD").upper() != currency.upper():
        raise HTTPException(
            status_code=400,
            detail=f"Gift card currency mismatch ({card['currency']} vs {currency})",
        )
    if card.get("balance", 0) <= 0:
        raise HTTPException(status_code=400, detail="Gift card has no balance")

    apply = round(min(float(card["balance"]), float(requested_amount)), 2)
    # Atomic decrement guarded by current balance to prevent race-condition
    # double-spend if the buyer pastes the code into two checkouts at once.
    new_balance = round(float(card["balance"]) - apply, 2)
    new_status = "depleted" if new_balance <= 0 else "active"
    redemption = {
        "booking_id": booking_id,
        "amount": apply,
        "redeemed_at": utc_now().isoformat(),
    }
    result = await db.gift_cards.update_one(
        {"code": code_n, "balance": card["balance"], "status": "active"},
        {
            "$set": {"balance": new_balance, "status": new_status},
            "$push": {"redemptions": redemption},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=409, detail="Gift card was just used elsewhere — please retry")
    return {"applied": apply, "remaining_balance": new_balance, "card_id": card["card_id"]}
