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


async def _resolve_recipients(db, event: dict, face_total: float) -> list[dict]:
    """Return the list of recipients to pay for an event.

    If `event.revenue_splits` is set (e.g. `[{user_id, percent, label}]`),
    we honor it — each entry receives `face_total * percent / 100` of the
    organizer-side share. Percents must sum to ~100; otherwise we fall back
    to a single 100%-organizer payout to be safe.

    Each returned dict carries `{user_id, name, label, amount, account_id}`.
    Recipients with no verified Connect account are dropped (logged); their
    share is forfeited to platform until the event is reconfigured.
    """
    splits = event.get("revenue_splits") or []
    if not splits:
        organizer_id = event.get("organizer_id")
        org = await db.users.find_one({"user_id": organizer_id}, {"_id": 0})
        if not org or not org.get("stripe_account_id") or not org.get("stripe_payouts_enabled"):
            return []
        return [{
            "user_id": organizer_id,
            "name": org.get("name") or "organizer",
            "label": "organizer",
            "amount": round(face_total, 2),
            "account_id": org["stripe_account_id"],
        }]
    total_pct = sum(float(s.get("percent") or 0) for s in splits)
    if abs(total_pct - 100.0) > 0.5:
        logger.warning("[connect-payout] event %s revenue_splits sum to %.2f%% (not 100) — falling back to organizer-only payout", event.get("event_id"), total_pct)
        # Fallback: pay organizer in full to avoid double-paying / underpaying
        return await _resolve_recipients(db, {"organizer_id": event.get("organizer_id"), "revenue_splits": []}, face_total)
    out: list[dict] = []
    for s in splits:
        uid = s.get("user_id")
        if not uid:
            continue
        u = await db.users.find_one({"user_id": uid}, {"_id": 0})
        if not u or not u.get("stripe_account_id") or not u.get("stripe_payouts_enabled"):
            logger.warning("[connect-payout] skipping split recipient %s — no verified Connect", uid)
            continue
        out.append({
            "user_id": uid,
            "name": u.get("name") or "recipient",
            "label": s.get("label") or "recipient",
            "amount": round(face_total * float(s.get("percent")) / 100.0, 2),
            "account_id": u["stripe_account_id"],
        })
    return out


async def _attempt_event_payout(db, event: dict, *, triggered_by: str = "scheduler") -> dict:
    """Create one or more Stripe Transfers for one event.

    Supports `event.revenue_splits` (multi-organizer revenue share). When set,
    each recipient gets a separate transfer keyed by
    `event-payout-{event_id}-{user_id}`, so adding a new split later doesn't
    re-pay the recipients who already got their share.

    Returns a summary dict including a per-recipient breakdown.
    """
    event_id = event["event_id"]
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return {"event_id": event_id, "status": "skipped", "reason": "no organizer"}

    # Skip events fully settled in a previous run. Per-recipient idempotency
    # already protects against double-pay, but checking up-front saves a
    # round-trip and keeps audit logs clean.
    if event.get("payout_status") == "paid" and not event.get("payout_recipients"):
        # Legacy single-organizer path — already done.
        return {"event_id": event_id, "status": "skipped", "reason": "already paid"}

    # Check Connect verification BEFORE booking aggregation so the scheduler
    # can retry once the organizer (or a split recipient) completes Stripe
    # onboarding. We pass `gross=0` here for the existence check; the real
    # share amounts are computed below.
    pre_recipients = await _resolve_recipients(db, event, 0.0)
    if not pre_recipients:
        return {"event_id": event_id, "status": "skipped", "reason": "connect not verified"}

    gross, platform_fee, tickets, booking_ids, currency = await _gross_for_event(db, event_id)
    if gross <= 0 or not booking_ids:
        await db.events.update_one(
            {"event_id": event_id},
            {"$set": {"payout_status": "no_revenue", "payout_processed_at": _utc_now().isoformat()}},
        )
        return {"event_id": event_id, "status": "skipped", "reason": "no paid bookings"}

    recipients = await _resolve_recipients(db, event, gross)
    if not recipients:
        return {"event_id": event_id, "status": "skipped", "reason": "connect not verified"}

    if not _STRIPE or not os.environ.get("STRIPE_API_KEY"):
        return {"event_id": event_id, "status": "skipped", "reason": "stripe not configured"}
    _stripe.api_key = os.environ["STRIPE_API_KEY"]

    cur = (currency or event.get("currency") or "nzd").lower()

    # Track which recipients we've already paid (in case of retries).
    prior = {r.get("user_id"): r for r in (event.get("payout_recipients") or []) if isinstance(r, dict)}

    results: list[dict] = []
    all_paid = True
    any_failed = False

    for rcpt in recipients:
        uid = rcpt["user_id"]
        if prior.get(uid, {}).get("status") == "paid":
            # Already transferred in a previous run — preserve audit row.
            results.append(prior[uid])
            continue

        amount_minor = int(round(float(rcpt["amount"]) * 100))
        if amount_minor <= 0:
            results.append({**rcpt, "status": "skipped", "reason": "zero share"})
            continue

        # Per-recipient idempotency so a partial failure can be retried
        # without double-paying anyone who already succeeded.
        idem_key = f"event-payout-{event_id}-{uid}"
        try:
            transfer = await asyncio.to_thread(
                _stripe.Transfer.create,
                amount=amount_minor,
                currency=cur,
                destination=rcpt["account_id"],
                description=f"Allsale Events payout — {event.get('title','event')[:60]} ({rcpt.get('label','organizer')})",
                metadata={
                    "event_id": event_id,
                    "organizer_id": organizer_id,
                    "recipient_user_id": uid,
                    "recipient_label": rcpt.get("label", "organizer"),
                    "gross": str(gross),
                    "share_amount": str(rcpt["amount"]),
                    "platform_fee": str(platform_fee),
                    "tickets": str(tickets),
                    "triggered_by": triggered_by,
                },
                idempotency_key=idem_key,
            )
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)[:300]
            logger.exception(f"[connect-payout] event={event_id} recipient={uid} failed: {reason}")
            results.append({
                **rcpt,
                "status": "failed",
                "error": reason,
                "attempted_at": _utc_now().isoformat(),
            })
            await db.connect_payouts.insert_one({
                "payout_id": "cpyt_" + uuid4().hex[:12],
                "event_id": event_id,
                "organizer_id": organizer_id,
                "recipient_user_id": uid,
                "recipient_label": rcpt.get("label"),
                "stripe_account_id": rcpt["account_id"],
                "status": "failed",
                "error": reason,
                "gross": gross,
                "platform_fee": platform_fee,
                "net_amount": rcpt["amount"],
                "currency": cur,
                "bookings_count": len(booking_ids),
                "tickets_count": tickets,
                "booking_ids": booking_ids,
                "triggered_by": triggered_by,
                "created_at": _utc_now().isoformat(),
            })
            all_paid = False
            any_failed = True
            continue

        now_iso = _utc_now().isoformat()
        transfer_id = transfer.get("id") if isinstance(transfer, dict) else getattr(transfer, "id", None)
        results.append({
            **rcpt,
            "status": "paid",
            "transfer_id": transfer_id,
            "paid_at": now_iso,
        })
        await db.connect_payouts.insert_one({
            "payout_id": "cpyt_" + uuid4().hex[:12],
            "event_id": event_id,
            "organizer_id": organizer_id,
            "recipient_user_id": uid,
            "recipient_label": rcpt.get("label"),
            "stripe_account_id": rcpt["account_id"],
            "stripe_transfer_id": transfer_id,
            "status": "paid",
            "gross": gross,
            "platform_fee": platform_fee,
            "net_amount": rcpt["amount"],
            "currency": cur,
            "bookings_count": len(booking_ids),
            "tickets_count": tickets,
            "booking_ids": booking_ids,
            "triggered_by": triggered_by,
            "created_at": now_iso,
            "paid_at": now_iso,
        })

        # Email each recipient individually so co-organizers know they got paid.
        try:
            user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0}) or {}
            target_email = user_doc.get("notification_email") or user_doc.get("email")
            if target_email:
                send_template_fireforget(
                    "organizer_payout_issued",
                    target_email,
                    {
                        "organizer_name": user_doc.get("name") or rcpt.get("name") or "organizer",
                        "payout_id": transfer_id or "—",
                        "amount": rcpt["amount"],
                        "bookings_count": len(booking_ids),
                        "period": _format_period(event.get("date"), now_iso),
                        "event_title": event.get("title", "your event"),
                        "currency": cur.upper(),
                    },
                    db,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[connect-payout] email failed for {uid}: {exc}")

    # Roll-up event state.
    paid_total = round(sum(float(r.get("amount", 0)) for r in results if r.get("status") == "paid"), 2)
    if not any(r.get("status") == "paid" for r in results) and any_failed:
        status_label = "failed"
    elif any_failed:
        status_label = "partial"
    else:
        status_label = "paid" if all_paid else "partial"

    # Backward-compat top-level fields (legacy single-organizer dashboards).
    legacy_recipient = next((r for r in results if r.get("status") == "paid"), results[0] if results else {})

    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {
            "payout_status": status_label,
            "payout_recipients": [
                {k: v for k, v in r.items() if k != "account_id" or True}  # keep account_id; audit
                for r in results
            ],
            "payout_transfer_id": legacy_recipient.get("transfer_id"),
            "payout_amount": paid_total,
            "payout_platform_fee": platform_fee,
            "payout_gross": gross,
            "payout_currency": cur,
            "payout_processed_at": _utc_now().isoformat(),
        }},
    )

    summary = {
        "event_id": event_id,
        "status": status_label,
        "recipients": results,
        "paid_total": paid_total,
        "platform_fee": platform_fee,
        "gross": gross,
    }
    if status_label == "paid":
        summary["transfer_id"] = legacy_recipient.get("transfer_id")
        summary["net"] = paid_total
    return summary


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
        st = res.get("status")
        if st == "paid":
            paid += 1
        elif st in ("failed", "partial"):
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
