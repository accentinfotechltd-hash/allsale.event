"""Ticket Protection (DIY internal pool variant).

Buyers can OPT-IN at checkout to upgrade their tickets with a refundable
protection upgrade — Allsale collects an extra percentage (default 6.5%)
on top of the ticket total. If the attendee can't make the event (illness,
travel disruption, weather etc.) they file a claim and the admin approves
or denies it from /admin.

This is a DIY implementation — Allsale acts as its own insurance pool. The
collected protection fees accrue to the `insurance_pool_balance` running
total stored on the platform's settings doc. Refunded claims drain that
pool; over time the platform takes any surplus as revenue.

Why not a real insurer (XCover / Booking Protect)?
  • Faster to ship.
  • No partnership negotiation, no per-claim API calls.
  • You can convert to a real partner later by just swapping the
    "approve" handler to call their refund-claim API.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now, logger

# Stripe is optional in dev — guard the import so the rest of the router
# still works when STRIPE_API_KEY isn't set.
try:
    import stripe as _stripe
    _STRIPE = True
except Exception:  # pragma: no cover
    _stripe = None
    _STRIPE = False

router = APIRouter(tags=["ticket_protection"])

# 6.5% by default — matches what major competitors (Booking Protect, XCover) charge.
TICKET_PROTECTION_PCT_BPS = int(os.environ.get("TICKET_PROTECTION_PCT_BPS", "650"))
TICKET_PROTECTION_PCT = TICKET_PROTECTION_PCT_BPS / 10000.0


def compute_protection_amount(subtotal: float) -> float:
    """Return how much extra the buyer pays for opt-in protection."""
    if subtotal <= 0:
        return 0.0
    return round(subtotal * TICKET_PROTECTION_PCT, 2)


# ---------------------------------------------------------------------------
# Public — quote endpoint (frontend uses this on the event detail page)
# ---------------------------------------------------------------------------
@router.get("/ticket-protection/quote")
async def quote_protection(subtotal: float) -> Dict[str, Any]:
    return {
        "subtotal": subtotal,
        "protection_pct_bps": TICKET_PROTECTION_PCT_BPS,
        "protection_amount": compute_protection_amount(subtotal),
        "currency_independent": True,
        "covers": [
            "Illness or injury preventing attendance",
            "Public transport delays / cancellations",
            "Severe weather warnings",
            "Family emergency or bereavement",
            "Mandatory work / school commitments",
        ],
    }


# ---------------------------------------------------------------------------
# Buyer endpoints — file a claim
# ---------------------------------------------------------------------------
class ClaimIn(BaseModel):
    booking_id: str
    reason: str = Field(min_length=10, max_length=2000)
    evidence_url: Optional[str] = Field(default=None, max_length=500)


@router.post("/ticket-protection/claims")
async def file_claim(payload: ClaimIn, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    booking = await db.bookings.find_one({"booking_id": payload.booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your booking")
    if not booking.get("protection_opted"):
        raise HTTPException(status_code=400, detail="This booking did not include Ticket Protection")
    if booking.get("status") not in ("paid", "confirmed"):
        raise HTTPException(status_code=400, detail="Booking is not in a refundable state")
    # Idempotent: don't allow two open claims for the same booking.
    existing = await db.protection_claims.find_one(
        {"booking_id": payload.booking_id, "status": {"$in": ["pending", "approved"]}}, {"_id": 0}
    )
    if existing:
        return existing
    claim_id = f"clm_{uuid.uuid4().hex[:12]}"
    doc = {
        "claim_id": claim_id,
        "booking_id": payload.booking_id,
        "user_id": user["user_id"],
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "event_id": booking.get("event_id"),
        "event_title": booking.get("event_title"),
        "amount": float(booking.get("amount") or 0),
        "currency": booking.get("currency", "NZD"),
        "reason": payload.reason.strip(),
        "evidence_url": payload.evidence_url,
        "status": "pending",
        "created_at": utc_now().isoformat(),
    }
    await db.protection_claims.insert_one(doc)
    logger.info(f"[protection] claim filed {claim_id} for booking {payload.booking_id}")
    return doc


@router.get("/ticket-protection/claims/mine")
async def my_claims(user: dict = Depends(get_current_user)) -> List[Dict[str, Any]]:
    cur = db.protection_claims.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return [doc async for doc in cur]


# ---------------------------------------------------------------------------
# Admin P&L stats — read-only dashboard widget
# ---------------------------------------------------------------------------
@router.get("/admin/ticket-protection/stats")
async def admin_protection_stats(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Aggregate stats for the Admin dashboard P&L widget.

    Premiums = sum of `protection_amount` from confirmed/paid bookings that
    opted in. Claims = sum of refunded `amount` from approved claims. Pool
    balance is the running difference — the platform keeps the surplus as
    revenue once volume stabilizes.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    cutoff = (utc_now() - __import__("datetime").timedelta(days=30)).isoformat()

    # Premiums collected — only bookings actually paid count toward the pool.
    async def _sum(cursor, field):
        total = 0.0
        async for d in cursor:
            total += float(d.get(field) or 0)
        return round(total, 2)

    prem_lifetime = await _sum(
        db.bookings.find(
            {"protection_opted": True, "status": {"$in": ["paid", "confirmed"]}},
            {"_id": 0, "protection_amount": 1},
        ),
        "protection_amount",
    )
    prem_30d = await _sum(
        db.bookings.find(
            {
                "protection_opted": True,
                "status": {"$in": ["paid", "confirmed"]},
                "created_at": {"$gte": cutoff},
            },
            {"_id": 0, "protection_amount": 1},
        ),
        "protection_amount",
    )

    # Pool outflow = ONLY the platform_fee + stripe_fee + protection_premium
    # the platform refunds to the buyer. face_value is the organizer's loss
    # (reversed via destination-charge transfer or held back from payout); it
    # does NOT drain the platform's premium pool.
    # For backwards compat with legacy approved claims (no pool_drain field),
    # we conservatively fall back to claim.amount - booking.face_value via a
    # secondary roundtrip; on a clean DB this stays cheap because approved
    # claims are rare. New approvals stamp pool_drain directly.
    async def _sum_pool_drain(filter_q: Dict[str, Any]) -> float:
        total = 0.0
        async for c in db.protection_claims.find(
            filter_q, {"_id": 0, "pool_drain": 1, "amount": 1, "booking_id": 1}
        ):
            if c.get("pool_drain") is not None:
                total += float(c["pool_drain"])
            else:
                # Legacy claim — derive on the fly.
                bk = await db.bookings.find_one(
                    {"booking_id": c.get("booking_id")},
                    {"_id": 0, "face_value": 1, "amount": 1},
                )
                if bk:
                    total += max(
                        float(bk.get("amount") or c.get("amount") or 0)
                        - float(bk.get("face_value") or 0),
                        0.0,
                    )
                else:
                    total += float(c.get("amount") or 0)
        return round(total, 2)

    claims_lifetime = await _sum_pool_drain({"status": "approved"})
    claims_30d = await _sum_pool_drain({"status": "approved", "decided_at": {"$gte": cutoff}})

    # Also expose the gross-refunded sum so admin can see the full
    # buyer-side impact (= pool_drain + face_value_loss). Per-claim:
    # prefer the explicit `refund_amount` stamped at approve time; fall
    # back to legacy `amount` for old claims.
    gross_refunded_lifetime = 0.0
    async for c in db.protection_claims.find(
        {"status": "approved"}, {"_id": 0, "refund_amount": 1, "amount": 1}
    ):
        gross_refunded_lifetime += float(c.get("refund_amount") or c.get("amount") or 0)
    gross_refunded_lifetime = round(gross_refunded_lifetime, 2)

    # Claim counts by status.
    pending_count = await db.protection_claims.count_documents({"status": "pending"})
    approved_count = await db.protection_claims.count_documents({"status": "approved"})
    denied_count = await db.protection_claims.count_documents({"status": "denied"})

    # Opt-in rate — what % of recent paid bookings included protection?
    paid_30d = await db.bookings.count_documents(
        {"status": {"$in": ["paid", "confirmed"]}, "created_at": {"$gte": cutoff}}
    )
    opted_30d = await db.bookings.count_documents(
        {
            "status": {"$in": ["paid", "confirmed"]},
            "protection_opted": True,
            "created_at": {"$gte": cutoff},
        }
    )
    opt_in_rate_30d = round((opted_30d / paid_30d * 100), 1) if paid_30d > 0 else 0.0

    net_lifetime = round(prem_lifetime - claims_lifetime, 2)
    net_30d = round(prem_30d - claims_30d, 2)
    # Claim ratio — % of premiums paid back as claims. Industry benchmark ~30-50%.
    claim_ratio_lifetime = round((claims_lifetime / prem_lifetime * 100), 1) if prem_lifetime > 0 else 0.0

    return {
        "currency": "NZD",
        "premiums_lifetime": prem_lifetime,
        "premiums_30d": prem_30d,
        "claims_paid_lifetime": claims_lifetime,
        "claims_paid_30d": claims_30d,
        "gross_refunded_lifetime": gross_refunded_lifetime,
        "net_pool_lifetime": net_lifetime,
        "net_pool_30d": net_30d,
        "claim_ratio_pct": claim_ratio_lifetime,
        "opt_in_rate_30d_pct": opt_in_rate_30d,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "denied_count": denied_count,
        "protection_pct_bps": TICKET_PROTECTION_PCT_BPS,
        "notes": "claims_paid = pool drain (platform_fee + stripe_fee + premium). face_value losses are the organizer's, not the pool's.",
    }


# ---------------------------------------------------------------------------
# Admin endpoints — list / approve / deny
# ---------------------------------------------------------------------------
async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# Canned denial reason templates — admin can pick one from a dropdown in the
# UI instead of re-typing the same denial reasoning every time. Used by the
# Admin Ticket Protection tab to populate the "Reason for denial" dropdown.
DENIAL_TEMPLATES: List[Dict[str, str]] = [
    {
        "id": "no_evidence",
        "label": "No evidence provided",
        "text": (
            "Thank you for filing your Ticket Protection claim. Unfortunately we "
            "weren't able to verify your reason for requesting a refund — no "
            "supporting documentation (doctor's note, transit-disruption notice, "
            "etc.) was attached. If you can provide evidence, please reply to "
            "this email and we'll happily reconsider."
        ),
    },
    {
        "id": "not_covered",
        "label": "Reason not covered by Ticket Protection",
        "text": (
            "Thank you for filing your Ticket Protection claim. After review, "
            "the reason provided isn't on our covered-events list (illness, "
            "transit delays, severe weather, family emergency, or mandatory "
            "work/school commitments). If we've misread your situation, please "
            "reply with more detail."
        ),
    },
    {
        "id": "post_event",
        "label": "Filed after event finished",
        "text": (
            "Thank you for filing your Ticket Protection claim. Unfortunately "
            "claims must be submitted before the event start time so the "
            "organiser can resell your seat. We weren't able to approve this "
            "one because the event has already concluded."
        ),
    },
    {
        "id": "change_of_mind",
        "label": "Change of mind (not covered)",
        "text": (
            "Thank you for filing your Ticket Protection claim. Our policy "
            "specifically excludes change-of-mind refunds — Ticket Protection "
            "covers genuine inability-to-attend events. You're welcome to "
            "transfer your ticket to a friend instead via the 'Transfer "
            "ticket' option in your account."
        ),
    },
    {
        "id": "duplicate",
        "label": "Duplicate / already refunded",
        "text": (
            "Thank you for filing your Ticket Protection claim. Our records "
            "show this booking has already been refunded under a previous "
            "request — no further action is required. Please reply if you "
            "believe this is in error."
        ),
    },
    {
        "id": "suspected_abuse",
        "label": "Suspected abuse of the protection programme",
        "text": (
            "Thank you for filing your Ticket Protection claim. After review, "
            "we're unable to approve this request. If you'd like more detail "
            "on the decision, please reply to this email and a member of our "
            "support team will follow up."
        ),
    },
]


@router.get("/admin/ticket-protection/denial-templates")
async def list_denial_templates(user: dict = Depends(_require_admin)) -> Dict[str, Any]:
    """Return the canned denial reason templates so the admin UI can render
    them as a dropdown when denying a claim. Read-only; templates are
    hard-coded so they stay version-controlled."""
    return {"templates": DENIAL_TEMPLATES}


@router.get("/admin/ticket-protection/claims")
async def admin_list_claims(status: Optional[str] = None, user: dict = Depends(_require_admin)) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    cur = db.protection_claims.find(q, {"_id": 0}).sort("created_at", -1).limit(200)
    return [doc async for doc in cur]


class DecisionIn(BaseModel):
    admin_note: Optional[str] = Field(default=None, max_length=1000)


@router.post("/admin/ticket-protection/claims/{claim_id}/approve")
async def approve_claim(claim_id: str, payload: DecisionIn, user: dict = Depends(_require_admin)) -> Dict[str, Any]:
    """One-click approve + Stripe-refund + release-seats + email-buyer.

    Protection promise: when approved, the buyer is **always** refunded the
    full `booking.amount` they were charged (face value + all fees +
    protection premium). This bypasses the event's `refund_policy` window
    because that's literally what they paid 6.5% for.
    """
    claim = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Claim is already {claim['status']}")

    booking = await db.bookings.find_one({"booking_id": claim["booking_id"]}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Already refunded? Idempotent — just mark the claim approved and bail.
    if booking.get("status") == "refunded":
        await db.protection_claims.update_one(
            {"claim_id": claim_id},
            {"$set": {
                "status": "approved",
                "admin_note": (payload.admin_note or "").strip() or None,
                "decided_at": utc_now().isoformat(),
                "decided_by": user["user_id"],
                "refund_amount": booking.get("amount_refunded"),
                "stripe_refund_id": booking.get("stripe_refund_id"),
                "refund_status": "already_refunded",
            }},
        )
        return {
            "ok": True,
            "already_refunded": True,
            "amount_refunded": booking.get("amount_refunded"),
            "stripe_refund_id": booking.get("stripe_refund_id"),
        }

    refund_amount = float(booking.get("amount") or 0)
    if refund_amount <= 0:
        raise HTTPException(status_code=400, detail="Booking has no charge to refund")

    # Pool-drain accounting:
    #   pool_drain    = what comes out of the 6.5% premium pool to make the
    #                   buyer whole on platform_fee + stripe_fee + premium
    #   face_value_loss = the organizer's lost ticket revenue (org never sees
    #                     this; reversed via destination-charge transfer or
    #                     deducted from their next payout)
    face_value = float(booking.get("face_value") or 0)
    pool_drain = round(max(refund_amount - face_value, 0.0), 2)

    is_destination_charge = bool(booking.get("stripe_destination_charge"))

    pi = booking.get("stripe_payment_intent") or booking.get("payment_intent_id")
    session_id = booking.get("stripe_session_id")
    refund_id: Optional[str] = None
    refund_status = "skipped_no_stripe_key"

    if _STRIPE and os.environ.get("STRIPE_API_KEY"):
        _stripe.api_key = os.environ["STRIPE_API_KEY"]
        try:
            kwargs: Dict[str, Any] = {
                "amount": int(round(refund_amount * 100)),
                "metadata": {
                    "claim_id": claim_id,
                    "booking_id": booking["booking_id"],
                    "event_id": claim.get("event_id") or booking.get("event_id"),
                    "user_id": claim["user_id"],
                    "reason": "ticket_protection_claim_approved",
                    "pool_drain": f"{pool_drain:.2f}",
                    "face_value_loss": f"{face_value:.2f}",
                },
                "reason": "requested_by_customer",
            }
            # Destination charges settle the face_value to the connected
            # account at checkout. To make the buyer whole AND claw face_value
            # back from the organizer (and the application_fee back to us),
            # we must set reverse_transfer + refund_application_fee.
            if is_destination_charge:
                kwargs["reverse_transfer"] = True
                kwargs["refund_application_fee"] = True
            if pi:
                kwargs["payment_intent"] = pi
            elif session_id:
                sess = _stripe.checkout.Session.retrieve(session_id)
                if not getattr(sess, "payment_intent", None):
                    raise HTTPException(status_code=400, detail="Stripe charge not yet settled — try again in a few minutes.")
                kwargs["payment_intent"] = sess.payment_intent
            else:
                raise HTTPException(status_code=400, detail="No Stripe charge found on this booking")

            refund = _stripe.Refund.create(**kwargs, idempotency_key=f"protection-refund-{booking['booking_id']}")
            refund_id = refund.get("id") if isinstance(refund, dict) else getattr(refund, "id", None)
            refund_status = "succeeded"
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[protection] stripe refund failed for claim {claim_id}: {exc}")
            raise HTTPException(status_code=500, detail=f"Stripe refund failed: {str(exc)[:200]}")

    now_iso = utc_now().isoformat()

    # Stamp the claim with full audit trail of where the money went.
    await db.protection_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {
            "status": "approved",
            "admin_note": (payload.admin_note or "").strip() or None,
            "decided_at": now_iso,
            "decided_by": user["user_id"],
            "refund_amount": refund_amount,
            "pool_drain": pool_drain,
            "face_value_loss": face_value,
            "stripe_destination_charge": is_destination_charge,
            "stripe_refund_id": refund_id,
            "refund_status": refund_status,
        }},
    )

    # Mark the booking refunded (stamps pool-drain breakdown too so the admin
    # P&L widget can sum pool drains by querying bookings directly if needed).
    await db.bookings.update_one(
        {"booking_id": booking["booking_id"]},
        {"$set": {
            "status": "refunded",
            "amount_refunded": refund_amount,
            "protection_pool_drain": pool_drain,
            "protection_face_value_loss": face_value,
            "stripe_refund_id": refund_id,
            "refund_reason": "ticket_protection_claim_approved",
            "protection_claim_approved": True,
            "protection_claim_id": claim_id,
            "refunded_at": now_iso,
            "refunded_by": user["user_id"],
            "refund_source": "ticket_protection",
        }},
    )

    # Release seats back to inventory so other buyers can grab them.
    try:
        from routers.refunds import _release_seats
        await _release_seats(booking)
    except Exception as exc:  # noqa: BLE001 — non-fatal
        logger.warning(f"[protection] seat release failed for {booking['booking_id']}: {exc}")

    # Fire-and-forget confirmation email to the buyer.
    try:
        from emails import send_template_fireforget
        send_template_fireforget(
            "refund_issued",
            booking.get("user_email"),
            {
                "user_name": booking.get("user_name") or "there",
                "event_title": booking.get("event_title"),
                "amount": refund_amount,
                "currency": booking.get("currency", "NZD"),
                "booking_id": booking["booking_id"],
            },
            db,
        )
    except Exception:  # noqa: BLE001
        pass

    logger.info(
        f"[protection] claim approved + refunded {claim_id} → "
        f"booking {booking['booking_id']} → refund {refund_id} "
        f"(${refund_amount:.2f} = ${pool_drain:.2f} pool + ${face_value:.2f} org loss)"
    )
    return {
        "ok": True,
        "amount_refunded": refund_amount,
        "pool_drain": pool_drain,
        "face_value_loss": face_value,
        "stripe_destination_charge": is_destination_charge,
        "stripe_refund_id": refund_id,
        "refund_status": refund_status,
    }


@router.post("/admin/ticket-protection/claims/{claim_id}/deny")
async def deny_claim(claim_id: str, payload: DecisionIn, user: dict = Depends(_require_admin)) -> Dict[str, Any]:
    claim = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Claim is already {claim['status']}")
    admin_note = (payload.admin_note or "").strip() or None
    await db.protection_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {
            "status": "denied",
            "admin_note": admin_note,
            "decided_at": utc_now().isoformat(),
            "decided_by": user["user_id"],
        }},
    )
    # Fire-and-forget denial email to the buyer using the admin's note as the
    # reason body. Always sent so the buyer isn't left wondering.
    try:
        from emails import send_template_fireforget
        send_template_fireforget(
            "protection_claim_denied",
            claim.get("user_email"),
            {
                "user_name": claim.get("user_name") or "there",
                "event_title": claim.get("event_title") or "your event",
                "reason_text": admin_note or "If you'd like more detail, please reply to this email.",
                "booking_id": claim.get("booking_id"),
            },
            db,
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}
