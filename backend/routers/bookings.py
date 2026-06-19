"""Booking endpoints: create hold, get, list mine."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from core import (
    db, get_current_user, utc_now, gen_qr_data_url, booking_to_public, HOLD_MINUTES,
    compute_tier_effective_price, seat_price_for,
)
from fees import compute_fees
from models import HoldIn
from routers.discount_codes import _find_active_code, _check_code_usable, _apply_discount, _normalize_code
from routers.waitlist import try_offer_next_in_waitlist
from routers.ws_seats import notify_seats, notify_tier_refresh

router = APIRouter(tags=["bookings"])


@router.post("/bookings/hold")
async def create_hold(payload: HoldIn, request: Request, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Mark any newly-expired pending holds as expired (so freed capacity flows
    # back to inventory and to waitlist offers).
    now_iso = utc_now().isoformat()
    expired = await db.bookings.update_many(
        {"event_id": payload.event_id, "status": "pending", "hold_expires_at": {"$lt": now_iso}},
        {"$set": {"status": "expired"}},
    )
    # Also clean expired seatmap holds so seats free up immediately
    expired_seats = await db.seat_reservations.delete_many(
        {"event_id": payload.event_id, "status": "held", "expires_at": {"$lt": now_iso}},
    )
    if expired.modified_count > 0 or expired_seats.deleted_count > 0:
        # Capacity just opened up — try to offer the freed spot to next person in queue.
        try:
            await try_offer_next_in_waitlist(payload.event_id)
        except Exception:
            pass

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

        amount = round(sum(seat_price_for(event, s) for s in seats), 2)
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
        unit_price, surging = compute_tier_effective_price(event, tier, sold)
        amount = round(unit_price * quantity, 2)
        tier_name = payload.tier_name
        seats = []

    hold_doc = {
        "booking_id": booking_id, "event_id": payload.event_id, "user_id": user["user_id"],
        "tier_name": tier_name, "quantity": quantity, "seats": seats,
        "expires_at": expires.isoformat(), "created_at": utc_now().isoformat(),
    }
    if not event.get("has_seatmap"):
        await db.seat_holds.insert_one(hold_doc)

    # Auto group-discount — applies when buyer purchases >= min_qty in one go.
    # Stacks BEFORE any promo code so the promo % is applied to the already
    # group-discounted subtotal (a common e-commerce convention).
    group_discount_amount = 0.0
    group_discount_pct = 0.0
    gd = event.get("group_discount") or {}
    try:
        min_qty = int(gd.get("min_qty") or 0)
        pct_off = float(gd.get("pct_off") or 0)
    except (TypeError, ValueError):
        min_qty, pct_off = 0, 0.0
    qty_for_gd = len(seats) if seats else quantity
    if min_qty > 0 and pct_off > 0 and qty_for_gd >= min_qty:
        group_discount_amount = round(amount * (pct_off / 100.0), 2)
        amount = round(max(0, amount - group_discount_amount), 2)
        group_discount_pct = pct_off

    # Apply optional discount code
    subtotal = amount
    discount_code = None
    discount_amount = 0.0
    if payload.code:
        code = _normalize_code(payload.code)
        c = await _find_active_code(code, payload.event_id)
        if not c:
            raise HTTPException(status_code=404, detail="Discount code not found")
        qty_for_check = len(seats) if seats else quantity
        err = _check_code_usable(c, tier_name, qty_for_check)
        if err:
            raise HTTPException(status_code=err[0], detail=err[1])
        discount_amount = _apply_discount(c["kind"], c["value"], subtotal)
        amount = round(max(0, subtotal - discount_amount), 2)
        discount_code = code
        # Atomic uses_count++ guarded by max_uses
        if c.get("max_uses") is not None:
            result = await db.discount_codes.update_one(
                {
                    "code_id": c["code_id"],
                    "$expr": {"$lt": [{"$add": ["$uses_count", qty_for_check]}, {"$add": ["$max_uses", 1]}]},
                },
                {"$inc": {"uses_count": qty_for_check}},
            )
            if result.modified_count == 0:
                raise HTTPException(status_code=409, detail="Code usage limit reached")
        else:
            await db.discount_codes.update_one(
                {"code_id": c["code_id"]}, {"$inc": {"uses_count": qty_for_check}}
            )

    booking_doc = {
        "booking_id": booking_id, "event_id": payload.event_id,
        "event_title": event["title"], "event_date": event["date"],
        "event_venue": event["venue"], "event_image": event["image_url"],
        "user_id": user["user_id"], "user_email": user["email"], "user_name": user["name"],
        "tier_name": tier_name, "quantity": quantity, "seats": seats,
        # `amount` is what we charge Stripe (buyer-total, including fees).
        # `face_value` is the organizer's gross revenue base (paid out 5 days
        # after the event, less platform fee). `service_fee` is the single
        # number shown to the buyer (platform_fee + Stripe processing fee).
        # Discounts apply to `face_value`; if it goes to $0 the booking is a
        # comp and we skip Stripe entirely.
        "subtotal": subtotal,
        "group_discount_amount": group_discount_amount,
        "group_discount_pct": group_discount_pct,
        "discount_code": discount_code, "discount_amount": discount_amount,
        "currency": (event.get("currency") or "NZD").upper(), "status": "pending",
        "hold_expires_at": expires.isoformat(), "created_at": utc_now().isoformat(),
    }
    fee_breakdown = compute_fees(amount, booking_doc["currency"])
    buyer_total = round(fee_breakdown.buyer_total, 2)
    # Apply optional gift card AFTER fees so the buyer sees the dollar
    # off their card-charged total. Stored as `gift_card_amount` for
    # auditing; we DO NOT reduce face_value (organizer still gets paid).
    gift_card_amount = 0.0
    gift_card_code = None
    if payload.gift_card_code:
        from routers.gift_cards import redeem_gift_card_for_booking
        res = await redeem_gift_card_for_booking(
            payload.gift_card_code,
            buyer_total,
            booking_id,
            booking_doc["currency"],
        )
        gift_card_amount = res["applied"]
        gift_card_code = payload.gift_card_code.strip().upper().replace(" ", "")
        buyer_total = round(max(0.0, buyer_total - gift_card_amount), 2)

    booking_doc.update({
        "face_value": round(fee_breakdown.face_value, 2),
        "platform_fee": round(fee_breakdown.platform_fee, 2),
        "stripe_fee_estimated": round(fee_breakdown.stripe_fee, 2),
        "service_fee": round(fee_breakdown.service_fee, 2),
        "amount": buyer_total,
        "gift_card_code": gift_card_code,
        "gift_card_amount": gift_card_amount,
    })

    # Ticket Protection upgrade — opt-in surcharge tacked onto the buyer
    # total. Tracked separately so refund flows and admin reporting can
    # see the protection cut vs. the ticket face value clearly.
    if getattr(payload, "protection_opted", False):
        from routers.ticket_protection import compute_protection_amount
        protection_amount = compute_protection_amount(buyer_total)
        if protection_amount > 0:
            booking_doc["protection_opted"] = True
            booking_doc["protection_amount"] = protection_amount
            booking_doc["amount"] = round(buyer_total + protection_amount, 2)
    await db.bookings.insert_one(booking_doc)

    # Affiliate attribution — pull the cookie (or query param fallback) and
    # attach affiliate_code/id to the booking. Best-effort; never blocks the
    # hold creation.
    try:
        from routers.affiliates import affiliate_code_from_cookie, attribute_booking
        aff_code = affiliate_code_from_cookie(request) or request.query_params.get("aff")
        if aff_code:
            await attribute_booking(booking_doc, aff_code)
            if booking_doc.get("affiliate_id"):
                await db.bookings.update_one(
                    {"booking_id": booking_doc["booking_id"]},
                    {"$set": {
                        "affiliate_code": booking_doc["affiliate_code"],
                        "affiliate_id": booking_doc["affiliate_id"],
                        "affiliate_commission_pct": booking_doc["affiliate_commission_pct"],
                    }},
                )
    except Exception:  # noqa: BLE001
        pass

    # Live broadcast: tell anyone watching the seatmap/tier counts changed
    if seats:
        await notify_seats(payload.event_id, [{"seat_id": s, "status": "held"} for s in seats])
    else:
        await notify_tier_refresh(payload.event_id)

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
