"""Manual bookings — box office / cash / offline-card sales.

Admins and event organizers (or team members with `manager` rights) can
create bookings directly, bypassing the Stripe checkout flow, for buyers
who are paying on the spot (cash, POS terminal, bank transfer). Two modes:

  • **paid** — booking lands as `status=paid` immediately, seats booked,
    e-ticket PDF emailed to the buyer. Use at the box office when the buyer
    is standing in front of you paying.
  • **hold** — booking lands as `status=manual_hold`, seats blocked for
    24 h, buyer gets a "come pay to confirm" email. Two follow-up endpoints
    flip the hold → paid or cancel it (releasing the seats).

The QR code is generated on transition to `status=paid` so a held ticket
can't be walked in with. Payment method is stamped on the booking doc for
downstream reporting.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from core import (
    db, get_current_user, gen_qr_data_url, seat_price_for, utc_now,
)
from emails import send_template_fireforget

logger = logging.getLogger("aura.manual_bookings")
router = APIRouter(prefix="/organizer", tags=["manual-bookings"])


PAYMENT_METHODS = {"cash", "card_offline"}
MODES = {"paid", "hold"}
MANUAL_HOLD_HOURS = 24


class ManualBookingIn(BaseModel):
    buyer_name: str = Field(min_length=1, max_length=120)
    buyer_email: EmailStr
    buyer_phone: Optional[str] = Field(default=None, max_length=32)
    payment_method: Literal["cash", "card_offline"]
    mode: Literal["paid", "hold"] = "paid"
    # Tier-based events: pick a tier + quantity. Seat-map events: pick seats.
    tier_name: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1, le=50)
    seats: Optional[List[str]] = None
    # Optional override — defaults to face value (tier price × quantity or
    # sum of seat prices). Admin can enter a discounted amount for comps.
    amount_paid: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=500)


async def _load_event_or_404(event_id: str) -> Dict[str, Any]:
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return e


async def _authorize_manage_event(user: dict, event: dict) -> None:
    """Admin or an organizer/team-member with manager+ rights. Same rule
    as the buyer-report + attendee endpoints, so a door-staff-only team
    member can't create backdated comps — only manager+.
    """
    from routers.team import user_can_manage_event
    if user.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Manual bookings require organizer or admin role")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")


def _compute_face_value(event: dict, payload: ManualBookingIn) -> tuple[float, str, int, List[str]]:
    """Return (face_value, tier_name_or_label, quantity, seat_ids). Raises
    HTTPException 400 for shape mismatches (missing seats on a seat-map
    event, wrong tier name, etc.). Does NOT check capacity — that's the
    atomic-claim step below.
    """
    if event.get("has_seatmap"):
        seats = payload.seats or []
        if not seats:
            raise HTTPException(status_code=400, detail="This event uses a seat map — pick at least one seat")
        aisles = set(event.get("aisles") or [])
        bad = [s for s in seats if s in aisles]
        if bad:
            raise HTTPException(status_code=400, detail=f"Seats are aisles / not sellable: {bad}")
        face_value = round(sum(seat_price_for(event, s) for s in seats), 2)
        return face_value, "Seat Selection", len(seats), seats

    # Tier-based flow.
    if not payload.tier_name or not payload.quantity:
        raise HTTPException(status_code=400, detail="Tier name and quantity are required for tier events")
    tier = next((t for t in event.get("tiers", []) if t.get("name") == payload.tier_name), None)
    if not tier:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {payload.tier_name}")
    face_value = round(float(tier.get("price") or 0) * payload.quantity, 2)
    return face_value, payload.tier_name, payload.quantity, []


async def _reserve_seats_or_conflict(
    event_id: str, seats: List[str], booking_id: str, user_id: str, expires_iso: Optional[str], status: str,
) -> None:
    """Atomic seat claim reusing the same compound-unique index the buyer
    hold flow uses. On conflict, releases anything we just claimed so we
    never leak orphaned reservations.
    """
    claimed: List[str] = []
    now_iso = utc_now().isoformat()
    # Sweep expired holds first so a stale hold doesn't block a real sale.
    await db.seat_reservations.delete_many(
        {"event_id": event_id, "status": "held", "expires_at": {"$lt": now_iso}}
    )
    try:
        for sid in seats:
            await db.seat_reservations.insert_one({
                "event_id": event_id,
                "seat_id": sid,
                "booking_id": booking_id,
                "user_id": user_id,
                "status": status,
                "expires_at": expires_iso,
                "created_at": now_iso,
                "manual_booking": True,
            })
            claimed.append(sid)
    except DuplicateKeyError:
        if claimed:
            await db.seat_reservations.delete_many(
                {"event_id": event_id, "seat_id": {"$in": claimed}, "booking_id": booking_id}
            )
        raise HTTPException(status_code=409, detail="One or more seats are no longer available")


async def _check_tier_capacity(event_id: str, tier: dict, requested_qty: int) -> None:
    """Count paid/confirmed bookings + active holds for this tier and reject
    the manual sale if we'd blow past capacity.
    """
    sold = 0
    async for b in db.bookings.find(
        {
            "event_id": event_id,
            "tier_name": tier["name"],
            "status": {"$in": ["paid", "confirmed", "manual_hold"]},
        },
        {"_id": 0, "quantity": 1, "status": 1, "hold_expires_at": 1},
    ):
        # Skip manual_holds whose 24h window already lapsed.
        if b.get("status") == "manual_hold":
            he = b.get("hold_expires_at") or ""
            if he and he < utc_now().isoformat():
                continue
        sold += int(b.get("quantity") or 0)
    # Active buyer-side holds occupy inventory too.
    held_qty = 0
    async for h in db.seat_holds.find(
        {
            "event_id": event_id,
            "tier_name": tier["name"],
            "expires_at": {"$gte": utc_now().isoformat()},
        },
        {"_id": 0, "quantity": 1},
    ):
        held_qty += int(h.get("quantity") or 0)
    if sold + held_qty + requested_qty > int(tier.get("capacity") or 0):
        raise HTTPException(status_code=409, detail=f"Not enough capacity in tier '{tier['name']}'")


def _confirmation_email_ctx(booking: dict, event: dict, currency: str) -> dict:
    return {
        "user_name": booking.get("user_name", ""),
        "user_email": booking["user_email"],
        "booking_id": booking["booking_id"],
        "event_id": booking["event_id"],
        "event_title": booking.get("event_title") or event.get("title", ""),
        "event_date": event.get("date", ""),
        "venue": event.get("venue", ""),
        "city": event.get("city", ""),
        "seats": booking.get("seats") or [],
        "tier_name": booking.get("tier_name", ""),
        "quantity": booking.get("quantity", 1),
        "amount": booking.get("amount", 0),
        "currency": currency,
    }


async def _send_paid_confirmation(booking_id: str) -> None:
    """Reuse the same PDF + template the Stripe path uses so buyers of
    manual bookings get an identical experience.
    """
    from routers.payments import _send_booking_confirmation_email
    try:
        await _send_booking_confirmation_email(booking_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[manual-bookings] confirmation email failed: %s", str(exc)[:200])


# ---------------------------------------------------------------------------
# 1. Create manual booking (paid OR hold)
# ---------------------------------------------------------------------------
@router.post("/events/{event_id}/manual-booking")
async def create_manual_booking(
    event_id: str,
    payload: ManualBookingIn,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if payload.payment_method not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail=f"Payment method must be one of: {sorted(PAYMENT_METHODS)}")
    if payload.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {sorted(MODES)}")

    event = await _load_event_or_404(event_id)
    await _authorize_manage_event(user, event)

    face_value, tier_name, quantity, seat_ids = _compute_face_value(event, payload)
    amount_paid = float(payload.amount_paid) if payload.amount_paid is not None else face_value

    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    hold_expires_iso: Optional[str] = None
    if payload.mode == "hold":
        hold_expires_iso = (now + timedelta(hours=MANUAL_HOLD_HOURS)).isoformat()

    # Reserve inventory FIRST — this is the only path that can fail on
    # conflict so we do it before touching the bookings collection.
    if event.get("has_seatmap"):
        seat_status = "booked" if payload.mode == "paid" else "held"
        seat_expires = None if payload.mode == "paid" else hold_expires_iso
        await _reserve_seats_or_conflict(
            event_id, seat_ids, booking_id, user["user_id"], seat_expires, seat_status,
        )
    else:
        tier = next(t for t in event.get("tiers", []) if t.get("name") == tier_name)
        await _check_tier_capacity(event_id, tier, quantity)

    booking_status = "paid" if payload.mode == "paid" else "manual_hold"
    booking_doc = {
        "booking_id": booking_id,
        "event_id": event_id,
        "event_title": event.get("title") or "",
        "event_date": event.get("date") or "",
        "event_venue": event.get("venue") or "",
        "event_image": event.get("image_url") or "",
        # For lookups: buyer email is the identifier. We synthesise a stable
        # "manual-buyer" user_id so the booking still shows up in the buyer's
        # /me/bookings if they later sign up with the same email.
        "user_id": f"manual_{uuid.uuid4().hex[:10]}",
        "user_email": str(payload.buyer_email).lower(),
        "user_name": payload.buyer_name.strip(),
        "phone": (payload.buyer_phone or "").strip() or None,
        "tier_name": tier_name,
        "quantity": quantity,
        "seats": seat_ids,
        # face_value = organiser's revenue base. amount = what buyer paid.
        # Manual bookings skip Stripe so there's no service_fee gross-up.
        "face_value": face_value,
        "amount": amount_paid,
        "currency": (event.get("currency") or "NZD").upper(),
        "status": booking_status,
        "hold_expires_at": hold_expires_iso,
        "created_at": now.isoformat(),
        # Audit fields — who created this booking and how.
        "manual_booking": True,
        "payment_method": payload.payment_method,
        "manual_notes": (payload.notes or "").strip() or None,
        "created_by_user_id": user["user_id"],
        "created_by_role": user.get("role") or "organizer",
    }
    if payload.mode == "paid":
        booking_doc["paid_at"] = now.isoformat()
        booking_doc["qr_code"] = gen_qr_data_url(f"AURA|{booking_id}")

    await db.bookings.insert_one(booking_doc)

    if payload.mode == "paid":
        await _send_paid_confirmation(booking_id)

    return {
        "ok": True,
        "booking_id": booking_id,
        "status": booking_status,
        "hold_expires_at": hold_expires_iso,
        "face_value": face_value,
        "amount_paid": amount_paid,
        "currency": booking_doc["currency"],
    }


# ---------------------------------------------------------------------------
# 2. Confirm a hold → paid (when cash / card is collected)
# ---------------------------------------------------------------------------
class ConfirmManualIn(BaseModel):
    amount_paid: Optional[float] = Field(default=None, ge=0)
    payment_method: Optional[Literal["cash", "card_offline"]] = None


@router.post("/manual-bookings/{booking_id}/confirm")
async def confirm_manual_booking(
    booking_id: str,
    payload: ConfirmManualIn,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking or not booking.get("manual_booking"):
        raise HTTPException(status_code=404, detail="Manual booking not found")
    if booking.get("status") != "manual_hold":
        raise HTTPException(status_code=400, detail=f"Booking is already {booking.get('status')}")
    event = await _load_event_or_404(booking["event_id"])
    await _authorize_manage_event(user, event)

    now = utc_now()
    update: Dict[str, Any] = {
        "status": "paid",
        "paid_at": now.isoformat(),
        "qr_code": gen_qr_data_url(f"AURA|{booking_id}"),
        "hold_expires_at": None,
        "confirmed_by_user_id": user["user_id"],
    }
    if payload.amount_paid is not None:
        update["amount"] = float(payload.amount_paid)
    if payload.payment_method:
        update["payment_method"] = payload.payment_method
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": update})

    # Flip any held seat_reservations → booked.
    await db.seat_reservations.update_many(
        {"booking_id": booking_id},
        {"$set": {"status": "booked", "expires_at": None}},
    )
    await _send_paid_confirmation(booking_id)
    return {"ok": True, "booking_id": booking_id, "status": "paid"}


# ---------------------------------------------------------------------------
# 3. Cancel a hold (release seats, no email)
# ---------------------------------------------------------------------------
@router.post("/manual-bookings/{booking_id}/cancel")
async def cancel_manual_booking(
    booking_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking or not booking.get("manual_booking"):
        raise HTTPException(status_code=404, detail="Manual booking not found")
    if booking.get("status") != "manual_hold":
        raise HTTPException(status_code=400, detail="Only manual_hold bookings can be cancelled here")
    event = await _load_event_or_404(booking["event_id"])
    await _authorize_manage_event(user, event)

    await db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {"status": "cancelled", "cancelled_at": utc_now().isoformat(), "cancelled_by_user_id": user["user_id"]}},
    )
    await db.seat_reservations.delete_many({"booking_id": booking_id})
    return {"ok": True, "booking_id": booking_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# 4. List manual bookings for an event (auditing / follow-up)
# ---------------------------------------------------------------------------
@router.get("/events/{event_id}/manual-bookings")
async def list_manual_bookings(
    event_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    event = await _load_event_or_404(event_id)
    await _authorize_manage_event(user, event)

    cur = db.bookings.find(
        {"event_id": event_id, "manual_booking": True},
        {"_id": 0},
    ).sort("created_at", -1).limit(500)
    items = [doc async for doc in cur]
    summary: Dict[str, int] = {}
    for b in items:
        s = b.get("status") or "unknown"
        summary[s] = summary.get(s, 0) + 1
    return {"ok": True, "items": items, "summary": summary}
