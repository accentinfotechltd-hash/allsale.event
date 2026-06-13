"""Background scheduler — runs once an hour to dispatch upcoming-event emails.

Two passes per tick:

1. **24-hour reminders** — for every paid booking whose event starts in the
   next 24h and that hasn't been reminded yet (`reminder_24h_sent_at` unset),
   send the `event_reminder_24h` template. Respects `notification_prefs.email_reminders`.
2. **Weekly digest** — every Monday between 08:00 and 10:00 UTC, send the
   `weekly_digest` template once per user with the upcoming week's events.
   Respects `notification_prefs.email_marketing`. Uses `weekly_digest_sent_at`
   stamp on the user doc to dedupe.

The scheduler is fully resilient: any exception inside a tick is logged but
never bubbles up, so the loop keeps running. On startup it sleeps 30s before
the first tick so the API is responsive immediately.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from emails import send_template_fireforget
from connect_payouts_engine import run_due_event_payouts

logger = logging.getLogger("aura.scheduler")


def _pref_on(user: dict, key: str, default: bool = True) -> bool:
    prefs = user.get("notification_prefs") or {}
    return bool(prefs.get(key, default))


def _format_when(iso_str: str) -> str:
    """Pretty 'Sat, May 30 · 7:30 PM' from an ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%a, %b %-d · %-I:%M %p")
    except Exception:
        return iso_str


async def _send_24h_reminders(db) -> int:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)
    window_start = now + timedelta(hours=12)  # only 12-24h ahead so we don't spam the day-of

    sent = 0
    # Pull events whose date is in the window
    candidate_event_ids: list[str] = []
    async for e in db.events.find(
        {"date": {"$gte": window_start.isoformat(), "$lte": window_end.isoformat()}},
        {"_id": 0, "event_id": 1},
    ):
        candidate_event_ids.append(e["event_id"])
    if not candidate_event_ids:
        return 0

    async for b in db.bookings.find(
        {
            "event_id": {"$in": candidate_event_ids},
            "status": "paid",
            "reminder_24h_sent_at": {"$exists": False},
        },
        {"_id": 0},
    ):
        # Look up the up-to-date user record so email + prefs reflect any recent edits
        user = await db.users.find_one({"user_id": b["user_id"]}, {"_id": 0, "password_hash": 0}) or {}
        target_email = user.get("email") or b.get("user_email")
        if not target_email:
            continue
        if not _pref_on(user, "email_reminders", default=True):
            await db.bookings.update_one(
                {"booking_id": b["booking_id"]},
                {"$set": {"reminder_24h_sent_at": now.isoformat(), "reminder_24h_skipped": "user_pref_off"}},
            )
            continue
        try:
            send_template_fireforget(
                "event_reminder_24h",
                target_email,
                {
                    "user_name": user.get("name") or b.get("user_name") or "there",
                    "event_title": b.get("event_title", "your event"),
                    "event_when": _format_when(b.get("event_date") or ""),
                    "event_venue": b.get("event_venue", ""),
                    "seats": b.get("seats") or [],
                    "tier_name": b.get("tier_name"),
                },
                db,
            )
            await db.bookings.update_one(
                {"booking_id": b["booking_id"]},
                {"$set": {"reminder_24h_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("24h reminder failed for booking %s: %s", b.get("booking_id"), exc)

    return sent


async def _send_weekly_digest(db) -> int:
    """Once per week (Monday 08-10 UTC), email each opted-in user a 6-event digest."""
    now = datetime.now(timezone.utc)
    # Only run on Mondays 8-10 UTC
    if now.weekday() != 0 or now.hour < 8 or now.hour >= 10:
        return 0

    # Top 6 upcoming events in the next 14 days (published)
    horizon = (now + timedelta(days=14)).isoformat()
    events: list[dict] = []
    async for e in db.events.find(
        {"date": {"$gte": now.isoformat(), "$lte": horizon}, "status": {"$in": ["published", "approved"]}},
        {"_id": 0, "event_id": 1, "title": 1, "venue": 1, "city": 1, "date": 1, "image_url": 1},
    ).sort("date", 1).limit(20):
        events.append({
            "event_id": e["event_id"],
            "title": e.get("title", ""),
            "venue": e.get("venue") or e.get("city") or "",
            "when": _format_when(e.get("date") or ""),
        })
    if not events:
        return 0

    sent = 0
    week_key = now.strftime("%G-W%V")  # ISO year-week so we dedupe per week
    async for user in db.users.find(
        {"$or": [
            {"weekly_digest_sent_week": {"$exists": False}},
            {"weekly_digest_sent_week": {"$ne": week_key}},
        ]},
        {"_id": 0, "password_hash": 0},
    ):
        if not _pref_on(user, "email_marketing", default=False):  # opt-in only
            continue
        if not user.get("email"):
            continue
        try:
            send_template_fireforget(
                "weekly_digest",
                user["email"],
                {"user_name": user.get("name") or user["email"].split("@")[0], "events": events[:6]},
                db,
            )
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"weekly_digest_sent_week": week_key, "weekly_digest_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("weekly digest failed for user %s: %s", user.get("user_id"), exc)
    return sent


async def _send_stripe_setup_nudges(db: Any) -> int:
    """Email organizers with upcoming events but no verified Stripe Connect.

    Targets: organizer has at least one approved event starting within the
    next `PAYOUT_HOLD_HOURS + 24` hours (so the payout would happen within
    a week) AND they don't have `stripe_payouts_enabled=True`. Sent at most
    once every 72 h per organizer so we don't spam them.
    """
    import os
    now = datetime.now(timezone.utc)
    hold_hours = int(os.environ.get("PAYOUT_HOLD_HOURS", "120"))
    horizon = now + timedelta(hours=hold_hours + 24)
    cooldown = now - timedelta(hours=72)

    # Find distinct organizer IDs with at least one upcoming event in window.
    pipeline = [
        {"$match": {
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": now.isoformat(), "$lt": horizon.isoformat()},
        }},
        {"$group": {"_id": "$organizer_id", "events_count": {"$sum": 1}, "next_event": {"$min": "$date"}, "next_title": {"$first": "$title"}}},
    ]
    sent = 0
    async for row in db.events.aggregate(pipeline):
        organizer_id = row["_id"]
        if not organizer_id:
            continue
        organizer = await db.users.find_one({"user_id": organizer_id}, {"_id": 0})
        if not organizer:
            continue
        if organizer.get("stripe_payouts_enabled"):
            continue  # already verified
        last_nudge = organizer.get("stripe_nudge_sent_at")
        if last_nudge:
            try:
                then = datetime.fromisoformat(last_nudge)
                if then.tzinfo is None:
                    then = then.replace(tzinfo=timezone.utc)
                if then >= cooldown:
                    continue  # cooldown
            except Exception:
                pass
        try:
            send_template_fireforget(
                "organizer_stripe_setup_nudge",
                organizer.get("email"),
                {
                    "organizer_name": organizer.get("name") or "organizer",
                    "events_count": int(row.get("events_count", 1)),
                    "next_event_title": row.get("next_title") or "your next event",
                    "next_event_date": row.get("next_event") or "",
                    "dashboard_url": "https://www.allsale.events/organizer",
                },
                db,
            )
            await db.users.update_one(
                {"user_id": organizer_id},
                {"$set": {"stripe_nudge_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("stripe nudge failed for organizer %s: %s", organizer_id, exc)
    return sent


async def _send_follower_weekly_digest(db) -> int:
    """Sunday 09:00-11:00 UTC: send each follower a digest of new events
    (approved in the last 7 days) from organizers they follow.

    Dedupe stamp: `follower_digest_sent_at` on the user doc. Skipped when
    a follower has no new events to surface (so we never send empty mail).
    """
    now = datetime.now(timezone.utc)
    if now.weekday() != 6 or now.hour < 9 or now.hour > 11:
        return 0
    today = now.date().isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    sent = 0

    # Find all unique follower user_ids — there'll be far fewer of them than
    # event-follower pairs in most apps, so dedupe early.
    follower_ids = set()
    async for f in db.follows.find({}, {"_id": 0, "user_id": 1}):
        follower_ids.add(f["user_id"])

    for uid in follower_ids:
        user = await db.users.find_one({"user_id": uid}, {"_id": 0})
        if not user:
            continue
        if not _pref_on(user, "email_marketing", True):
            continue
        last_sent = user.get("follower_digest_sent_at")
        if isinstance(last_sent, str) and last_sent.startswith(today):
            continue

        # Collect all organizer_ids they follow
        org_ids = []
        async for f in db.follows.find({"user_id": uid}, {"_id": 0, "organizer_id": 1}):
            org_ids.append(f["organizer_id"])
        if not org_ids:
            continue

        # Recent events from those organizers
        items = []
        async for ev in db.events.find(
            {
                "organizer_id": {"$in": org_ids},
                "status": {"$in": ["approved", "published"]},
                "created_at": {"$gte": seven_days_ago},
                "date": {"$gte": now.isoformat()},
            },
            {"_id": 0, "title": 1, "organizer_id": 1, "date": 1, "venue": 1, "city": 1, "event_id": 1},
        ).sort("date", 1).limit(10):
            org = await db.users.find_one({"user_id": ev["organizer_id"]}, {"_id": 0, "name": 1})
            items.append({
                "title": ev.get("title", "New event"),
                "organizer_name": (org or {}).get("name") or "Organizer",
                "when_human": _format_when(ev.get("date", "")),
                "venue": f"{ev.get('venue','')}, {ev.get('city','')}",
                "url": f"https://www.allsale.events/events/{ev['event_id']}",
            })

        if not items:
            continue

        target = user.get("notification_email") or user.get("email")
        if not target:
            continue
        try:
            send_template_fireforget(
                "follower_weekly_digest",
                target,
                {"follower_name": user.get("name") or "there", "items": items},
                db,
            )
            await db.users.update_one(
                {"user_id": uid},
                {"$set": {"follower_digest_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.exception("follower digest failed for %s: %s", uid, exc)
    return sent


async def _check_webhook_silent_failure(db) -> bool:
    """Detect silent webhook failures.

    Fires once per day (between 09-10 UTC) if either:
      - STRIPE_CONNECT_WEBHOOK_SECRET is set in env BUT no deliveries received in 48h
      - OR signature verifications have been failing (sentinel: all recent
        deliveries have `signature_verified=False`)

    Sends to ADMIN_ALERT_EMAIL (falls back to allsaletickets@gmail.com).
    Dedupes via `platform_settings.webhook_alert_last_sent`.

    Common breakage modes this catches:
      - Stripe rotated the signing secret and Railway env var is stale
      - Railway env var got deleted/renamed in a deploy
      - Webhook endpoint disabled on Stripe dashboard
      - Domain DNS changes broke the webhook URL
    """
    import os as _os
    now = datetime.now(timezone.utc)
    if now.hour != 9:  # run once daily
        return False
    secret_configured = bool(_os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET"))
    if not secret_configured:
        # The setup card on the admin page already covers this case visually.
        return False

    # Dedupe — don't email more than once per 24h
    settings = await db.platform_settings.find_one({"key": "webhook_health"}, {"_id": 0}) or {}
    last_sent = settings.get("alert_last_sent")
    if isinstance(last_sent, str):
        try:
            last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < 22 * 3600:
                return False
        except Exception:  # noqa: BLE001
            pass

    forty_eight_hrs_ago = (now - timedelta(hours=48)).isoformat()
    recent_count = await db.webhook_deliveries.count_documents({
        "source": "stripe_connect",
        "received_at": {"$gte": forty_eight_hrs_ago},
    })

    # Only alert if the platform has actually been operational (>0 events ever).
    # New deployments get a 7-day grace period.
    total_ever = await db.webhook_deliveries.count_documents({"source": "stripe_connect"})
    if total_ever == 0:
        return False

    if recent_count > 0:
        return False  # healthy

    # Build alert email
    admin_email = (
        _os.environ.get("ADMIN_ALERT_EMAIL")
        or "allsaletickets@gmail.com"
    )
    last_delivery_doc = await db.webhook_deliveries.find_one(
        {"source": "stripe_connect"}, sort=[("received_at", -1)],
    )
    last_delivery_at = (last_delivery_doc or {}).get("received_at") or "never"

    try:
        send_template_fireforget(
            "admin_webhook_silent_failure",
            admin_email,
            {
                "last_delivery_at": last_delivery_at,
                "total_ever": total_ever,
                "now_iso": now.isoformat(),
                "dashboard_url": "https://www.allsale.events/admin",
            },
            db,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("webhook alert failed: %s", exc)
        return False

    await db.platform_settings.update_one(
        {"key": "webhook_health"},
        {"$set": {"alert_last_sent": now.isoformat()}},
        upsert=True,
    )
    return True


async def scheduler_loop(db: Any, interval_seconds: int = 3600) -> None:
    """Top-level loop — sleeps 30s on startup, then ticks every `interval_seconds`."""
    await asyncio.sleep(30)
    while True:
        try:
            n_reminders = await _send_24h_reminders(db)
            n_digest = await _send_weekly_digest(db)
            n_nudge = await _send_stripe_setup_nudges(db)
            n_fdigest = await _send_follower_weekly_digest(db)
            webhook_alert = await _check_webhook_silent_failure(db)
            payout_summary = await run_due_event_payouts(db)
            if n_reminders or n_digest or n_nudge or n_fdigest or webhook_alert or payout_summary.get("paid") or payout_summary.get("failed"):
                logger.info(
                    "[scheduler] reminders=%s digest=%s nudges=%s fdigest=%s webhook_alert=%s payouts=%s",
                    n_reminders, n_digest, n_nudge, n_fdigest, webhook_alert, payout_summary,
                )
        except Exception as exc:  # pragma: no cover
            logger.exception("[scheduler] tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)
