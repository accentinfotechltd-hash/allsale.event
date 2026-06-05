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

# Raw Stripe SDK used as a fallback when `emergentintegrations` chokes on
# metadata fields (its Pydantic model rejects Stripe's StripeObject return
# type and explodes on every reconcile). We use it ONLY for read-only session
# lookups; the create-session flow still uses the higher-level wrapper.
try:
    import stripe as _stripe_sdk  # type: ignore
    _RAW_STRIPE_AVAILABLE = True
except Exception:
    _stripe_sdk = None  # type: ignore
    _RAW_STRIPE_AVAILABLE = False


async def _raw_session_status(session_id: str) -> dict:
    """Pull a Stripe Checkout Session via the raw SDK and return just the
    fields we need — bypasses the emergentintegrations Pydantic model that
    rejects Stripe's `metadata` return type.
    """
    if not _RAW_STRIPE_AVAILABLE:
        raise RuntimeError("Raw stripe SDK not installed")
    _stripe_sdk.api_key = STRIPE_API_KEY
    import asyncio
    sess = await asyncio.to_thread(_stripe_sdk.checkout.Session.retrieve, session_id)
    # `sess` is a StripeObject; both attribute and item access work, but item
    # access is safest because some legacy session fields use dashes.
    def _g(obj, key, default=None):
        # Triple-redundant accessor — handles dict, StripeObject, and any
        # subclass that overrides __getitem__ without exposing .get().
        try:
            v = obj[key]
            return default if v is None else v
        except Exception:  # noqa: BLE001
            try:
                return getattr(obj, key, default)
            except Exception:  # noqa: BLE001
                return default

    metadata_raw = _g(sess, "metadata", {})
    md = dict(metadata_raw) if metadata_raw else {}
    customer_details = _g(sess, "customer_details", None)
    cust_email = _g(customer_details, "email", None) if customer_details else None
    if not cust_email:
        cust_email = _g(sess, "customer_email", None)
    return {
        "status": _g(sess, "status"),
        "payment_status": _g(sess, "payment_status"),
        "amount_total": _g(sess, "amount_total"),
        "currency": _g(sess, "currency"),
        "metadata": md,
        "customer_email": cust_email,
    }


from core import db, get_current_user, utc_now, gen_qr_data_url, STRIPE_API_KEY, logger
from models import CheckoutIn
from emails import send_template_fireforget
from routers.ws_seats import notify_seats, notify_tier_refresh

router = APIRouter(tags=["payments"])


@router.get("/payments/mode")
async def payments_mode():
    """Public endpoint used by the checkout UI to display the truthful Stripe
    mode under the "Pay" button. Returns just `{configured, mode}` — no key
    material, no admin-only fields. Safe to call without auth.
    """
    if not STRIPE_API_KEY:
        return {"configured": False, "mode": None}
    prefix = STRIPE_API_KEY[:8]
    if prefix.startswith("sk_live"):
        mode = "live"
    elif prefix.startswith("sk_test"):
        mode = "test"
    elif prefix.startswith("rk_live"):
        mode = "live (restricted)"
    elif prefix.startswith("rk_test"):
        mode = "test (restricted)"
    else:
        mode = "unknown"
    return {"configured": True, "mode": mode}


@router.get("/payments/health")
async def payments_health(user: dict = Depends(get_current_user)):
    """Admin-only sanity probe — verifies which Stripe environment the
    backend is running in (test vs live) so the launch checklist can confirm
    the live key was picked up after a Railway redeploy.

    Returns mode by inspecting the API key prefix: `sk_test_...` → test,
    `sk_live_...` → live. Never returns the key itself.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not STRIPE_API_KEY:
        return {"configured": False, "mode": None, "available": _STRIPE_AVAILABLE}
    prefix = STRIPE_API_KEY[:8]
    if prefix.startswith("sk_live"):
        mode = "live"
    elif prefix.startswith("sk_test"):
        mode = "test"
    elif prefix.startswith("rk_live"):
        mode = "live (restricted)"
    elif prefix.startswith("rk_test"):
        mode = "test (restricted)"
    else:
        mode = "unknown"
    return {
        "configured": True,
        "mode": mode,
        "available": _STRIPE_AVAILABLE,
        "key_prefix": prefix,
    }




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
    # Stripe rejects non-https webhook URLs in live mode. Behind Railway's
    # proxy, `request.base_url` sometimes reports `http://` even though the
    # external scheme is `https://`. We force https when the request came in
    # via an https-terminated edge (detected via the standard forwarded-proto
    # header set by Railway / Vercel).
    fwd_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if fwd_proto == "https" and host_url.startswith("http://"):
        host_url = "https://" + host_url[len("http://"):]
    # Operators can pin the webhook URL via `STRIPE_WEBHOOK_URL` env var if
    # the auto-detected one ever drifts (e.g. when fronted by Cloudflare with
    # a custom domain).
    import os as _os
    webhook_url = (_os.environ.get("STRIPE_WEBHOOK_URL") or "").strip() or f"{host_url}api/webhook/stripe"
    try:
        stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Stripe client init failed | webhook_url={webhook_url}")
        raise HTTPException(status_code=502, detail=f"Stripe init failed: {exc}") from exc

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
    try:
        session = await stripe.create_checkout_session(req)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Stripe create_checkout_session failed | "
            f"booking={booking['booking_id']} amount={booking['amount']} "
            f"currency={currency} webhook_url={webhook_url} "
            f"success_url={success_url} origin={payload.origin_url}"
        )
        # Surface a useful message to the buyer rather than a blank 500.
        raise HTTPException(
            status_code=502,
            detail=f"Payment provider rejected the request: {exc}",
        ) from exc

    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "booking_id": booking["booking_id"],
        "user_id": user["user_id"], "amount": booking["amount"], "currency": currency,
        "metadata": req.metadata, "payment_status": "pending", "status": "initiated",
        "created_at": utc_now().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


async def _finalize_paid_booking(booking_id: str, session_id: str | None = None) -> bool:
    """Mark a booking as paid, free seat holds, generate QR, email confirmation.
    Idempotent — safe to call multiple times. Returns True if this call
    actually flipped the booking from pending → paid (and therefore did the
    fulfilment work), False if it was already paid (and we skipped).
    """
    result = await db.bookings.update_one(
        {"booking_id": booking_id, "status": {"$ne": "paid"}},
        {"$set": {"status": "paid", "paid_at": utc_now().isoformat()}},
    )
    if result.modified_count == 0:
        return False
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
    if session_id:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete"}},
        )
    await _send_booking_confirmation_email(booking_id)
    logger.info(f"[booking_paid] {booking_id} — confirmation email queued")
    # Live broadcast — seats went from held → booked.
    booking_doc = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if booking_doc:
        seats = booking_doc.get("seats") or []
        if seats:
            await notify_seats(
                booking_doc["event_id"],
                [{"seat_id": s, "status": "booked"} for s in seats],
            )
        else:
            await notify_tier_refresh(booking_doc["event_id"])
    return True


@router.post("/admin/payments/reconcile")
async def admin_reconcile_payments(user: dict = Depends(get_current_user)):
    """Admin tool: queries Stripe for every still-pending checkout session and
    fulfils any that have actually been paid. Use this when the live webhook
    hasn't been configured yet OR when a webhook delivery has failed — Stripe
    is the source of truth, so we re-pull each session's status and fulfil
    locally if Stripe says it's paid.

    Returns a summary so the admin UI can show what was fixed.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not _STRIPE_AVAILABLE or not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # NOTE: We don't actually need a StripeCheckout instance — _raw_session_status
    # talks to the raw SDK. Initialised earlier as a defensive smoke-test.
    # Pull every transaction we still believe is pending OR initiated. We cap
    # at 200 so a runaway DB doesn't time out the request.
    pending = await db.payment_transactions.find(
        {"payment_status": {"$nin": ["paid", "expired", "failed", "refunded"]}},
        {"_id": 0, "session_id": 1, "booking_id": 1, "user_id": 1, "created_at": 1},
    ).sort("created_at", -1).limit(200).to_list(200)

    fulfilled: list[dict] = []
    still_pending: list[str] = []
    errors: list[dict] = []

    for tx in pending:
        sid = tx.get("session_id")
        bkg = tx.get("booking_id")
        if not sid:
            continue
        try:
            s = await _raw_session_status(sid)
            new_pay = s.get("payment_status") or "pending"
            await db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"status": s.get("status") or "open", "payment_status": new_pay, "updated_at": utc_now().isoformat()}},
            )
            if new_pay == "paid":
                did_fulfil = await _finalize_paid_booking(bkg, session_id=sid)
                fulfilled.append({"booking_id": bkg, "session_id": sid, "newly_fulfilled": did_fulfil})
            else:
                still_pending.append(sid)
        except Exception as exc:  # noqa: BLE001
            errors.append({"session_id": sid, "booking_id": bkg, "error": str(exc)[:200]})
            logger.warning(f"Reconcile: stripe lookup failed for {sid}: {exc}")

    return {
        "ok": True,
        "scanned": len(pending),
        "fulfilled_count": sum(1 for f in fulfilled if f["newly_fulfilled"]),
        "already_paid_count": sum(1 for f in fulfilled if not f["newly_fulfilled"]),
        "still_pending_count": len(still_pending),
        "errors": errors,
        "fulfilled": fulfilled,
    }


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
    try:
        s = await _raw_session_status(session_id)
        new_status = s.get("status") or "open"
        new_pay = s.get("payment_status") or "pending"
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
        await _finalize_paid_booking(tx["booking_id"], session_id=session_id)

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
            await _finalize_paid_booking(booking_id, session_id=evt.session_id)
    return {"ok": True}
