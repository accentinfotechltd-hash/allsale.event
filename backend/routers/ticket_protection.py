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
# Admin endpoints — list / approve / deny
# ---------------------------------------------------------------------------
async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


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
    claim = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Claim is already {claim['status']}")

    # Mark the claim approved and flip the booking into the refund pipeline.
    # The actual Stripe refund is processed by the admin via the existing
    # /admin → Bookings panel (one-click "Issue refund"). We just stage the
    # ticket for refund here so the approval is auditable and the seat hold
    # can be released.
    await db.protection_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {
            "status": "approved",
            "admin_note": (payload.admin_note or "").strip() or None,
            "decided_at": utc_now().isoformat(),
            "decided_by": user["user_id"],
        }},
    )
    await db.bookings.update_one(
        {"booking_id": claim["booking_id"]},
        {"$set": {
            "protection_claim_approved": True,
            "protection_claim_id": claim_id,
            "refund_requested_at": utc_now().isoformat(),
            "refund_reason": "ticket_protection_claim_approved",
        }},
    )
    logger.info(f"[protection] claim approved {claim_id} — booking {claim['booking_id']} staged for refund")
    return {"ok": True, "next_step": "Issue the Stripe refund from /admin → Bookings → Refund."}


@router.post("/admin/ticket-protection/claims/{claim_id}/deny")
async def deny_claim(claim_id: str, payload: DecisionIn, user: dict = Depends(_require_admin)) -> Dict[str, Any]:
    claim = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Claim is already {claim['status']}")
    await db.protection_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {
            "status": "denied",
            "admin_note": (payload.admin_note or "").strip() or None,
            "decided_at": utc_now().isoformat(),
            "decided_by": user["user_id"],
        }},
    )
    return {"ok": True}
