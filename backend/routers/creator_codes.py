"""Admin-managed creator promo codes.

Admins attach a discount code to a specific creator/influencer for a given
event. Buyers get the discount, and (if a `commission_percent` is set on the
code) the creator earns a commission credited to their `creator_earnings`
ledger on every paid booking that used the code.

How this fits with existing systems:
  • Codes live in the SAME `discount_codes` collection used by the organizer
    self-serve flow, but with two extra fields: `creator_id` and
    `commission_percent`. The booking validation / apply path is unchanged
    (organizers already validate against any discount_codes row for their
    event).
  • To keep the `_find_active_code()` lookup working we store
    `created_by = event.organizer_id` — i.e. the code "belongs" to the
    organizer for discount-lookup purposes, but the `creator_id` field
    records who gets credited.
  • Commission credit fires from `routers/payments.py` on the standard
    `booking_paid` hook, alongside the existing marketing-partner credit.
    Idempotent via a unique `(creator_id, booking_id)` compound index.

Endpoints (admin only):
  POST   /api/admin/events/{event_id}/creator-codes   create
  GET    /api/admin/events/{event_id}/creator-codes   list (+ usage stats)
  DELETE /api/admin/events/{event_id}/creator-codes/{code_id}   deactivate
  GET    /api/admin/creator-codes/users-search?q=     autocomplete users
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

logger = logging.getLogger("aura.creator_codes")
router = APIRouter(prefix="/admin", tags=["admin-creator-codes"])

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


def _admin_only(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


class CreatorCodeIn(BaseModel):
    code: str  # case-insensitive; we uppercase + strip
    creator_email: str  # who gets credit + earnings (we'll resolve to user_id)
    kind: str = "percent"  # "percent" or "flat"
    value: float = Field(..., gt=0)
    commission_percent: Optional[float] = Field(
        None, ge=0, le=100,
        description="If set, creator earns this % on each paid booking using the code.",
    )
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[str] = None  # ISO datetime
    restricted_tiers: List[str] = Field(default_factory=list)


@router.post("/events/{event_id}/creator-codes")
async def admin_create_creator_code(
    event_id: str,
    payload: CreatorCodeIn,
    user: dict = Depends(get_current_user),
):
    """Admin attaches a promo code to a creator for a specific event."""
    _admin_only(user)
    code = (payload.code or "").strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Code must be 2-24 chars A-Z, 0-9, _ or -")
    if payload.kind not in ("percent", "flat"):
        raise HTTPException(status_code=400, detail="Kind must be 'percent' or 'flat'")
    if payload.kind == "percent" and payload.value > 100:
        raise HTTPException(status_code=400, detail="Percent cannot exceed 100")

    ev = await db.events.find_one({"event_id": event_id}, {"_id": 0, "organizer_id": 1, "title": 1, "currency": 1})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    creator_email = (payload.creator_email or "").strip().lower()
    creator = await db.users.find_one(
        {"email": creator_email},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    )
    if not creator:
        raise HTTPException(status_code=404, detail=f"No user found with email {creator_email}")

    # Codes are unique per organizer (existing constraint) — block duplicates.
    if await db.discount_codes.find_one({"code": code, "created_by": ev["organizer_id"]}):
        raise HTTPException(status_code=409, detail=f"A code '{code}' already exists on this organizer's account")

    doc = {
        "code_id": f"dc_{uuid.uuid4().hex[:12]}",
        "code": code,
        "kind": payload.kind,
        "value": float(payload.value),
        "event_id": event_id,
        "max_uses": payload.max_uses,
        "uses_count": 0,
        "expires_at": payload.expires_at,
        "restricted_tiers": payload.restricted_tiers,
        "active": True,
        # `created_by` = organizer so the existing _find_active_code lookup still finds it.
        "created_by": ev["organizer_id"],
        "creator_id": creator["user_id"],
        "creator_email": creator["email"],
        "creator_name": creator.get("name"),
        "commission_percent": payload.commission_percent,
        "admin_created_by": user["user_id"],
        "auto_generated": False,
        "kind_tag": "creator_promo",
        "created_at": utc_now().isoformat(),
    }
    await db.discount_codes.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        "[creator-code] admin %s created %s for creator %s on event %s",
        user["user_id"], code, creator["user_id"], event_id,
    )
    return doc


@router.get("/events/{event_id}/creator-codes")
async def admin_list_creator_codes(event_id: str, user: dict = Depends(get_current_user)):
    """List creator promo codes attached to this event with usage + commission stats."""
    _admin_only(user)
    cur = db.discount_codes.find(
        {"event_id": event_id, "creator_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ).sort("created_at", -1)
    items = [doc async for doc in cur]

    # Aggregate per-code: bookings paid + revenue + commission credited.
    for c in items:
        bookings_agg = await db.bookings.aggregate([
            {"$match": {"discount_code": c["code"], "event_id": event_id, "status": {"$in": ["paid", "confirmed"]}}},
            {"$group": {"_id": None, "count": {"$sum": 1}, "revenue": {"$sum": "$amount"}}},
        ]).to_list(1)
        c["paid_bookings"] = bookings_agg[0]["count"] if bookings_agg else 0
        c["revenue"] = round(bookings_agg[0]["revenue"], 2) if bookings_agg else 0
        earn_agg = await db.creator_earnings.aggregate([
            {"$match": {"code_id": c["code_id"]}},
            {"$group": {"_id": "$status", "amount": {"$sum": "$earning_amount"}}},
        ]).to_list(5)
        c["commission_credited"] = round(sum(e["amount"] for e in earn_agg), 2)
        c["commission_unpaid"] = round(sum(e["amount"] for e in earn_agg if e["_id"] == "unpaid"), 2)
    return {"items": items}


@router.delete("/events/{event_id}/creator-codes/{code_id}")
async def admin_deactivate_creator_code(
    event_id: str,
    code_id: str,
    user: dict = Depends(get_current_user),
):
    """Soft-delete: mark the code inactive. Existing earning rows stay."""
    _admin_only(user)
    res = await db.discount_codes.update_one(
        {"code_id": code_id, "event_id": event_id, "creator_id": {"$exists": True}},
        {"$set": {"active": False, "deactivated_at": utc_now().isoformat()}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Creator code not found")
    return {"deactivated": code_id}


@router.get("/creator-codes/users-search")
async def admin_search_users(q: str = Query(..., min_length=2), user: dict = Depends(get_current_user)):
    """Tiny autocomplete for the 'Pick a creator' modal. Matches name OR email
    prefix. Returns up to 10 results.
    """
    _admin_only(user)
    needle = q.strip()
    if not needle:
        return {"items": []}
    pattern = re.escape(needle)
    cur = db.users.find(
        {"$or": [{"email": {"$regex": pattern, "$options": "i"}},
                 {"name": {"$regex": pattern, "$options": "i"}}]},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1},
    ).limit(10)
    return {"items": [u async for u in cur]}


# -----------------------------------------------------------------------------
# Commission credit hook — called from routers/payments.py on `booking_paid`.
# -----------------------------------------------------------------------------
async def record_creator_earning_for_booking(booking: dict) -> Optional[str]:
    """If a paid booking used a creator-tagged code with `commission_percent`,
    credit the creator's earnings ledger. Idempotent on (creator_id, booking_id).
    """
    code_str = booking.get("discount_code")
    if not code_str:
        return None
    booking_id = booking.get("booking_id")
    if not booking_id:
        return None
    code_doc = await db.discount_codes.find_one(
        {"code": code_str, "event_id": booking.get("event_id"), "creator_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    )
    if not code_doc:
        return None
    pct = code_doc.get("commission_percent")
    if pct is None or pct <= 0:
        return None  # creator wants credit but no payout — that's fine

    amount = float(booking.get("amount") or 0)
    if amount <= 0:
        return None
    earning_amt = round(amount * (pct / 100.0), 2)
    earning_id = f"cren_{uuid.uuid4().hex[:12]}"
    try:
        await db.creator_earnings.insert_one({
            "earning_id": earning_id,
            "creator_id": code_doc["creator_id"],
            "creator_email": code_doc.get("creator_email"),
            "creator_name": code_doc.get("creator_name"),
            "code_id": code_doc["code_id"],
            "code": code_str,
            "booking_id": booking_id,
            "event_id": booking.get("event_id"),
            "booking_amount": amount,
            "commission_percent": pct,
            "earning_amount": earning_amt,
            "currency": booking.get("currency") or "NZD",
            "status": "unpaid",
            "created_at": utc_now(),
        })
    except Exception as exc:  # noqa: BLE001
        from pymongo.errors import DuplicateKeyError
        if isinstance(exc, DuplicateKeyError):
            return None  # webhook replay
        raise
    logger.info(
        "[creator-earning] credited %s to creator %s for booking %s",
        earning_amt, code_doc["creator_id"], booking_id,
    )
    return earning_id
