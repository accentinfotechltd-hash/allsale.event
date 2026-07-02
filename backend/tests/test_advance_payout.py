"""Advance-payout opt-in + 1-week-out admin digest scheduler.

Covers:
  • EventIn accepts advance_payout_enabled=True and persists it on the doc.
  • Scheduler window: 09:00–10:00 UTC only.
  • Scheduler window: only events between now+6d and now+8d qualify.
  • Only opted-in, non-draft, non-notified events surface.
  • Amount = 50% of face_value across paid + confirmed bookings.
  • advance_payout_notified_at is stamped so tomorrow's tick doesn't re-send.
  • Email template registers + renders with the right subject.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
import scheduler as sched  # noqa: E402
from emails import TEMPLATES  # noqa: E402
from models import EventIn  # noqa: E402
from routers import events as events_router  # noqa: E402


class _FakeRequest:
    def __init__(self):
        self.headers = {}


async def _make_admin():
    admin_id = f"admin_test_{uuid.uuid4().hex[:6]}"
    await db.users.update_one(
        {"user_id": admin_id},
        {"$set": {
            "user_id": admin_id, "name": "Admin", "role": "admin",
            "email": f"admin_{uuid.uuid4().hex[:6]}@example.com",
        }},
        upsert=True,
    )
    return await db.users.find_one({"user_id": admin_id}, {"_id": 0})


async def _cleanup_user(user_id):
    await db.users.delete_one({"user_id": user_id})


async def _cleanup_event(event_id):
    await db.events.delete_one({"event_id": event_id})
    await db.bookings.delete_many({"event_id": event_id})


# ---------------------------------------------------------------------------
# 1. Persistence — the flag survives round-trip through the API.
# ---------------------------------------------------------------------------
async def test_advance_payout_flag_persists_on_create_and_edit():
    admin = await _make_admin()
    payload = EventIn(
        title=f"Advance Test {uuid.uuid4().hex[:6]}",
        description="pytest", category="music", venue="V", city="Auckland",
        country="NZ", timezone="Pacific/Auckland",
        date="2027-06-15T20:00:00Z", image_url="https://example.com/x.jpg",
        tiers=[{"name": "General", "price": 50, "capacity": 100}],
        advance_payout_enabled=True,
    )
    result = await events_router.create_event(payload, _FakeRequest(), admin)
    try:
        assert result["advance_payout_enabled"] is True

        # PATCH turns it off
        updated = await events_router.update_event(
            result["event_id"], {"advance_payout_enabled": False}, admin,
        )
        assert updated["advance_payout_enabled"] is False
    finally:
        await _cleanup_event(result["event_id"])
        await _cleanup_user(admin["user_id"])


# ---------------------------------------------------------------------------
# 2. Scheduler only fires between 09:00 and 10:00 UTC.
# ---------------------------------------------------------------------------
async def test_scheduler_respects_hour_window():
    fake_now = datetime(2026, 3, 1, 3, 0, tzinfo=timezone.utc)  # 03:00 UTC
    with patch("scheduler.datetime") as mocked_dt:
        mocked_dt.now.return_value = fake_now
        mocked_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        n = await sched._send_advance_payout_admin_digest(db)
    assert n == 0


# ---------------------------------------------------------------------------
# 3. Scheduler picks up opted-in events in the +7d window and stamps them.
# ---------------------------------------------------------------------------
async def test_scheduler_notifies_and_stamps_events_in_window():
    admin = await _make_admin()
    now = datetime.now(timezone.utc)
    # Event date is 7 days out — squarely inside the [now+6d, now+8d] window.
    event_date = (now + timedelta(days=7)).isoformat()
    event_id = f"evt_test_{uuid.uuid4().hex[:8]}"
    await db.events.insert_one({
        "event_id": event_id,
        "title": "Advance-Enabled Test",
        "organizer_id": admin["user_id"],
        "organizer_name": "Test Organizer",
        "status": "approved",
        "date": event_date,
        "currency": "NZD",
        "advance_payout_enabled": True,
        "created_at": utc_now().isoformat(),
    })
    # Seed one paid booking so face_total > 0.
    await db.bookings.insert_one({
        "booking_id": f"bk_test_{uuid.uuid4().hex[:6]}",
        "event_id": event_id,
        "status": "paid",
        "face_value": 400,
        "amount": 425,
        "currency": "NZD",
        "created_at": utc_now().isoformat(),
    })
    try:
        # Force the scheduler into the 09:00–10:00 window and pin now.
        fake_now = now.replace(hour=9, minute=15, second=0, microsecond=0)
        with patch("scheduler.datetime") as mocked_dt:
            mocked_dt.now.return_value = fake_now
            # Any other datetime construction inside the function delegates
            # to the real class.
            mocked_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("scheduler.send_template_fireforget") as mock_send:
                sent = await sched._send_advance_payout_admin_digest(db)

        assert sent >= 1, "at least one admin should have been emailed"
        assert mock_send.called
        # Inspect the email context: should include our event with $200 advance.
        call_kwargs = mock_send.call_args
        template_name, admin_email, ctx, _db = call_kwargs.args
        assert template_name == "admin_advance_payout_due_digest"
        assert ctx["count"] >= 1
        our_row = next((e for e in ctx["events"] if e["event_id"] == event_id), None)
        assert our_row is not None
        assert our_row["collected_amount"] == 400.0
        assert our_row["advance_amount"] == 200.0
        assert our_row["stripe_connected"] is False

        # Event doc must now be stamped so tomorrow's tick skips it.
        after = await db.events.find_one({"event_id": event_id}, {"_id": 0})
        assert after.get("advance_payout_notified_at")

        # Second run in the same window must NOT re-send that event.
        with patch("scheduler.datetime") as mocked_dt:
            mocked_dt.now.return_value = fake_now
            mocked_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("scheduler.send_template_fireforget") as mock_send2:
                await sched._send_advance_payout_admin_digest(db)
                # our event should be excluded now; if there's nothing else
                # in the window, send is not called.
                for call in mock_send2.call_args_list:
                    _, _, ctx2, _ = call.args
                    assert not any(e["event_id"] == event_id for e in ctx2.get("events", []))
    finally:
        await _cleanup_event(event_id)
        await _cleanup_user(admin["user_id"])


# ---------------------------------------------------------------------------
# 4. Events OUTSIDE the +7d window are ignored.
# ---------------------------------------------------------------------------
async def test_scheduler_skips_events_outside_window():
    admin = await _make_admin()
    now = datetime.now(timezone.utc)
    # Event is 30 days out — nowhere near the 1-week trigger.
    far_id = f"evt_test_{uuid.uuid4().hex[:8]}"
    await db.events.insert_one({
        "event_id": far_id,
        "title": "Too Far Out",
        "organizer_id": admin["user_id"],
        "status": "approved",
        "date": (now + timedelta(days=30)).isoformat(),
        "advance_payout_enabled": True,
        "created_at": utc_now().isoformat(),
    })
    try:
        fake_now = now.replace(hour=9, minute=15, second=0, microsecond=0)
        with patch("scheduler.datetime") as mocked_dt:
            mocked_dt.now.return_value = fake_now
            mocked_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("scheduler.send_template_fireforget") as mock_send:
                await sched._send_advance_payout_admin_digest(db)
                for call in mock_send.call_args_list:
                    _, _, ctx, _ = call.args
                    assert not any(e["event_id"] == far_id for e in ctx.get("events", []))
    finally:
        await _cleanup_event(far_id)
        await _cleanup_user(admin["user_id"])


# ---------------------------------------------------------------------------
# 5. Non-opted-in events are ignored even in the window.
# ---------------------------------------------------------------------------
async def test_scheduler_skips_non_opted_in_events():
    admin = await _make_admin()
    now = datetime.now(timezone.utc)
    off_id = f"evt_test_{uuid.uuid4().hex[:8]}"
    await db.events.insert_one({
        "event_id": off_id,
        "title": "Opt Out",
        "organizer_id": admin["user_id"],
        "status": "approved",
        "date": (now + timedelta(days=7)).isoformat(),
        "advance_payout_enabled": False,
        "created_at": utc_now().isoformat(),
    })
    try:
        fake_now = now.replace(hour=9, minute=15, second=0, microsecond=0)
        with patch("scheduler.datetime") as mocked_dt:
            mocked_dt.now.return_value = fake_now
            mocked_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("scheduler.send_template_fireforget") as mock_send:
                await sched._send_advance_payout_admin_digest(db)
                for call in mock_send.call_args_list:
                    _, _, ctx, _ = call.args
                    assert not any(e["event_id"] == off_id for e in ctx.get("events", []))
    finally:
        await _cleanup_event(off_id)
        await _cleanup_user(admin["user_id"])


# ---------------------------------------------------------------------------
# 6. Email template renders cleanly.
# ---------------------------------------------------------------------------
def test_advance_payout_email_template_registered():
    assert "admin_advance_payout_due_digest" in TEMPLATES
    subject, html, text = TEMPLATES["admin_advance_payout_due_digest"]({
        "events": [
            {
                "event_id": "e1",
                "event_title": "Sample Concert",
                "event_date_iso": "2027-01-15T20:00:00Z",
                "currency": "NZD",
                "organizer_name": "Sample Organizer",
                "organizer_email": "org@example.com",
                "stripe_connected": False,
                "collected_amount": 1000.0,
                "advance_amount": 500.0,
                "bookings_count": 20,
            }
        ],
        "count": 1,
    })
    assert "advance payout" in subject.lower()
    assert "Sample Concert" in html
    assert "NZD 500.00" in html
    assert "Manual bank transfer" in html
    assert "Sample Organizer" in text
    assert "500.00" in text
