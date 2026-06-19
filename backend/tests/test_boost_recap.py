"""Boost recap — email template renders + scheduler picks up expired boosts."""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from emails import TEMPLATES  # noqa: E402


def test_boost_recap_template_renders_with_full_ctx():
    assert "boost_recap" in TEMPLATES
    subject, html, text = TEMPLATES["boost_recap"]({
        "organizer_name": "Sarah",
        "event_title": "Garba Night",
        "boost_tier": "1day",
        "boost_kind": "paid",
        "during_views": 142,
        "during_bookings": 18,
        "view_lift_pct": 47.5,
        "booking_lift_pct": 80.0,
    })
    assert "Garba Night" in subject
    assert "Sarah" in html
    assert "142" in html and "18" in html
    assert "+47.5%" in html and "+80.0%" in html
    assert "Garba Night" in text


def test_boost_recap_template_handles_missing_stats():
    subject, html, text = TEMPLATES["boost_recap"]({
        "organizer_name": "there",
        "event_title": "Comedy Night",
        "boost_tier": None,
        "boost_kind": "free",
        "during_views": None,
        "during_bookings": None,
        "view_lift_pct": None,
        "booking_lift_pct": None,
    })
    # Should render — None values display as "—"
    assert "Comedy Night" in subject
    assert "—" in html


def test_scheduler_marks_expired_boosts_and_stamps():
    """Insert a fake expired boost → run the recap fn → row should be stamped."""
    from scheduler import _send_boost_recaps

    async def run():
        event_id = f"evt_{uuid.uuid4().hex[:10]}"
        owner_id = f"u_{uuid.uuid4().hex[:8]}"
        now = utc_now()
        try:
            await db.users.insert_one({
                "user_id": owner_id, "email": "test-recap@example.com", "name": "Test Owner",
            })
            await db.events.insert_one({
                "event_id": event_id,
                "organizer_id": owner_id,
                "title": "Expired Boost Test",
                "date": (now + timedelta(days=10)).isoformat(),
                "boosted_at": (now - timedelta(days=2)).isoformat(),
                "boosted_until": (now - timedelta(hours=2)).isoformat(),
                "last_boost_kind": "paid",
                "last_boost_tier": "1day",
            })
            sent = await _send_boost_recaps(db)
            assert sent >= 1
            stamped = await db.events.find_one({"event_id": event_id}, {"_id": 0, "boost_recap_sent_at": 1})
            assert stamped and stamped.get("boost_recap_sent_at")
            # Second run is a no-op
            sent2 = await _send_boost_recaps(db)
            stamped2 = await db.events.find_one({"event_id": event_id}, {"_id": 0, "boost_recap_sent_at": 1})
            assert stamped["boost_recap_sent_at"] == stamped2["boost_recap_sent_at"]
            # sent2 should not increment for THIS event
            assert sent2 <= sent  # may pick up other test residue, but our row didn't re-send
        finally:
            await db.events.delete_one({"event_id": event_id})
            await db.users.delete_one({"user_id": owner_id})

    asyncio.get_event_loop().run_until_complete(run())
