"""Stripe checkout: create session, poll status, webhook."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

try:
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout, CheckoutSessionRequest,
    )
    _STRIPE_AVAILABLE = True
except Exception as _stripe_import_err:  # pragma: no cover
    StripeCheckout = None  # type: ignore
    CheckoutSessionRequest = None  # type: ignore
    _STRIPE_AVAILABLE = False
    _STRIPE_IMPORT_ERROR = str(_stripe_import_err)

from core import db, get_current_user, utc_now, gen_qr_data_url, STRIPE_API_KEY, logger
from models import CheckoutIn
from emails import send_template_fireforget
from routers.ws_seats import notify_seats, notify_tier_refresh

router = APIRouter(tags=["payments"])


async def _send_booking_confirmation_email(booking_id: str) -> None:
    """Fetch fresh booking + event and queue confirmation email (non-blocking)."""
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking or not booking.get("user_email"):
        return
    event = await db.events.find_one({"event_id": booking["event_id"]}, {"_id": 0}) or {}
    ctx = {
        "user_name": booking.get("user_name", ""),
        "user_email": booking["user_email"],
        "booking_id": booking_id,
        "event_id": booking["event_id"],
        "event_title": booking.get("event_title") or event.get("title", ""),
        "event_date": event.get("date", ""),
        "venue": event.get("venue", ""),
        "city": event.get("city", ""),
        "seats": booking.get("seats") or [],
        "tier_name": booking.get("tier_name", ""),
        "quantity": booking.get("quantity", 1),
        "amount": booking.get("amount", 0),
    }
    send_template_fireforget("booking_confirmation", booking["user_email"], ctx, db)


@router.post("/checkout/session")
async def checkout_session(payload: CheckoutIn, request: Request, user: dict = Depends(get_current_user)):
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Payments are temporarily unavailable")
    booking = await db.bookings.find_one({"booking_id": payload.booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if booking["status"] == "paid":
        raise HTTPException(status_code=400, detail="Already paid")

    exp = booking["hold_expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < utc_now():
        raise HTTPException(status_code=410, detail="Hold expired")

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    # Currency is set per-event by the organizer. Stripe expects ISO-4217 lowercase.
    event = await db.events.find_one({"event_id": booking["event_id"]}, {"_id": 0}) or {}
    currency = (event.get("currency") or "NZD").lower()

    success_url = f"{payload.origin_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{payload.origin_url}/checkout/{payload.booking_id}"
    req = CheckoutSessionRequest(
        amount=float(booking["amount"]), currency=currency,
        success_url=success_url, cancel_url=cancel_url,
        metadata={
            "booking_id": booking["booking_id"], "event_id": booking["event_id"],
            "user_id": user["user_id"],
        },
    )
    session = await stripe.create_checkout_session(req)

    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "booking_id": booking["booking_id"],
        "user_id": user["user_id"], "amount": booking["amount"], "currency": currency,
        "metadata": req.metadata, "payment_status": "pending", "status": "initiated",
        "created_at": utc_now().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


@router.get("/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: dict = Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Tx not found")
    if tx["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    if tx["payment_status"] in ("paid", "expired", "failed"):
        return {"status": tx["status"], "payment_status": tx["payment_status"], "booking_id": tx["booking_id"]}

    if not _STRIPE_AVAILABLE:
        return {"status": tx.get("status", "initiated"), "payment_status": tx.get("payment_status", "pending"), "booking_id": tx["booking_id"]}
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    try:
        s = await stripe.get_checkout_status(session_id)
        new_status = s.status
        new_pay = s.payment_status
    except Exception as e:
        logger.warning(f"Stripe get_checkout_status failed for {session_id}: {e}")
        return {
            "status": tx.get("status", "initiated"),
            "payment_status": tx.get("payment_status", "pending"),
            "booking_id": tx["booking_id"],
        }
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"status": new_status, "payment_status": new_pay, "updated_at": utc_now().isoformat()}},
    )

    if new_pay == "paid" and tx["payment_status"] != "paid":
        result = await db.bookings.update_one(
            {"booking_id": tx["booking_id"], "status": {"$ne": "paid"}},
            {"$set": {"status": "paid", "paid_at": utc_now().isoformat()}},
        )
        if result.modified_count > 0:
            await db.seat_holds.delete_many({"booking_id": tx["booking_id"]})
            await db.seat_reservations.update_many(
                {"booking_id": tx["booking_id"]},
                {"$set": {"status": "booked", "expires_at": None}},
            )
            qr_payload = f"AURA|{tx['booking_id']}"
            await db.bookings.update_one(
                {"booking_id": tx["booking_id"]},
                {"$set": {"qr_code": gen_qr_data_url(qr_payload)}},
            )
            await _send_booking_confirmation_email(tx["booking_id"])
            logger.info(f"[booking_paid] {tx['booking_id']} — confirmation email queued")
            # Live broadcast — seats went from held → booked
            booking_doc = await db.bookings.find_one({"booking_id": tx["booking_id"]}, {"_id": 0})
            if booking_doc:
                seats = booking_doc.get("seats") or []
                if seats:
                    await notify_seats(booking_doc["event_id"], [{"seat_id": s, "status": "booked"} for s in seats])
                else:
                    await notify_tier_refresh(booking_doc["event_id"])

    return {"status": new_status, "payment_status": new_pay, "booking_id": tx["booking_id"]}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Payments unavailable")
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    try:
        evt = await stripe.handle_webhook(body, sig)
    except Exception as e:
        # Reject with 400 so Stripe knows verification failed and will retry.
        # Returning 200 here would silently swallow forged or replayed requests.
        logger.error(f"Stripe webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    if evt.payment_status == "paid" and evt.session_id:
        booking_id = (evt.metadata or {}).get("booking_id")
        if booking_id:
            result = await db.bookings.update_one(
                {"booking_id": booking_id, "status": {"$ne": "paid"}},
                {"$set": {"status": "paid", "paid_at": utc_now().isoformat()}},
            )
            if result.modified_count > 0:
                await db.seat_holds.delete_many({"booking_id": booking_id})
                await db.seat_reservations.update_many(
                    {"booking_id": booking_id},
                    {"$set": {"status": "booked", "expires_at": None}},
                )
                qr_payload = f"AURA|{booking_id}"
                await db.bookings.update_one(
                    {"booking_id": booking_id},
                    {"$set": {"qr_code": gen_qr_data_url(qr_payload)}},
                )
                await db.payment_transactions.update_one(
                    {"session_id": evt.session_id},
                    {"$set": {"payment_status": "paid", "status": "complete"}},
                )
                await _send_booking_confirmation_email(booking_id)
    return {"ok": True}
