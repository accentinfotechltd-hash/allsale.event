"""Regression tests for past-event auto-archival.

An event becomes "past" (i.e. removed from public listings + recommendations)
once its start `date` is older than `EVENT_FINISHED_GRACE_HOURS` (default 24h).
Direct-link access to the event detail still works but returns `is_past=True`
so the UI can disable booking.

Uses HTTP against the running uvicorn server (same pattern as the other
iteration tests) to sidestep motor event-loop reuse issues.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import utc_now  # noqa: E402
from routers.events import EVENT_FINISHED_GRACE_HOURS, _is_event_past  # noqa: E402

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module", autouse=True)
def _seed_and_cleanup():
    """Seed one future + one finished event, then tear them down."""
    future_iso = (utc_now() + timedelta(days=30)).isoformat()
    past_iso = (utc_now() - timedelta(hours=EVENT_FINISHED_GRACE_HOURS + 5)).isoformat()
    future_id = f"evt_pasttest_future_{uuid.uuid4().hex[:8]}"
    past_id = f"evt_pasttest_past_{uuid.uuid4().hex[:8]}"

    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        base = {
            "organizer_id": "org_pasttest",
            "organizer_name": "Past Test Org",
            "description": "x",
            "category": "music",
            "venue": "Venue",
            "city": "Auckland",
            "image_url": "https://example.com/x.jpg",
            "tiers": [{"name": "Standard", "price": 10, "capacity": 100}],
            "has_seatmap": False,
            "status": "approved",
            "currency": "NZD",
        }
        await db.events.insert_many([
            {**base, "event_id": future_id, "date": future_iso, "title": "PASTTEST_FUTURE"},
            {**base, "event_id": past_id, "date": past_iso, "title": "PASTTEST_PAST", "featured": True},
        ])
        client.close()

    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.events.delete_many({"event_id": {"$in": [future_id, past_id]}})
        client.close()

    asyncio.run(_seed())
    yield {"future_id": future_id, "past_id": past_id}
    try:
        asyncio.run(_clean())
    except Exception:
        pass


def test_past_helper():
    grace = EVENT_FINISHED_GRACE_HOURS
    long_ago = (utc_now() - timedelta(hours=grace + 1)).isoformat()
    just_now = (utc_now() - timedelta(hours=1)).isoformat()
    assert _is_event_past(long_ago) is True
    assert _is_event_past(just_now) is False
    assert _is_event_past(None) is False
    assert _is_event_past("") is False


def test_list_events_default_hides_past(_seed_and_cleanup):
    ids = _seed_and_cleanup
    r = requests.get(f"{API}/api/events", params={"limit": 200}, timeout=10)
    assert r.status_code == 200
    found_ids = {e["event_id"] for e in r.json()}
    assert ids["future_id"] in found_ids
    assert ids["past_id"] not in found_ids


def test_list_events_past_true_shows_past(_seed_and_cleanup):
    ids = _seed_and_cleanup
    r = requests.get(f"{API}/api/events", params={"past": "true", "limit": 200}, timeout=10)
    assert r.status_code == 200
    items = r.json()
    found_ids = {e["event_id"] for e in items}
    assert ids["past_id"] in found_ids
    assert ids["future_id"] not in found_ids
    past_entry = next(e for e in items if e["event_id"] == ids["past_id"])
    assert past_entry.get("is_past") is True


def test_featured_excludes_past(_seed_and_cleanup):
    ids = _seed_and_cleanup
    r = requests.get(f"{API}/api/events/featured", timeout=10)
    assert r.status_code == 200
    found_ids = {e["event_id"] for e in r.json()}
    assert ids["past_id"] not in found_ids


def test_event_detail_flags_is_past(_seed_and_cleanup):
    ids = _seed_and_cleanup
    r_past = requests.get(f"{API}/api/events/{ids['past_id']}", timeout=10)
    assert r_past.status_code == 200
    assert r_past.json().get("is_past") is True

    r_future = requests.get(f"{API}/api/events/{ids['future_id']}", timeout=10)
    assert r_future.status_code == 200
    assert r_future.json().get("is_past") is False
