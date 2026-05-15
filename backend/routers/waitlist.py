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


def _all_seat_ids(event: dict) -> set[str]:
    """All non-aisle seat IDs in a seatmap event."""
    rows = event.get("seat_rows", 0)
    cols = event.get("seat_cols", 0)
    aisles = set(event.get("aisles") or [])
    out = set()
    for r in range(rows):
        row_letter = chr(65 + r)
        for c in range(1, cols + 1):
            sid = f"{row_letter}-{c}"
            if sid not in aisles:
                out.add(sid)
    return out


async def _occupied_seat_ids(event: dict) -> set[str]:
    """Seat IDs currently locked: booked, or held with non-expired hold."""
    now_iso = utc_now().isoformat()
    occupied = set()
    async for r in db.seat_reservations.find(
        {"event_id": event["event_id"], "status": "booked"},
        {"_id": 0, "seat_id": 1},
    ):
        occupied.add(r["seat_id"])
    async for r in db.seat_reservations.find(
        {"event_id": event["event_id"], "status": "held", "expires_at": {"$gte": now_iso}},
        {"_id": 0, "seat_id": 1},
    ):
        occupied.add(r["seat_id"])
    return occupied


async def _available_seat_ids(event: dict) -> list[str]:
    all_ids = _all_seat_ids(event)
    occupied = await _occupied_seat_ids(event)
    free = sorted(all_ids - occupied)
    return free


async def is_sold_out(event: dict) -> bool:
    """Tier-based or seatmap: sold-out when there's no available capacity at all."""
    if event.get("has_seatmap"):
        return len(await _available_seat_ids(event)) == 0
    for t in event.get("tiers", []):
        if await _tier_remaining(event, t["name"]) > 0:
            return False
    return bool(event.get("tiers"))


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
    """Reserve a pending booking + waitlist offer for the user.

    For tier-based events: pick an offerable tier and create a tier-quantity hold.
    For seatmap events: claim the first N available seats (atomic via unique
    compound index on (event_id, seat_id)). Returns booking_id or None.
    """
    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
    expires = utc_now() + timedelta(minutes=OFFER_TTL_MIN)

    if event.get("has_seatmap"):
        quantity = int(entry.get("quantity") or 1)
        # Try to claim the first `quantity` available seats atomically
        claimed = []
        attempts = 0
        max_attempts = max(20, quantity * 4)
        while len(claimed) < quantity and attempts < max_attempts:
            attempts += 1
            free = await _available_seat_ids(event)
            # Skip any we've already tried
            free = [s for s in free if s not in claimed]
            if not free:
                break
            sid = free[0]
            try:
                await db.seat_reservations.insert_one({
                    "event_id": event["event_id"], "seat_id": sid,
                    "booking_id": booking_id, "user_id": entry["user_id"],
                    "status": "held", "expires_at": expires.isoformat(),
                    "created_at": utc_now().isoformat(),
                    "source": "waitlist",
                })
                claimed.append(sid)
            except DuplicateKeyError:
                # Someone else just took it; loop to try the next.
                continue

        if not claimed:
            return None
        # Settle for partial fulfilment if necessary (e.g., they asked for 2,
        # we could only get 1). Better partial offer than nothing.
        amount = round(event.get("seat_price", 0.0) * len(claimed), 2)
        tier_name = "Seat Selection"
        seats = claimed
        quantity = len(claimed)
    else:
        tier = await _find_offerable_tier(event, entry.get("tier_preference"))
        if not tier:
            return None
        quantity = int(entry.get("quantity") or 1)
        if quantity > await _tier_remaining(event, tier["name"]):
            if 1 <= await _tier_remaining(event, tier["name"]):
                quantity = 1
            else:
                return None
        amount = round(tier["price"] * quantity, 2)
        tier_name = tier["name"]
        seats = []

    await db.bookings.insert_one({
        "booking_id": booking_id, "event_id": event["event_id"],
        "event_title": event["title"], "event_date": event.get("date"),
        "event_venue": event.get("venue"), "event_image": event.get("image_url"),
        "user_id": entry["user_id"], "user_email": entry["user_email"], "user_name": entry["user_name"],
        "tier_name": tier_name, "quantity": quantity, "seats": seats,
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
            "offered_seats": seats if event.get("has_seatmap") else None,
        }},
    )

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
    if not event:
        return None

    now_iso = utc_now().isoformat()
    # Mark expired pending bookings + free their seats
    expired_cursor = db.waitlist_entries.find(
        {"event_id": event_id, "status": "offered", "expires_at": {"$lt": now_iso}},
        {"_id": 0},
    )
    async for e in expired_cursor:
        await db.waitlist_entries.update_one(
            {"waitlist_id": e["waitlist_id"]},
            {"$set": {"status": "expired"}},
        )
        if e.get("booking_id"):
            await db.bookings.update_one(
                {"booking_id": e["booking_id"], "status": "pending"},
                {"$set": {"status": "expired"}},
            )
            # Free seatmap reservations linked to this expired offer
            if event.get("has_seatmap"):
                await db.seat_reservations.delete_many(
                    {"event_id": event_id, "booking_id": e["booking_id"], "status": "held"},
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

    entry = await try_offer_next_in_waitlist(event_id)
    if not entry:
        raise HTTPException(status_code=400, detail="No one on waitlist, or no capacity to offer")
    return entry
