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


async def _gross_for_event(db, event_id: str) -> tuple[float, int, list[str], str | None]:
    """Total paid gross, ticket count, booking IDs, dominant currency for an event."""
    gross = 0.0
    tickets = 0
    booking_ids: list[str] = []
    currency = None
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid"}, {"_id": 0}
    ):
        # Skip if refunded after payment.
        if b.get("refunded_at") or b.get("status") == "refunded":
            continue
        gross += float(b.get("amount", 0) or 0)
        tickets += int(b.get("quantity", 0) or 0)
        booking_ids.append(b["booking_id"])
        if currency is None:
            currency = b.get("currency") or "nzd"
    return round(gross, 2), tickets, booking_ids, currency


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

    gross, tickets, booking_ids, currency = await _gross_for_event(db, event_id)
    if gross <= 0 or not booking_ids:
        await db.events.update_one(
            {"event_id": event_id},
            {"$set": {"payout_status": "no_revenue", "payout_processed_at": _utc_now().isoformat()}},
        )
        return {"event_id": event_id, "status": "skipped", "reason": "no paid bookings"}

    platform_fee = round(gross * (PLATFORM_FEE_BPS / 10000.0), 2)
    net = round(max(0.0, gross - platform_fee), 2)
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
