"""Stripe checkout: create session, poll status, webhook."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

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
    rejects Stripe's `metadata` return type. We convert to a plain dict
    immediately to avoid every StripeObject quirk.
    """
    if not _RAW_STRIPE_AVAILABLE:
        raise RuntimeError("Raw stripe SDK not installed")
    _stripe_sdk.api_key = STRIPE_API_KEY
    import asyncio
    import json as _json
    sess = await asyncio.to_thread(_stripe_sdk.checkout.Session.retrieve, session_id)
    # `sess` is a StripeObject (dict subclass with magical accessors). To
    # avoid every access-time surprise (custom __getitem__, lazy expansion,
    # etc.), we round-trip through JSON to get a vanilla python dict.
    try:
        # Prefer the SDK's own dict converter when available — fastest path.
        sess_dict = sess.to_dict_recursive() if hasattr(sess, "to_dict_recursive") else _json.loads(str(sess))
    except Exception:  # noqa: BLE001
        # Last-ditch: serialise via stripe's __repr__ which is JSON-shaped.
        try:
            sess_dict = _json.loads(str(sess))
        except Exception:  # noqa: BLE001
            sess_dict = {}
    if not isinstance(sess_dict, dict):
        sess_dict = {}

    metadata_raw = sess_dict.get("metadata") or {}
    if not isinstance(metadata_raw, dict):
        metadata_raw = {}
    customer_details = sess_dict.get("customer_details") or {}
    if not isinstance(customer_details, dict):
        customer_details = {}
    cust_email = customer_details.get("email") or sess_dict.get("customer_email")
    return {
        "status": sess_dict.get("status"),
        "payment_status": sess_dict.get("payment_status"),
        "amount_total": sess_dict.get("amount_total"),
        "currency": sess_dict.get("currency"),
        "metadata": metadata_raw,
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
    """Fetch fresh booking + event and queue confirmation email (non-blocking).

    Attaches the printable ticket PDF (QR top-left + details) so the buyer
    can open their inbox at the door and just show the attachment — no need
    to log back into the site.
    """
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
    # Build a print-ready PDF and attach it. Best-effort — if PDF generation
    # fails we still send the email without the attachment (the buyer can
    # still download it from /profile).
    attachments = None
    try:
        from ticket_pdf import build_ticket_pdf  # local import to keep startup lean
        pdf_ctx = {
            **ctx,
            "event_venue": event.get("venue", ""),
            "event_city": event.get("city", ""),
            "qr_code": booking.get("qr_code"),
            "currency": booking.get("currency") or event.get("currency", "NZD"),
        }
        pdf_bytes, filename = build_ticket_pdf(pdf_ctx)
        attachments = [{"content": pdf_bytes, "filename": filename}]
    except Exception:  # noqa: BLE001
        logger.exception(f"[email] ticket PDF build failed for booking {booking_id}")
    send_template_fireforget(
        "booking_confirmation", booking["user_email"], ctx, db, attachments=attachments
    )


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

    # Gift card covered the entire buyer-total — no Stripe round-trip needed.
    # We finalize the booking directly (creates QR, sends email, frees holds).
    if float(booking.get("amount", 0)) <= 0:
        await _finalize_paid_booking(booking["booking_id"], session_id=None)
        return {"url": None, "session_id": None, "direct_paid": True}

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

    # Stripe Tax — when enabled, use the raw stripe SDK path so we can pass
    # automatic_tax. Otherwise stick with the emergent wrapper (which is
    # battle-tested for the legacy buyer-pays-fees flow).
    try:
        from routers.stripe_tax import stripe_tax_enabled, build_checkout_session_with_tax
        if stripe_tax_enabled():
            tax_sess = await build_checkout_session_with_tax(
                booking=booking, event=event,
                success_url=success_url, cancel_url=cancel_url,
            )
            await db.payment_transactions.insert_one({
                "session_id": tax_sess["session_id"],
                "booking_id": booking["booking_id"],
                "user_id": user["user_id"],
                "amount": booking["amount"],
                "currency": currency,
                "payment_status": "initiated",
                "tax_enabled": True,
                "created_at": utc_now().isoformat(),
            })
            return {"url": tax_sess["url"], "session_id": tax_sess["session_id"]}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — fall back to legacy path
        logger.warning(f"[stripe-tax] fallback to legacy checkout: {exc}")

    req = CheckoutSessionRequest(
        amount=float(booking["amount"]), currency=currency,
        success_url=success_url, cancel_url=cancel_url,
        metadata={
            "booking_id": booking["booking_id"], "event_id": booking["event_id"],
            "user_id": user["user_id"], "user_email": user.get("email", ""),
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

    # Welcome email #3 — fired ONCE on the organizer's first ever paid sale.
    # Guarded by `organizer.first_sale_email_sent_at` to be idempotent.
    try:
        booking_for_org = await db.bookings.find_one(
            {"booking_id": booking_id},
            {"_id": 0, "event_id": 1, "amount": 1, "currency": 1},
        )
        if booking_for_org:
            event_doc = await db.events.find_one(
                {"event_id": booking_for_org["event_id"]},
                {"_id": 0, "organizer_id": 1, "title": 1, "currency": 1},
            )
            if event_doc and event_doc.get("organizer_id"):
                organizer = await db.users.find_one(
                    {"user_id": event_doc["organizer_id"], "first_sale_email_sent_at": {"$exists": False}},
                    {"_id": 0, "email": 1, "notification_email": 1, "name": 1, "user_id": 1},
                )
                if organizer:
                    target = organizer.get("notification_email") or organizer.get("email")
                    if target:
                        from emails import send_template_fireforget as _ff
                        _ff(
                            "organizer_welcome_3_first_sale",
                            target,
                            {
                                "organizer_name": organizer.get("name") or "there",
                                "event_title": event_doc.get("title", "your event"),
                                "amount": float(booking_for_org.get("amount") or 0),
                                "currency": event_doc.get("currency") or booking_for_org.get("currency") or "NZD",
                            },
                            db,
                        )
                        await db.users.update_one(
                            {"user_id": organizer["user_id"]},
                            {"$set": {"first_sale_email_sent_at": utc_now().isoformat()}},
                        )
    except Exception:  # noqa: BLE001 — never block payment confirmation
        pass
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
            # Capture full type + message + traceback so we can diagnose what
            # the Stripe SDK is unhappy about. Most "weird" Stripe SDK errors
            # are just `KeyError` / `AttributeError` whose str() is uninformative.
            import traceback
            tb_last = traceback.format_exc().splitlines()[-1]
            err_msg = f"{type(exc).__name__}: {str(exc)[:120]} | {tb_last[:120]}"
            errors.append({"session_id": sid, "booking_id": bkg, "error": err_msg})
            logger.exception(f"Reconcile: stripe lookup failed for {sid}")

    return {
        "ok": True,
        "scanned": len(pending),
        "fulfilled_count": sum(1 for f in fulfilled if f["newly_fulfilled"]),
        "already_paid_count": sum(1 for f in fulfilled if not f["newly_fulfilled"]),
        "still_pending_count": len(still_pending),
        "errors": errors,
        "fulfilled": fulfilled,
    }


class _ForceFulfilIn(BaseModel):
    booking_id: str


@router.post("/admin/payments/force-fulfil")
async def admin_force_fulfil_booking(payload: _ForceFulfilIn, user: dict = Depends(get_current_user)):
    """Manually mark a booking as paid and trigger fulfilment (QR + email +
    seat lock + live tier refresh). Used by admin when Stripe shows the
    charge as Succeeded in the dashboard but the Stripe SDK can't be queried
    cleanly (rare — usually a Pydantic / version mismatch with the SDK).
    The admin MUST visually confirm the payment in the Stripe dashboard
    before calling this — there's no automated Stripe-side verification.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    booking = await db.bookings.find_one({"booking_id": payload.booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail=f"No booking with id {payload.booking_id}")
    did_fulfil = await _finalize_paid_booking(payload.booking_id, session_id=None)
    return {
        "ok": True,
        "booking_id": payload.booking_id,
        "newly_fulfilled": did_fulfil,
        "to": booking.get("user_email"),
        "message": (
            "Booking marked paid; confirmation email queued."
            if did_fulfil
            else "Booking was already paid — no fulfilment work done."
        ),
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
        meta = evt.metadata or {}
        kind = meta.get("kind")
        if kind == "gift_card":
            try:
                from routers.gift_cards import finalize_gift_card_purchase
                await finalize_gift_card_purchase(meta.get("card_id"))
            except Exception:  # noqa: BLE001
                logger.exception("Failed to finalize gift card from webhook")
        elif kind == "bundle":
            try:
                from routers.bundles import finalize_bundle_purchase
                await finalize_bundle_purchase(meta.get("purchase_id"))
            except Exception:  # noqa: BLE001
                logger.exception("Failed to finalize bundle from webhook")
        elif kind == "paid_boost":
            try:
                from routers.events import finalize_paid_boost
                await finalize_paid_boost(meta)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to finalize paid boost from webhook")
        else:
            booking_id = meta.get("booking_id")
            if booking_id:
                await _finalize_paid_booking(booking_id, session_id=evt.session_id)
    return {"ok": True}
