"""Waitlist for sold-out events.

V1 scope: tier-based events only (seatmap waitlists deferred). When a sold-out
event regains capacity, the head of the waitlist is offered a 15-minute hold
on a pending booking — they receive an email with a direct checkout link.

Flow:
1. User clicks "Join waitlist" on a sold-out event → creates `waitlist_entries`
   doc with status=waiting.
2. A spot opens (manual organizer trigger, or auto when a hold expires):
   `_try_offer_next_in_waitlist(event_id)` finds the head, calls
   `_create_waitlist_offer` to insert a pending booking + 15-min hold for them,
   marks the entry "offered", and emails them via `waitlist_spot_opened`.
3. User clicks the email link → /checkout/{booking_id} → completes payment
   normally. The waitlist entry transitions to "claimed" once the booking
   reaches paid status (handled lazily; not critical for MVP).
4. If they don't pay within 15 mins, the next person in line is offered.

Schema (`waitlist_entries`):
- waitlist_id, event_id, user_id, user_email, user_name
- tier_preference (optional, str)
- quantity (default 1, max 4)
- status: "waiting" | "offered" | "claimed" | "expired" | "cancelled"
- requested_at, offered_at?, expires_at?, claimed_booking_id?, booking_id?
- position (computed on read for display)

Unique compound index: (event_id, user_id, status="waiting") prevents dupes.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core import db, get_current_user, require_role, utc_now, HOLD_MINUTES
from emails import send_template_fireforget

router = APIRouter(tags=["waitlist"])

OFFER_TTL_MIN = 15  # waitlist offer expiry (longer than normal HOLD_MINUTES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _tier_remaining(event: dict, tier_name: str) -> int:
    """How many tickets are still available for this tier (paid + held subtracted)."""
    tier = next((t for t in event.get("tiers", []) if t.get("name") == tier_name), None)
    if not tier:
        return 0
    sold = 0
    async for b in db.bookings.find(
        {"event_id": event["event_id"], "tier_name": tier_name, "status": {"$in": ["paid", "confirmed", "pending"]}},
        {"_id": 0, "quantity": 1, "hold_expires_at": 1, "status": 1},
    ):
        # Skip expired pending holds
        if b.get("status") == "pending":
            exp = b.get("hold_expires_at")
            if exp and exp < utc_now().isoformat():
                continue
        sold += b.get("quantity", 0)
    return max(0, tier.get("capacity", 0) - sold)


async def is_sold_out(event: dict) -> bool:
    """Tier-based: sold-out when no tier has any remaining capacity."""
    if event.get("has_seatmap"):
        # Seatmap waitlists not supported in V1
        return False
    for t in event.get("tiers", []):
        if await _tier_remaining(event, t["name"]) > 0:
            return False
    return True


async def _find_offerable_tier(event: dict, preference: Optional[str] = None) -> Optional[dict]:
    """Pick a tier we can hand the waitlist user. Prefer their requested tier."""
    if preference:
        tier = next((t for t in event.get("tiers", []) if t.get("name") == preference), None)
        if tier and await _tier_remaining(event, tier["name"]) >= 1:
            return tier
    # Otherwise cheapest available
    candidates = []
    for t in event.get("tiers", []):
        if await _tier_remaining(event, t["name"]) >= 1:
            candidates.append(t)
    if not candidates:
        return None
    candidates.sort(key=lambda t: t.get("price", 0))
    return candidates[0]


async def _create_waitlist_offer(event: dict, entry: dict) -> Optional[str]:
    """Reserve a pending booking + waitlist offer for the user. Returns booking_id or None."""
    tier = await _find_offerable_tier(event, entry.get("tier_preference"))
    if not tier:
        return None

    quantity = int(entry.get("quantity") or 1)
    if quantity > await _tier_remaining(event, tier["name"]):
        # Try with quantity=1 if their preferred quantity is too large
        if 1 <= await _tier_remaining(event, tier["name"]):
            quantity = 1
        else:
            return None

    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
    expires = utc_now() + timedelta(minutes=OFFER_TTL_MIN)
    amount = round(tier["price"] * quantity, 2)

    await db.bookings.insert_one({
        "booking_id": booking_id, "event_id": event["event_id"],
        "event_title": event["title"], "event_date": event.get("date"),
        "event_venue": event.get("venue"), "event_image": event.get("image_url"),
        "user_id": entry["user_id"], "user_email": entry["user_email"], "user_name": entry["user_name"],
        "tier_name": tier["name"], "quantity": quantity, "seats": [],
        "amount": amount, "subtotal": amount,
        "discount_code": None, "discount_amount": 0,
        "currency": "usd", "status": "pending",
        "hold_expires_at": expires.isoformat(),
        "created_at": utc_now().isoformat(),
        "waitlist_id": entry["waitlist_id"],
    })

    offer_token = uuid.uuid4().hex[:24]
    await db.waitlist_entries.update_one(
        {"waitlist_id": entry["waitlist_id"]},
        {"$set": {
            "status": "offered",
            "offered_at": utc_now().isoformat(),
            "expires_at": expires.isoformat(),
            "booking_id": booking_id,
            "offer_token": offer_token,
        }},
    )

    # Fire email
    send_template_fireforget("waitlist_spot_opened", entry["user_email"], {
        "user_name": entry["user_name"],
        "event_id": event["event_id"],
        "event_title": event["title"],
        "waitlist_token": offer_token,
    }, db)

    return booking_id


async def try_offer_next_in_waitlist(event_id: str) -> Optional[dict]:
    """Look up event + head-of-waitlist; if capacity exists, create an offer.
    Returns the updated entry if offered, else None. Cheap to call repeatedly.
    """
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event or event.get("has_seatmap"):
        return None

    # First flush any expired offers back to "expired" so they don't block the head
    now_iso = utc_now().isoformat()
    expired_cursor = db.waitlist_entries.find(
        {"event_id": event_id, "status": "offered", "expires_at": {"$lt": now_iso}},
        {"_id": 0},
    )
    async for e in expired_cursor:
        await db.waitlist_entries.update_one(
            {"waitlist_id": e["waitlist_id"]},
            {"$set": {"status": "expired"}},
        )
        # Also expire the linked pending booking
        if e.get("booking_id"):
            await db.bookings.update_one(
                {"booking_id": e["booking_id"], "status": "pending"},
                {"$set": {"status": "expired"}},
            )

    # Find the next waiting entry (FIFO)
    head = await db.waitlist_entries.find_one(
        {"event_id": event_id, "status": "waiting"},
        {"_id": 0}, sort=[("requested_at", 1)],
    )
    if not head:
        return None

    booking_id = await _create_waitlist_offer(event, head)
    if not booking_id:
        return None
    return await db.waitlist_entries.find_one({"waitlist_id": head["waitlist_id"]}, {"_id": 0})


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------
class JoinWaitlistIn(BaseModel):
    tier_preference: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=4)


@router.post("/events/{event_id}/waitlist/join")
async def join_waitlist(event_id: str, payload: JoinWaitlistIn, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("has_seatmap"):
        raise HTTPException(status_code=400, detail="Seatmap events don't support waitlists yet")
    if not await is_sold_out(event):
        raise HTTPException(status_code=400, detail="Event still has tickets available")

    waitlist_id = f"wl_{uuid.uuid4().hex[:12]}"
    doc = {
        "waitlist_id": waitlist_id,
        "event_id": event_id,
        "event_title": event["title"],
        "user_id": user["user_id"],
        "user_email": user["email"],
        "user_name": user["name"],
        "tier_preference": payload.tier_preference,
        "quantity": payload.quantity,
        "status": "waiting",
        "requested_at": utc_now().isoformat(),
    }
    try:
        await db.waitlist_entries.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="You're already on this waitlist")
    doc.pop("_id", None)
    return doc


@router.get("/events/{event_id}/waitlist/me")
async def my_waitlist_status(event_id: str, user: dict = Depends(get_current_user)):
    entries = []
    async for e in db.waitlist_entries.find(
        {"event_id": event_id, "user_id": user["user_id"], "status": {"$in": ["waiting", "offered"]}},
        {"_id": 0},
    ).sort("requested_at", 1):
        if e["status"] == "waiting":
            # Compute position (1-indexed) among waiting entries
            position = await db.waitlist_entries.count_documents({
                "event_id": event_id, "status": "waiting",
                "requested_at": {"$lt": e["requested_at"]},
            }) + 1
            e["position"] = position
        entries.append(e)
    return entries


@router.delete("/events/{event_id}/waitlist/me")
async def leave_waitlist(event_id: str, user: dict = Depends(get_current_user)):
    result = await db.waitlist_entries.update_one(
        {"event_id": event_id, "user_id": user["user_id"], "status": "waiting"},
        {"$set": {"status": "cancelled", "cancelled_at": utc_now().isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="No waiting entry to cancel")
    return {"ok": True}


@router.get("/me/waitlist")
async def my_all_waitlist(user: dict = Depends(get_current_user)):
    """All of my active waitlist entries across all events."""
    entries = []
    async for e in db.waitlist_entries.find(
        {"user_id": user["user_id"], "status": {"$in": ["waiting", "offered"]}},
        {"_id": 0},
    ).sort("requested_at", -1):
        entries.append(e)
    return entries


# ---------------------------------------------------------------------------
# Organizer endpoints
# ---------------------------------------------------------------------------
@router.get("/organizer/events/{event_id}/waitlist")
async def organizer_waitlist(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")

    entries = []
    async for e in db.waitlist_entries.find({"event_id": event_id}, {"_id": 0}).sort("requested_at", 1):
        entries.append(e)
    # Summary counts
    counts = {"waiting": 0, "offered": 0, "claimed": 0, "expired": 0, "cancelled": 0}
    for e in entries:
        counts[e.get("status", "waiting")] = counts.get(e.get("status"), 0) + 1
    return {"items": entries, "counts": counts, "sold_out": await is_sold_out(event)}


@router.post("/organizer/events/{event_id}/waitlist/offer-next")
async def organizer_offer_next(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    if event.get("has_seatmap"):
        raise HTTPException(status_code=400, detail="Seatmap events don't support automatic waitlist offers")

    entry = await try_offer_next_in_waitlist(event_id)
    if not entry:
        raise HTTPException(status_code=400, detail="No one on waitlist, or no capacity to offer")
    return entry
