"""Trending events endpoint — only returns currently-boosted, approved,
upcoming events; sorted by `boosted_at` desc."""
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
from routers.events import trending_events  # noqa: E402


def test_trending_only_returns_currently_boosted_approved_upcoming():
    async def run():
        now = utc_now()
        org = f"org_{uuid.uuid4().hex[:6]}"
        # 4 seeded events to cover the matrix
        boosted_now = f"evt_trA_{uuid.uuid4().hex[:6]}"
        boost_expired = f"evt_trB_{uuid.uuid4().hex[:6]}"
        not_approved = f"evt_trC_{uuid.uuid4().hex[:6]}"
        past_event = f"evt_trD_{uuid.uuid4().hex[:6]}"

        base = lambda: {
            "organizer_id": org, "organizer_name": "TrendOrg",
            "description": "x", "category": "music", "venue": "v",
            "city": "Auckland", "country": "NZ",
            "image_url": "https://example.com/x.jpg", "currency": "NZD",
            "tiers": [{"name": "GA", "price": 25.0, "capacity": 100}],
            "has_seatmap": False,
            "created_at": now.isoformat(),
        }
        await db.events.insert_many([
            {**base(), "event_id": boosted_now, "title": "Visible",
             "status": "approved", "date": (now + timedelta(days=5)).isoformat(),
             "boosted_at": now.isoformat(),
             "boosted_until": (now + timedelta(hours=24)).isoformat()},
            {**base(), "event_id": boost_expired, "title": "ExpiredBoost",
             "status": "approved", "date": (now + timedelta(days=5)).isoformat(),
             "boosted_at": (now - timedelta(days=5)).isoformat(),
             "boosted_until": (now - timedelta(hours=1)).isoformat()},
            {**base(), "event_id": not_approved, "title": "Draft",
             "status": "pending", "date": (now + timedelta(days=5)).isoformat(),
             "boosted_at": now.isoformat(),
             "boosted_until": (now + timedelta(hours=24)).isoformat()},
            {**base(), "event_id": past_event, "title": "Old",
             "status": "approved", "date": (now - timedelta(days=10)).isoformat(),
             "boosted_at": now.isoformat(),
             "boosted_until": (now + timedelta(hours=24)).isoformat()},
        ])
        try:
            items = await trending_events(limit=12)
            ids = {i["event_id"] for i in items}
            # ONLY the live-boosted, approved, upcoming event is included
            assert boosted_now in ids
            assert boost_expired not in ids
            assert not_approved not in ids
            assert past_event not in ids
            # All returned items are flagged is_boosted=True
            assert all(i.get("is_boosted") is True for i in items)
        finally:
            await db.events.delete_many({"event_id": {"$in": [boosted_now, boost_expired, not_approved, past_event]}})

    asyncio.get_event_loop().run_until_complete(run())


def test_trending_sorts_newest_boost_first():
    async def run():
        now = utc_now()
        org = f"org_{uuid.uuid4().hex[:6]}"
        older = f"evt_tr_old_{uuid.uuid4().hex[:6]}"
        newer = f"evt_tr_new_{uuid.uuid4().hex[:6]}"
        base = {
            "organizer_id": org, "organizer_name": "TrendOrg", "description": "x",
            "category": "music", "venue": "v", "city": "Auckland", "country": "NZ",
            "image_url": "https://example.com/x.jpg", "currency": "NZD",
            "tiers": [{"name": "GA", "price": 25.0, "capacity": 100}],
            "has_seatmap": False, "status": "approved",
            "boosted_until": (now + timedelta(hours=24)).isoformat(),
            "date": (now + timedelta(days=5)).isoformat(),
            "created_at": now.isoformat(),
        }
        await db.events.insert_many([
            {**base, "event_id": older, "title": "Older boost", "boosted_at": (now - timedelta(hours=10)).isoformat()},
            {**base, "event_id": newer, "title": "Newer boost", "boosted_at": (now - timedelta(minutes=1)).isoformat()},
        ])
        try:
            items = await trending_events(limit=12)
            order = [i["event_id"] for i in items if i["event_id"] in (older, newer)]
            assert order == [newer, older]
        finally:
            await db.events.delete_many({"event_id": {"$in": [older, newer]}})

    asyncio.get_event_loop().run_until_complete(run())
