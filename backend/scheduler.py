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


async def _send_post_event_nps(db) -> int:
    """Email each paid attendee an NPS prompt 24 hours after their event ends.

    The email includes a tracked link to `/feedback/:booking_id` where the
    visitor leaves a 1-5 rating + optional comment. Stored on `event_feedback`
    so organizers can display ratings as social proof on their event pages.
    """
    now = datetime.now(timezone.utc)
    window_end = now - timedelta(hours=24)
    window_start = now - timedelta(hours=72)  # 1-3 days after event end

    candidate_event_ids: list[str] = []
    async for e in db.events.find(
        {"date": {"$gte": window_start.isoformat(), "$lte": window_end.isoformat()}},
        {"_id": 0, "event_id": 1, "title": 1, "image_url": 1},
    ):
        candidate_event_ids.append(e["event_id"])
    if not candidate_event_ids:
        return 0

    sent = 0
    async for b in db.bookings.find(
        {
            "event_id": {"$in": candidate_event_ids},
            "status": "paid",
            "nps_email_sent_at": {"$exists": False},
        },
        {"_id": 0},
    ):
        user = await db.users.find_one({"user_id": b["user_id"]}, {"_id": 0, "password_hash": 0}) or {}
        target_email = user.get("email") or b.get("user_email")
        if not target_email:
            continue
        if not _pref_on(user, "email_reminders", default=True):
            await db.bookings.update_one(
                {"booking_id": b["booking_id"]},
                {"$set": {"nps_email_sent_at": now.isoformat(), "nps_skipped": "user_pref_off"}},
            )
            continue
        # Hydrate event details for the email body
        ev = next((e for e in []), None)
        ev = await db.events.find_one({"event_id": b["event_id"]}, {"_id": 0, "title": 1, "image_url": 1})
        cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
        origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
        feedback_url = f"{origin}/feedback/{b['booking_id']}"
        try:
            send_template_fireforget(
                to=target_email,
                subject=f"How was {ev.get('title', 'your event')}? 🎤",
                template="generic",
                params={
                    "title": "How was your night?",
                    "preheader": "Quick 30-second feedback — it makes a real difference for the organizer.",
                    "body_html": (
                        f"<p>Hi! Thanks for coming to <strong>{ev.get('title', 'the event')}</strong>.</p>"
                        f"<p>If you have 30 seconds, the organizer would love to hear how it went:</p>"
                        f"<p><a href=\"{feedback_url}\" style=\"display:inline-block;padding:12px 24px;background:#F08A2A;color:#0F2A3A;text-decoration:none;border-radius:8px;font-weight:600;\">Leave a quick rating ⭐</a></p>"
                        f"<p style=\"color:#888;font-size:12px;\">Your feedback is shown anonymously on the event page to help future fans decide.</p>"
                    ),
                },
            )
            await db.bookings.update_one(
                {"booking_id": b["booking_id"]},
                {"$set": {"nps_email_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("[scheduler] NPS email failed for %s: %s", target_email, exc)
    return sent


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


async def _send_organizer_welcome_followups(db) -> int:
    """Welcome email sequence:
      #2 fires 48h after signup if the organizer hasn't published any event.
      #4 fires 14d after their most-recent event ended if no new event scheduled.

    Both are deduped via per-user stamps (`welcome_2_sent_at`, `welcome_4_sent_at`).
    """
    now = datetime.now(timezone.utc)
    sent = 0
    forty_eight_ago = (now - timedelta(hours=48)).isoformat()
    fourteen_days_ago = (now - timedelta(days=14)).isoformat()
    seventy_two_ago = (now - timedelta(hours=72)).isoformat()

    # --- Email #2: signed up 48-72h ago, no event published ---
    async for u in db.users.find(
        {
            "role": "organizer",
            "created_at": {"$gte": seventy_two_ago, "$lte": forty_eight_ago},
            "welcome_2_sent_at": {"$exists": False},
        },
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "notification_email": 1},
    ):
        has_event = await db.events.find_one({"organizer_id": u["user_id"]}, {"_id": 1})
        if has_event:
            continue
        target = u.get("notification_email") or u.get("email")
        if not target:
            continue
        try:
            send_template_fireforget(
                "organizer_welcome_2_publish",
                target,
                {"organizer_name": u.get("name") or "there"},
                db,
            )
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"welcome_2_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("welcome_2 failed for %s: %s", u["user_id"], exc)

    # --- Email #4: last event ended 14d ago, no future event ---
    async for u in db.users.find(
        {"role": "organizer", "welcome_4_sent_at": {"$exists": False}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "notification_email": 1},
    ):
        # Most-recent past event for this organizer
        last = await db.events.find_one(
            {
                "organizer_id": u["user_id"],
                "status": {"$in": ["approved", "published", "archived"]},
                "date": {"$lt": fourteen_days_ago},
            },
            {"_id": 0, "event_id": 1, "title": 1, "date": 1},
            sort=[("date", -1)],
        )
        if not last:
            continue
        # Skip if they already have a future event scheduled.
        future = await db.events.find_one(
            {"organizer_id": u["user_id"], "date": {"$gte": now.isoformat()}},
            {"_id": 1},
        )
        if future:
            continue
        target = u.get("notification_email") or u.get("email")
        if not target:
            continue
        try:
            send_template_fireforget(
                "organizer_welcome_4_reactivate",
                target,
                {"organizer_name": u.get("name") or "there",
                 "last_event_title": last.get("title", "your last event")},
                db,
            )
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"welcome_4_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("welcome_4 failed for %s: %s", u["user_id"], exc)
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


async def _send_boost_recaps(db: Any) -> int:
    """Send a one-shot "Your Boost just ended — here's how it performed"
    recap email to organizers once their boost window expires.

    Idempotent: stamps `boost_recap_sent_at` on the event so re-running the
    scheduler tick doesn't double-send.
    """
    sent = 0
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=14)).isoformat()  # don't recap ancient boosts
    cur = db.events.find(
        {
            "boosted_until": {"$lt": now.isoformat(), "$gte": cutoff},
            "boost_recap_sent_at": {"$exists": False},
        },
        {"_id": 0},
    )
    async for event in cur:
        try:
            organizer = await db.users.find_one(
                {"user_id": event.get("organizer_id")},
                {"_id": 0, "email": 1, "name": 1},
            )
            if not organizer or not organizer.get("email"):
                # Still stamp so we don't keep scanning this event every tick.
                await db.events.update_one(
                    {"event_id": event["event_id"]},
                    {"$set": {"boost_recap_sent_at": now.isoformat(), "boost_recap_skipped": "no_email"}},
                )
                continue
            # Pull the lift stats by reusing the analytics function — keeps a
            # single source of truth for the math vs. duplicating it here.
            try:
                from routers.analytics import boost_lift  # type: ignore
                # Minimal user shim for the dep — the function checks organizer/admin.
                stats = await boost_lift.__wrapped__(  # type: ignore[attr-defined]
                    event["event_id"], {"user_id": event.get("organizer_id"), "role": "organizer"}
                )
            except Exception:  # noqa: BLE001
                # Fallback: just send the recap without lift numbers
                stats = {"during_views": None, "during_bookings": None, "view_lift_pct": None, "booking_lift_pct": None}

            from emails import send_template_fireforget
            send_template_fireforget(
                "boost_recap",
                organizer["email"],
                {
                    "organizer_name": organizer.get("name", "there"),
                    "event_title": event.get("title", "your event"),
                    "event_id": event["event_id"],
                    "boost_tier": event.get("last_boost_tier") or ("paid" if event.get("last_boost_kind") == "paid" else "free"),
                    "boost_kind": event.get("last_boost_kind", "free"),
                    "during_views": stats.get("during_views"),
                    "during_bookings": stats.get("during_bookings"),
                    "view_lift_pct": stats.get("view_lift_pct"),
                    "booking_lift_pct": stats.get("booking_lift_pct"),
                },
                db,
            )
            await db.events.update_one(
                {"event_id": event["event_id"]},
                {"$set": {"boost_recap_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception(f"[scheduler] boost recap failed for event={event.get('event_id')}")
    return sent



async def _send_event_recaps(db: Any) -> int:
    """Post-event recap. Sends ~1 hour after an event's start_date passes.

    Includes: tickets sold, gross revenue, check-in rate, top promo code (if any),
    and repeat-customer count (users who'd bought tickets to a prior event from
    the same organizer). Idempotent via `events.event_recap_sent_at` stamp.
    """
    sent = 0
    now = datetime.now(timezone.utc)
    floor = (now - timedelta(days=30)).isoformat()
    cur = db.events.find(
        {
            "date": {"$lt": now.isoformat(), "$gte": floor},
            "event_recap_sent_at": {"$exists": False},
            "status": {"$ne": "draft"},
        },
        {"_id": 0},
    )
    async for event in cur:
        try:
            organizer = await db.users.find_one(
                {"user_id": event.get("organizer_id")},
                {"_id": 0, "email": 1, "name": 1},
            )
            if not organizer or not organizer.get("email"):
                await db.events.update_one(
                    {"event_id": event["event_id"]},
                    {"$set": {"event_recap_sent_at": now.isoformat(), "event_recap_skipped": "no_email"}},
                )
                continue
            event_id = event["event_id"]
            # Tickets sold + gross
            agg = await db.bookings.aggregate([
                {"$match": {"event_id": event_id, "status": {"$in": ["paid", "confirmed"]}}},
                {"$group": {
                    "_id": None,
                    "tickets": {"$sum": {"$ifNull": ["$quantity", 1]}},
                    "gross": {"$sum": {"$ifNull": ["$face_value", "$amount"]}},
                }},
            ]).to_list(1)
            tickets = int((agg[0] if agg else {}).get("tickets") or 0)
            gross = float((agg[0] if agg else {}).get("gross") or 0)
            # Scan rate
            scanned = await db.bookings.count_documents({
                "event_id": event_id,
                "status": {"$in": ["paid", "confirmed"]},
                "checked_in_at": {"$exists": True, "$ne": None},
            })
            scan_rate = round((scanned / tickets) * 100, 1) if tickets else None
            # Top promo code
            top_promo_agg = await db.bookings.aggregate([
                {"$match": {
                    "event_id": event_id, "status": {"$in": ["paid", "confirmed"]},
                    "code": {"$exists": True, "$ne": None, "$ne": ""},
                }},
                {"$group": {"_id": "$code", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
                {"$limit": 1},
            ]).to_list(1)
            top_promo = (top_promo_agg[0]["_id"] if top_promo_agg else None)
            top_promo_count = (top_promo_agg[0]["n"] if top_promo_agg else 0)
            # Repeat customers — anyone who bought a prior ticket from this organizer too.
            buyer_ids = await db.bookings.distinct(
                "user_id",
                {"event_id": event_id, "status": {"$in": ["paid", "confirmed"]}},
            )
            repeat_count = 0
            if buyer_ids:
                repeat_count = await db.bookings.count_documents({
                    "user_id": {"$in": buyer_ids},
                    "event_id": {"$ne": event_id},
                    "status": {"$in": ["paid", "confirmed"]},
                })

            from emails import send_template_fireforget
            send_template_fireforget(
                "event_recap",
                organizer["email"],
                {
                    "organizer_name": organizer.get("name", "there"),
                    "event_title": event.get("title", "your event"),
                    "event_id": event_id,
                    "tickets": tickets,
                    "gross": round(gross, 2),
                    "currency": event.get("currency", "NZD"),
                    "scan_rate": scan_rate,
                    "top_promo": top_promo,
                    "top_promo_count": top_promo_count,
                    "repeat_customers": repeat_count,
                },
                db,
            )
            await db.events.update_one(
                {"event_id": event_id},
                {"$set": {"event_recap_sent_at": now.isoformat()}},
            )
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception(f"[scheduler] event recap failed for event={event.get('event_id')}")
    return sent


async def _send_monthly_partner_statements(db: Any) -> int:
    """On the 1st of every month, email each active partner their P&L statement.

    Idempotent via the `cron_runs` collection — we stamp a row keyed by
    `(job=marketing_partner_statements, period=YYYY-MM)` once the run
    completes, so a server restart on day 1 doesn't trigger a second blast.

    Only runs between 03:00 and 09:00 UTC on the 1st so partners get the
    statement during their morning, not at midnight UTC = afternoon NZ.
    """
    now = datetime.now(timezone.utc)
    if now.day != 1:
        return 0
    if not (3 <= now.hour < 9):
        return 0

    period_key = now.strftime("%Y-%m")
    job_key = {"job": "marketing_partner_statements", "period": period_key}
    existing = await db.cron_runs.find_one(job_key)
    if existing:
        return 0

    # Reserve the slot first — prevents two workers from both running it.
    try:
        await db.cron_runs.insert_one(
            {**job_key, "started_at": now.isoformat(), "status": "running"}
        )
    except Exception:
        # Race lost to another worker; bail.
        return 0

    # Build the per-partner ctx and send. Mirrors the admin endpoint logic
    # in `routers/marketing_partners.py::send_statements` so the email looks
    # identical whether it's auto-sent or admin-triggered.
    from routers.marketing_partners import _aggregate  # safe — no FastAPI deps

    period_label = now.strftime("%B %Y")
    period_start = now - timedelta(days=30)

    sent = 0
    cur = db.marketing_partners.find({"status": "active"}, {"_id": 0})
    async for p in cur:
        email = (p.get("email") or "").strip()
        if not email:
            continue
        agg = await _aggregate(p["partner_id"])
        period_pipeline = [
            {"$match": {"partner_id": p["partner_id"], "created_at": {"$gte": period_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$earning_amount"}}},
        ]
        period_doc = await db.marketing_partner_earnings.aggregate(period_pipeline).to_list(1)
        period_earnings = round(period_doc[0]["total"], 2) if period_doc else 0.0

        ledger_cur = (
            db.marketing_partner_earnings.find(
                {"partner_id": p["partner_id"]},
                {"_id": 0, "created_at": 1, "event_title": 1, "earning_amount": 1, "status": 1, "currency": 1},
            )
            .sort("created_at", -1)
            .limit(20)
        )
        earnings = []
        currency = "NZD"
        async for row in ledger_cur:
            ca = row.get("created_at")
            date_str = ca.strftime("%b %d") if isinstance(ca, datetime) else str(ca)[:10]
            earnings.append({
                "date": date_str,
                "event_title": row.get("event_title") or "",
                "earning_amount": row.get("earning_amount") or 0,
                "status": row.get("status") or "",
            })
            currency = row.get("currency") or currency

        ctx = {
            "partner_name": p.get("name") or "",
            "period_label": period_label,
            "currency": currency,
            "lifetime_earnings": agg["lifetime_earnings"],
            "period_earnings": period_earnings,
            "unpaid_balance": agg["unpaid_balance"],
            "organizer_count": agg["organizer_count"],
            "earnings": earnings,
        }
        try:
            # fire-and-forget so a single slow Resend call can't stall the tick.
            await send_template_fireforget("marketing_partner_statement", email, ctx, db=db)
            sent += 1
            await db.marketing_partners.update_one(
                {"partner_id": p["partner_id"]},
                {"$set": {"last_statement_sent_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[cron-monthly-statements] failed for {p['partner_id']}: {exc}")

    await db.cron_runs.update_one(
        job_key,
        {"$set": {"finished_at": datetime.now(timezone.utc).isoformat(), "status": "done", "sent_count": sent}},
    )
    logger.info(f"[cron-monthly-statements] sent {sent} statement emails for {period_key}")
    return sent


async def _run_monthly_partner_payouts(db: Any) -> dict:
    """On the 5th of every month, auto-batch all unpaid partner earnings into
    a payout batch (records them as `status=paid` with `payout_reference=
    "auto-batch YYYY-MM"`).

    Why the 5th, not the 1st? Statements go out on the 1st. Partners need a
    few days to query anything that looks off BEFORE the ledger gets sealed.
    Day 5 gives a 4-day reconciliation window.

    Why not the 1st: payment is actual money movement; admin still needs to
    actually transfer funds. This cron only updates the ledger to "paid" so
    the admin's "Mark all paid" routine doesn't have to be clicked every
    month. The admin opts in via `platform_settings.marketing_partners_auto_payout`.
    """
    settings = await db.platform_settings.find_one({}, {"_id": 0}) or {}
    if not settings.get("marketing_partners_auto_payout"):
        return {"skipped": "auto-payout disabled in platform_settings"}

    now = datetime.now(timezone.utc)
    if now.day != 5:
        return {}
    if not (3 <= now.hour < 9):
        return {}

    period_key = now.strftime("%Y-%m")
    job_key = {"job": "marketing_partner_auto_payout", "period": period_key}
    if await db.cron_runs.find_one(job_key):
        return {}
    try:
        await db.cron_runs.insert_one({**job_key, "started_at": now.isoformat(), "status": "running"})
    except Exception:
        return {}

    total_marked = 0
    partner_count = 0
    batch_id = f"pbat_auto_{now.strftime('%Y%m')}"
    reference = f"auto-batch {now.strftime('%B %Y')}"
    async for p in db.marketing_partners.find({"status": "active"}, {"_id": 0, "partner_id": 1}):
        res = await db.marketing_partner_earnings.update_many(
            {"partner_id": p["partner_id"], "status": "unpaid"},
            {
                "$set": {
                    "status": "paid",
                    "paid_at": datetime.now(timezone.utc).isoformat(),
                    "paid_by": "scheduler",
                    "payout_batch_id": batch_id,
                    "payout_reference": reference,
                }
            },
        )
        if res.modified_count:
            partner_count += 1
            total_marked += res.modified_count

    await db.cron_runs.update_one(
        job_key,
        {"$set": {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "done",
            "earnings_marked_paid": total_marked,
            "partners_touched": partner_count,
            "batch_id": batch_id,
        }},
    )
    logger.info(f"[cron-partner-payout] {period_key} → {total_marked} earnings across {partner_count} partners (batch {batch_id})")
    return {"earnings_marked_paid": total_marked, "partners_touched": partner_count, "batch_id": batch_id}


async def _dispatch_due_flyer_campaigns(db: Any) -> int:
    """Pick up `flyer_campaigns` whose `scheduled_for` is now-or-past and send
    them in 200-recipient chunks. Each successfully-sent email's Resend
    message-id is stamped on the campaign so the webhook can compute opens /
    clicks later.

    Called from the fast (60s) loop, NOT the hourly tick.
    """
    from emails import send_template as _send_template

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = db.flyer_campaigns.find(
        {"status": "scheduled", "scheduled_for": {"$lte": now_iso}},
    ).limit(5)  # bound per tick so we never block the loop too long

    dispatched = 0
    async for camp in cursor:
        cid = camp["campaign_id"]
        # Claim atomically so two replicas don't double-send.
        claim = await db.flyer_campaigns.update_one(
            {"campaign_id": cid, "status": "scheduled"},
            {"$set": {"status": "sending", "started_at": now_iso}},
        )
        if claim.modified_count == 0:
            continue

        kind = camp["kind"]
        emails = camp.get("emails") or []
        # Name lookup for personalized salutations.
        name_lookup: dict = {}
        async for u in db.users.find({"email": {"$in": emails}}, {"_id": 0, "email": 1, "name": 1}):
            name_lookup[u["email"]] = u.get("name") or "there"

        sent, failed, resend_map = 0, 0, {}
        # 200-recipient chunks, brief sleep between chunks to respect Resend rate limit.
        chunk_size = 200
        for i in range(0, len(emails), chunk_size):
            chunk = emails[i:i + chunk_size]
            for email in chunk:
                try:
                    res = await _send_template(kind, email, {"name": name_lookup.get(email, "there")}, db)
                    if res.get("status") == "sent":
                        sent += 1
                        rid = res.get("resend_id")
                        if rid:
                            resend_map[email.replace(".", "_DOT_")] = rid
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            if i + chunk_size < len(emails):
                await asyncio.sleep(1)  # short breath between chunks

        await db.flyer_campaigns.update_one(
            {"campaign_id": cid},
            {"$set": {
                "status": "sent",
                "sent_count": sent,
                "failed_count": failed,
                "resend_ids": resend_map,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"[scheduler] flyer campaign {cid} dispatched: sent={sent} failed={failed}")
        dispatched += 1
    return dispatched


async def fast_loop(db: Any, interval_seconds: int = 60) -> None:
    """High-cadence loop for tasks that need minute-level precision.

    Currently dispatches due `flyer_campaigns`. Could host future things like
    flash-sale start triggers without disturbing the hourly scheduler.
    """
    await asyncio.sleep(15)
    while True:
        try:
            await _dispatch_due_flyer_campaigns(db)
        except Exception as exc:  # pragma: no cover
            logger.exception("[fast-loop] tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def scheduler_loop(db: Any, interval_seconds: int = 3600) -> None:
    """Top-level loop — sleeps 30s on startup, then ticks every `interval_seconds`."""
    await asyncio.sleep(30)
    while True:
        try:
            n_reminders = await _send_24h_reminders(db)
            n_nps = await _send_post_event_nps(db)
            n_digest = await _send_weekly_digest(db)
            n_nudge = await _send_stripe_setup_nudges(db)
            n_fdigest = await _send_follower_weekly_digest(db)
            n_welcome = await _send_organizer_welcome_followups(db)
            n_boost = await _send_boost_recaps(db)
            n_recap = await _send_event_recaps(db)
            n_statements = await _send_monthly_partner_statements(db)
            payout_batch = await _run_monthly_partner_payouts(db)
            webhook_alert = await _check_webhook_silent_failure(db)
            payout_summary = await run_due_event_payouts(db)
            if n_reminders or n_nps or n_digest or n_nudge or n_fdigest or n_welcome or n_boost or n_recap or n_statements or payout_batch or webhook_alert or payout_summary.get("paid") or payout_summary.get("failed"):
                logger.info(
                    "[scheduler] reminders=%s nps=%s digest=%s nudges=%s fdigest=%s welcome=%s boost_recaps=%s event_recaps=%s monthly_statements=%s partner_payout_batch=%s webhook_alert=%s payouts=%s",
                    n_reminders, n_nps, n_digest, n_nudge, n_fdigest, n_welcome, n_boost, n_recap, n_statements, payout_batch, webhook_alert, payout_summary,
                )
        except Exception as exc:  # pragma: no cover
            logger.exception("[scheduler] tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)
