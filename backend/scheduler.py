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


async def scheduler_loop(db: Any, interval_seconds: int = 3600) -> None:
    """Top-level loop — sleeps 30s on startup, then ticks every `interval_seconds`."""
    await asyncio.sleep(30)
    while True:
        try:
            n_reminders = await _send_24h_reminders(db)
            n_digest = await _send_weekly_digest(db)
            if n_reminders or n_digest:
                logger.info("[scheduler] reminders=%s digest=%s", n_reminders, n_digest)
        except Exception as exc:  # pragma: no cover
            logger.exception("[scheduler] tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)
