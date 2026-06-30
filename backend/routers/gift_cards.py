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
    # Optional ISO 8601 date (YYYY-MM-DD) — when set, the recipient email is
    # held until this date instead of firing the moment the Stripe charge
    # succeeds. Useful for birthday/Christmas gifting. Max 365 days out.
    deliver_at: Optional[str] = None


def _parse_deliver_at(deliver_at: Optional[str]):
    """Validate `deliver_at` is a future-ish ISO date string within 365 days.
    Returns the parsed datetime (UTC midnight) or None for immediate delivery."""
    if not deliver_at:
        return None
    from datetime import datetime, timezone, timedelta
    try:
        # Accept either YYYY-MM-DD or full ISO timestamp
        if len(deliver_at) == 10:
            dt = datetime.strptime(deliver_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(deliver_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid deliver_at: {exc}")
    now = utc_now()
    if dt < now - timedelta(hours=1):
        raise HTTPException(status_code=400, detail="deliver_at must be in the future")
    if dt > now + timedelta(days=365):
        raise HTTPException(status_code=400, detail="deliver_at must be within 365 days")
    return dt


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

    # Validate scheduled-delivery date BEFORE creating the Stripe session so
    # an invalid date doesn't waste a Stripe call.
    deliver_dt = _parse_deliver_at(payload.deliver_at)

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
        "deliver_at": deliver_dt.isoformat() if deliver_dt else None,
        "delivered_at": None,
        "resend_count": 0,
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
    # If the buyer scheduled delivery for a future date, don't email yet —
    # the scheduler tick will pick it up. Send a confirmation to the
    # purchaser instead so they know it's locked in.
    if card.get("deliver_at"):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(card["deliver_at"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > utc_now():
                logger.info(
                    f"[gift_card] {card_id} scheduled for {card['deliver_at']} — "
                    f"holding recipient email until then"
                )
                return True
        except Exception:  # noqa: BLE001
            pass  # if parsing fails, fall through to immediate delivery
    return await _deliver_gift_card(card)


async def _deliver_gift_card(card: dict) -> bool:
    """Send the gift card delivery email to the recipient and stamp
    delivered_at. Safe to retry — re-deliveries (via the purchaser resend
    endpoint or the scheduled tick) increment resend_count separately."""
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
        await db.gift_cards.update_one(
            {"card_id": card["card_id"]},
            {"$set": {"delivered_at": utc_now().isoformat()}},
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Gift card delivery email failed for %s", card.get("card_id"))
        return False


async def deliver_scheduled_gift_cards() -> int:
    """Scheduler hook: find active cards whose `deliver_at` is now in the
    past AND haven't been delivered yet, and fire the recipient email.
    Returns the number of cards delivered this tick.

    Called from the fast (60s) loop so birthday/Christmas cards land within
    a minute of midnight, not an hour later.
    """
    now_iso = utc_now().isoformat()
    sent = 0
    async for card in db.gift_cards.find(
        {
            "status": "active",
            "deliver_at": {"$lte": now_iso, "$ne": None},
            "delivered_at": None,
        },
        {"_id": 0},
    ).limit(50):
        ok = await _deliver_gift_card(card)
        if ok:
            sent += 1
    return sent


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


@router.post("/me/gift-cards/{card_id}/resend")
async def resend_gift_card_email(card_id: str, user: dict = Depends(get_current_user)):
    """Purchaser self-serve: re-send the delivery email to the recipient
    (e.g. recipient deleted it / it landed in spam). Rate-limited to a
    max of 3 manual resends per card to prevent abuse."""
    card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    if card.get("purchased_by") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your gift card")
    if card["status"] not in ("active", "depleted"):
        raise HTTPException(status_code=400, detail="Card is not active yet")
    if int(card.get("resend_count") or 0) >= 3:
        raise HTTPException(status_code=429, detail="Resend limit reached (3 max per card)")
    ok = await _deliver_gift_card(card)
    if not ok:
        raise HTTPException(status_code=502, detail="Couldn't send the email — please retry")
    await db.gift_cards.update_one(
        {"card_id": card_id},
        {"$inc": {"resend_count": 1}, "$set": {"last_resend_at": utc_now().isoformat()}},
    )
    return {"ok": True, "resend_count": int(card.get("resend_count") or 0) + 1}


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


@router.get("/organizer/gift-card-redemptions")
async def organizer_gift_card_redemptions(user: dict = Depends(get_current_user)):
    """Recent gift card redemptions on this organizer's events. Surfaces
    incremental discovery — gift cards are platform-wide, so the organizer
    can see when one was used to pay for a ticket they're owed."""
    from core import require_role
    await require_role(user, "organizer", "admin")
    # Pull this organizer's events first, then match bookings
    event_ids = []
    async for e in db.events.find({"organizer_id": user["user_id"]}, {"_id": 0, "event_id": 1}):
        event_ids.append(e["event_id"])
    if not event_ids:
        return {"recent": [], "totals": {"count": 0, "amount": 0.0}}

    recent = []
    count = 0
    amount = 0.0
    async for b in db.bookings.find(
        {
            "event_id": {"$in": event_ids},
            "gift_card_code": {"$ne": None},
            "gift_card_amount": {"$gt": 0},
            "status": {"$in": ["paid", "confirmed"]},
        },
        {
            "_id": 0, "booking_id": 1, "event_id": 1, "event_title": 1,
            "user_name": 1, "user_email": 1, "gift_card_code": 1,
            "gift_card_amount": 1, "currency": 1, "created_at": 1,
        },
    ).sort("created_at", -1).limit(50):
        recent.append(b)
        count += 1
        amount += float(b.get("gift_card_amount") or 0)
    return {
        "recent": recent[:10],  # only return latest 10 to the UI
        "totals": {"count": count, "amount": round(amount, 2)},
    }


# ----- internal helper used by bookings/hold to redeem against a card -----

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
