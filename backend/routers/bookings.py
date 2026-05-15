"""Booking endpoints: create hold, get, list mine."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from core import (
    db, get_current_user, utc_now, gen_qr_data_url, booking_to_public, HOLD_MINUTES,
)
from models import HoldIn

router = APIRouter(tags=["bookings"])


@router.post("/bookings/hold")
async def create_hold(payload: HoldIn, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    expires = utc_now() + timedelta(minutes=HOLD_MINUTES)
    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"

    if event.get("has_seatmap"):
        seats = payload.seats or []
        if not seats:
            raise HTTPException(status_code=400, detail="No seats selected")
        aisles = set(event.get("aisles") or [])
        bad = [s for s in seats if s in aisles]
        if bad:
            raise HTTPException(status_code=400, detail=f"Seats are aisles: {bad}")

        now_iso = utc_now().isoformat()
        await db.seat_reservations.delete_many(
            {"event_id": payload.event_id, "status": "held", "expires_at": {"$lt": now_iso}}
        )

        # Atomic claim via unique compound index (event_id, seat_id)
        claimed = []
        try:
            for sid in seats:
                await db.seat_reservations.insert_one({
                    "event_id": payload.event_id, "seat_id": sid,
                    "booking_id": booking_id, "user_id": user["user_id"],
                    "status": "held", "expires_at": expires.isoformat(),
                    "created_at": utc_now().isoformat(),
                })
                claimed.append(sid)
        except DuplicateKeyError:
            if claimed:
                await db.seat_reservations.delete_many(
                    {"event_id": payload.event_id, "seat_id": {"$in": claimed}, "booking_id": booking_id}
                )
            raise HTTPException(status_code=409, detail="One or more seats just got taken. Please pick others.")

        amount = round(event.get("seat_price", 0.0) * len(seats), 2)
        tier_name = "Seat Selection"
        quantity = len(seats)
    else:
        tier = next((t for t in event.get("tiers", []) if t.get("name") == payload.tier_name), None)
        if not tier:
            raise HTTPException(status_code=400, detail="Invalid tier")
        quantity = payload.quantity
        if quantity < 1 or quantity > 10:
            raise HTTPException(status_code=400, detail="Quantity 1-10")
        sold = 0
        async for b in db.bookings.find(
            {"event_id": payload.event_id, "tier_name": payload.tier_name, "status": {"$in": ["paid", "confirmed"]}},
            {"_id": 0},
        ):
            sold += b.get("quantity", 0)
        held_qty = 0
        async for h in db.seat_holds.find(
            {"event_id": payload.event_id, "tier_name": payload.tier_name, "expires_at": {"$gte": utc_now().isoformat()}},
            {"_id": 0},
        ):
            held_qty += h.get("quantity", 0)
        if sold + held_qty + quantity > tier.get("capacity", 0):
            raise HTTPException(status_code=409, detail="Sold out for this tier")
        amount = round(tier["price"] * quantity, 2)
        tier_name = payload.tier_name
        seats = []

    hold_doc = {
        "booking_id": booking_id, "event_id": payload.event_id, "user_id": user["user_id"],
        "tier_name": tier_name, "quantity": quantity, "seats": seats,
        "expires_at": expires.isoformat(), "created_at": utc_now().isoformat(),
    }
    if not event.get("has_seatmap"):
        await db.seat_holds.insert_one(hold_doc)

    booking_doc = {
        "booking_id": booking_id, "event_id": payload.event_id,
        "event_title": event["title"], "event_date": event["date"],
        "event_venue": event["venue"], "event_image": event["image_url"],
        "user_id": user["user_id"], "user_email": user["email"], "user_name": user["name"],
        "tier_name": tier_name, "quantity": quantity, "seats": seats,
        "amount": amount, "currency": "usd", "status": "pending",
        "hold_expires_at": expires.isoformat(), "created_at": utc_now().isoformat(),
    }
    await db.bookings.insert_one(booking_doc)

    return booking_to_public(booking_doc)


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user: dict = Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if b.get("status") == "paid" and not b.get("qr_code"):
        qr_payload = f"AURA|{b['booking_id']}|{b['event_id']}|{b['user_id']}"
        b["qr_code"] = gen_qr_data_url(qr_payload)
        await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"qr_code": b["qr_code"]}})
    return booking_to_public(b)


@router.get("/me/bookings")
async def my_bookings(user: dict = Depends(get_current_user)):
    items = []
    async for b in db.bookings.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        items.append(b)
    return items
