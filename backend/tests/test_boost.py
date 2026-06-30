"""Self-serve boost endpoint — happy path, ownership, cooldown."""
from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers.events import boost_event, list_events  # noqa: E402


async def _seed(organizer_id):
    eid = f"evt_b_{uuid.uuid4().hex[:8]}"
    await db.events.insert_one({
        "event_id": eid, "organizer_id": organizer_id,
        "organizer_name": "BoostOrg",
        "title": "Boostable", "description": "x", "category": "music",
        "venue": "v", "city": "Auckland", "country": "NZ",
        "date": (utc_now() + timedelta(days=10)).isoformat(),
        "image_url": "https://example.com/x.jpg", "currency": "NZD",
        "tiers": [{"name": "GA", "price": 25.0, "capacity": 100}],
        "has_seatmap": False, "status": "approved",
        "created_at": utc_now().isoformat(),
    })
    return eid


async def test_boost_sets_boosted_until_and_listing_flag():
    org = f"org_{uuid.uuid4().hex[:6]}"
    eid = await _seed(org)
    try:
        user = {"user_id": org, "role": "organizer", "name": "Me", "email": "me@t.local"}
        r = await boost_event(eid, user)
        assert r["ok"] is True
        assert r["boosted_until"] > utc_now().isoformat()
        # Listing now annotates is_boosted=True for this event
        items = await list_events(q=None, category=None, city=None, country=None, past=False, limit=100)
        mine = next((e for e in items if e["event_id"] == eid), None)
        assert mine and mine["is_boosted"] is True
    finally:
        await db.events.delete_one({"event_id": eid})



async def test_boost_rejects_non_owner():
    owner = f"org_{uuid.uuid4().hex[:6]}"
    other = f"org_{uuid.uuid4().hex[:6]}"
    eid = await _seed(owner)
    try:
        user = {"user_id": other, "role": "organizer", "name": "Other", "email": "o@t.local"}
        with pytest.raises(HTTPException) as ex:
            await boost_event(eid, user)
        assert ex.value.status_code == 403
    finally:
        await db.events.delete_one({"event_id": eid})



async def test_boost_cooldown_blocks_repeat_within_window():
    org = f"org_{uuid.uuid4().hex[:6]}"
    eid = await _seed(org)
    try:
        user = {"user_id": org, "role": "organizer", "name": "Me", "email": "me@t.local"}
        await boost_event(eid, user)
        with pytest.raises(HTTPException) as ex:
            await boost_event(eid, user)
        assert ex.value.status_code == 429
        assert "cooldown" in ex.value.detail.lower()
    finally:
        await db.events.delete_one({"event_id": eid})



async def test_boost_admin_can_boost_anyone():
    org = f"org_{uuid.uuid4().hex[:6]}"
    eid = await _seed(org)
    try:
        admin = {"user_id": "admin", "role": "admin", "name": "Admin", "email": "admin@t.local"}
        r = await boost_event(eid, admin)
        assert r["ok"] is True
    finally:
        await db.events.delete_one({"event_id": eid})

