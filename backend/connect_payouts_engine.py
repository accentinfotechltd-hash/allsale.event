"""Stripe Connect — automated per-event payouts.

Runs on the scheduler. For each event whose start `date` is older than
`PAYOUT_HOLD_HOURS` (default **120h = 5 days**) AND whose organizer has a
verified Connect account (`stripe_payouts_enabled=true`), we:

1. Sum gross revenue from paid+non-refunded bookings on that event.
2. Subtract the platform fee (`PLATFORM_FEE_BPS`, default 500 = 5%).
3. Skip events that have already been transferred or whose net is ≤ 0.
4. Create a `stripe.Transfer` to the organizer's connected account
   (`source_transaction` omitted → uses platform balance, separate-charges
    model).
5. Stamp the event with `payout_status=paid|failed`, `payout_transfer_id`,
   `payout_amount`, `payout_processed_at`, and an entry in
   `connect_payouts` for audit.
6. Email the organizer using the existing `organizer_payout_issued` template.

We deliberately reuse `event_id` as the idempotency key so retries from the
scheduler (or a manual admin trigger) never produce duplicate transfers.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from emails import send_template_fireforget

logger = logging.getLogger("aura.connect_payouts")

# Defaults (can be overridden via env on Railway without code changes).
PAYOUT_HOLD_HOURS = int(os.environ.get("PAYOUT_HOLD_HOURS", "120"))  # 5 days
PLATFORM_FEE_BPS = int(os.environ.get("PLATFORM_FEE_BPS", "500"))   # 5%

try:
    import stripe as _stripe  # type: ignore
    _STRIPE = True
except Exception:  # pragma: no cover
    _stripe = None  # type: ignore
    _STRIPE = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_period(start_iso: str | None, end_iso: str | None) -> str:
    if not start_iso or not end_iso:
        return ""
    try:
        return f"{start_iso[:10]} → {end_iso[:10]}"
    except Exception:
        return ""


async def _gross_for_event(db, event_id: str) -> tuple[float, float, int, list[str], str | None]:
    """Return (face_value_sum, platform_fee_sum, tickets, booking_ids, currency).

    For new (post-fee-passthrough) bookings, `face_value` and `platform_fee`
    are stored explicitly. For legacy bookings missing those fields we fall
    back to `amount` as the face value and compute 5% on the fly so old
    events still pay out correctly during the migration window.
    """
    from fees import PLATFORM_FEE_BPS as _BPS  # local import to avoid cycle
    face_total = 0.0
    platform_total = 0.0
    tickets = 0
    booking_ids: list[str] = []
    currency = None
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid"}, {"_id": 0}
    ):
        # Skip if refunded after payment.
        if b.get("refunded_at") or b.get("status") == "refunded":
            continue
        face_val = b.get("face_value")
        if face_val is None:
            # Legacy booking — `amount` was the ticket face (no fees added).
            face_val = float(b.get("amount", 0) or 0)
        plat = b.get("platform_fee")
        if plat is None:
            plat = round(float(face_val) * (_BPS / 10000.0), 2)
        face_total += float(face_val)
        platform_total += float(plat)
        tickets += int(b.get("quantity", 0) or 0)
        booking_ids.append(b["booking_id"])
        if currency is None:
            currency = b.get("currency") or "nzd"
    return round(face_total, 2), round(platform_total, 2), tickets, booking_ids, currency


async def _attempt_event_payout(db, event: dict, *, triggered_by: str = "scheduler") -> dict:
    """Create a Stripe Transfer for one event. Returns a result dict."""
    event_id = event["event_id"]
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return {"event_id": event_id, "status": "skipped", "reason": "no organizer"}

    organizer = await db.users.find_one({"user_id": organizer_id}, {"_id": 0})
    if not organizer:
        return {"event_id": event_id, "status": "skipped", "reason": "organizer not found"}
    acct_id = organizer.get("stripe_account_id")
    if not acct_id or not organizer.get("stripe_payouts_enabled"):
        return {"event_id": event_id, "status": "skipped", "reason": "connect not verified"}

    if event.get("payout_status") == "paid":
        return {"event_id": event_id, "status": "skipped", "reason": "already paid"}

    gross, platform_fee, tickets, booking_ids, currency = await _gross_for_event(db, event_id)
    if gross <= 0 or not booking_ids:
        await db.events.update_one(
            {"event_id": event_id},
            {"$set": {"payout_status": "no_revenue", "payout_processed_at": _utc_now().isoformat()}},
        )
        return {"event_id": event_id, "status": "skipped", "reason": "no paid bookings"}

    # The organizer's transfer = face_value (their ticket revenue). The
    # platform fee was already collected from the buyer separately, so we
    # don't subtract it again — we just keep it in the platform's balance.
    net = round(gross, 2)
    if net <= 0:
        return {"event_id": event_id, "status": "skipped", "reason": "net <= 0"}

    if not _STRIPE or not os.environ.get("STRIPE_API_KEY"):
        return {"event_id": event_id, "status": "skipped", "reason": "stripe not configured"}
    _stripe.api_key = os.environ["STRIPE_API_KEY"]

    # Idempotency key: stable per-event so retries don't double-pay. If admin
    # ever needs to force a second payout, they can delete the event's
    # `payout_*` fields first.
    idem_key = f"event-payout-{event_id}"

    amount_minor = int(round(net * 100))  # cents
    cur = (currency or event.get("currency") or "nzd").lower()
    try:
        transfer = await asyncio.to_thread(
            _stripe.Transfer.create,
            amount=amount_minor,
            currency=cur,
            destination=acct_id,
            description=f"Allsale Events payout — {event.get('title','event')[:60]}",
            metadata={
                "event_id": event_id,
                "organizer_id": organizer_id,
                "gross": str(gross),
                "platform_fee": str(platform_fee),
                "tickets": str(tickets),
                "triggered_by": triggered_by,
            },
            idempotency_key=idem_key,
        )
    except Exception as exc:  # noqa: BLE001
        reason = str(exc)[:300]
        logger.exception(f"[connect-payout] event={event_id} failed: {reason}")
        await db.events.update_one(
            {"event_id": event_id},
            {"$set": {
                "payout_status": "failed",
                "payout_error": reason,
                "payout_processed_at": _utc_now().isoformat(),
            }},
        )
        await db.connect_payouts.insert_one({
            "payout_id": "cpyt_" + uuid4().hex[:12],
            "event_id": event_id,
            "organizer_id": organizer_id,
            "stripe_account_id": acct_id,
            "status": "failed",
            "error": reason,
            "gross": gross,
            "platform_fee": platform_fee,
            "net_amount": net,
            "currency": cur,
            "bookings_count": len(booking_ids),
            "tickets_count": tickets,
            "booking_ids": booking_ids,
            "triggered_by": triggered_by,
            "created_at": _utc_now().isoformat(),
        })
        return {"event_id": event_id, "status": "failed", "reason": reason}

    now_iso = _utc_now().isoformat()
    transfer_id = transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)

    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {
            "payout_status": "paid",
            "payout_transfer_id": transfer_id,
            "payout_amount": net,
            "payout_platform_fee": platform_fee,
            "payout_gross": gross,
            "payout_currency": cur,
            "payout_processed_at": now_iso,
        }},
    )
    payout_doc = {
        "payout_id": "cpyt_" + uuid4().hex[:12],
        "event_id": event_id,
        "organizer_id": organizer_id,
        "stripe_account_id": acct_id,
        "stripe_transfer_id": transfer_id,
        "status": "paid",
        "gross": gross,
        "platform_fee": platform_fee,
        "net_amount": net,
        "currency": cur,
        "bookings_count": len(booking_ids),
        "tickets_count": tickets,
        "booking_ids": booking_ids,
        "triggered_by": triggered_by,
        "created_at": now_iso,
        "paid_at": now_iso,
    }
    await db.connect_payouts.insert_one(payout_doc)

    # Notify organizer.
    try:
        target_email = (
            organizer.get("notification_email") or organizer.get("email")
        )
        if target_email:
            send_template_fireforget(
                "organizer_payout_issued",
                target_email,
                {
                    "organizer_name": organizer.get("name") or "organizer",
                    "payout_id": payout_doc["payout_id"],
                    "amount": net,
                    "bookings_count": len(booking_ids),
                    "period": _format_period(event.get("date"), now_iso),
                    "event_title": event.get("title", "your event"),
                    "currency": cur.upper(),
                },
                db,
            )
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[connect-payout] email failed: {exc}")

    return {"event_id": event_id, "status": "paid", "transfer_id": transfer_id, "net": net}


async def run_due_event_payouts(db) -> dict:
    """Find all events past their 5-day hold and try to pay them out."""
    cutoff = _utc_now() - timedelta(hours=PAYOUT_HOLD_HOURS)
    cutoff_iso = cutoff.isoformat()

    candidates: list[dict] = []
    async for e in db.events.find(
        {
            # Past their 5-day hold window
            "date": {"$lt": cutoff_iso},
            # Approved events only — drafts/pending shouldn't payout
            "status": {"$in": ["approved", "published"]},
            # Not already settled
            "$or": [
                {"payout_status": {"$exists": False}},
                {"payout_status": {"$nin": ["paid", "no_revenue"]}},
            ],
        },
        {"_id": 0},
    ):
        candidates.append(e)

    if not candidates:
        return {"checked": 0, "paid": 0, "skipped": 0, "failed": 0}

    paid = skipped = failed = 0
    for ev in candidates:
        res = await _attempt_event_payout(db, ev, triggered_by="scheduler")
        if res["status"] == "paid":
            paid += 1
        elif res["status"] == "failed":
            failed += 1
        else:
            skipped += 1
    return {"checked": len(candidates), "paid": paid, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Refund-aware reversal
# ---------------------------------------------------------------------------
async def reverse_transfer_for_refund(db, booking: dict, *, triggered_by: str = "refund") -> dict:
    """When a booking is refunded AFTER its event has already paid out, claw
    back the organizer's share proportionally via `stripe.Transfer.create_reversal`.

    Idempotent on `(booking_id)` — if we've already reversed for this
    booking, returns the cached reversal_id instead of double-reversing.

    Returns `{"status": "reversed"|"skipped"|"failed", ...}`.
    """
    event_id = booking.get("event_id")
    booking_id = booking.get("booking_id")
    if not (event_id and booking_id):
        return {"status": "skipped", "reason": "missing event/booking id"}

    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event or event.get("payout_status") != "paid":
        return {"status": "skipped", "reason": "event not paid out yet — no reversal needed"}

    transfer_id = event.get("payout_transfer_id")
    if not transfer_id:
        return {"status": "skipped", "reason": "event has no transfer to reverse"}

    # Check whether we already reversed this booking.
    existing = await db.connect_payouts.find_one(
        {"reversal_for_booking_id": booking_id}, {"_id": 0}
    )
    if existing:
        return {"status": "skipped", "reason": "already reversed", "reversal_id": existing.get("stripe_reversal_id")}

    # Compute the share to reverse: booking.face_value (the organizer net
    # of this single booking). Fallback to amount for legacy bookings.
    refundable = booking.get("face_value") or booking.get("amount") or 0
    refundable = float(refundable or 0)
    if refundable <= 0:
        return {"status": "skipped", "reason": "booking has no refundable face value"}

    if not _STRIPE or not os.environ.get("STRIPE_API_KEY"):
        return {"status": "skipped", "reason": "stripe not configured"}
    _stripe.api_key = os.environ["STRIPE_API_KEY"]

    amount_minor = int(round(refundable * 100))
    idem_key = f"refund-reversal-{booking_id}"
    try:
        reversal = await asyncio.to_thread(
            _stripe.Transfer.create_reversal,
            transfer_id,
            amount=amount_minor,
            description=f"Allsale refund reversal — booking {booking_id}",
            metadata={
                "booking_id": booking_id,
                "event_id": event_id,
                "triggered_by": triggered_by,
            },
            idempotency_key=idem_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[connect-payout] reversal failed for {booking_id}: {exc}")
        return {"status": "failed", "reason": str(exc)[:300]}

    reversal_id = reversal.get("id") if isinstance(reversal, dict) else getattr(reversal, "id", None)
    now_iso = _utc_now().isoformat()
    await db.connect_payouts.insert_one({
        "payout_id": "rev_" + uuid4().hex[:12],
        "event_id": event_id,
        "organizer_id": event.get("organizer_id"),
        "stripe_account_id": event.get("payout_transfer_id"),  # link
        "stripe_transfer_id": transfer_id,
        "stripe_reversal_id": reversal_id,
        "reversal_for_booking_id": booking_id,
        "status": "reversed",
        "net_amount": -refundable,
        "currency": (event.get("payout_currency") or "nzd"),
        "triggered_by": triggered_by,
        "created_at": now_iso,
    })
    await db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "transfer_reversal_id": reversal_id,
            "transfer_reversal_at": now_iso,
        }},
    )
    return {"status": "reversed", "reversal_id": reversal_id, "amount": refundable}
