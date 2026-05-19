"""Iteration 12 — AI recommendations + Dynamic pricing + Waitlist count badge."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import compute_tier_effective_price  # noqa: E402

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_module():
    yield
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_dyn_test_|^evt_rec_test_"}},
            {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.bookings.delete_many({"event_id": {"$in": ids}})
        client.close()
    try: asyncio.run(_clean())
    except Exception: pass


# ---------------------------------------------------------------------------
# Dynamic pricing math
# ---------------------------------------------------------------------------
def test_dynamic_pricing_disabled_uses_base():
    event = {"dynamic_pricing": {"enabled": False}}
    tier = {"price": 50.0, "capacity": 100}
    price, surging = compute_tier_effective_price(event, tier, sold=99)
    assert price == 50.0 and surging is False


def test_dynamic_pricing_above_threshold():
    event = {"dynamic_pricing": {"enabled": True, "surge_threshold_pct": 30, "surge_multiplier": 1.5}}
    tier = {"price": 50.0, "capacity": 100}
    # 50% remaining > 30% threshold → no surge
    price, surging = compute_tier_effective_price(event, tier, sold=50)
    assert price == 50.0 and surging is False


def test_dynamic_pricing_at_threshold():
    event = {"dynamic_pricing": {"enabled": True, "surge_threshold_pct": 30, "surge_multiplier": 1.5}}
    tier = {"price": 50.0, "capacity": 100}
    # 70 sold → 30% remaining → threshold reached → surge
    price, surging = compute_tier_effective_price(event, tier, sold=70)
    assert price == 75.0 and surging is True


def test_dynamic_pricing_multiplier_clamped():
    event = {"dynamic_pricing": {"enabled": True, "surge_threshold_pct": 30, "surge_multiplier": 100}}
    tier = {"price": 50.0, "capacity": 100}
    price, _ = compute_tier_effective_price(event, tier, sold=90)
    # Multiplier capped at 3.0
    assert price == 150.0


# ---------------------------------------------------------------------------
# Dynamic pricing endpoint (PATCH /organizer/events/{id}/dynamic-pricing)
# ---------------------------------------------------------------------------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


async def _seed_tier_event() -> str:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    org = await db.users.find_one({"email": "organizer@allsale.events"}, {"_id": 0})
    eid = f"evt_dyn_test_{uuid.uuid4().hex[:6]}"
    await db.events.insert_one({
        "event_id": eid, "title": "Dyn Test",
        "organizer_id": org["user_id"], "category": "music",
        "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
        "image_url": "", "status": "approved",
        "tiers": [{"name": "GA", "price": 100.0, "capacity": 100, "sold": 0}],
        "has_seatmap": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    client.close()
    return eid


def test_set_dynamic_pricing_organizer_can():
    eid = asyncio.run(_seed_tier_event())
    token = _login("organizer@allsale.events", "organizer123")
    r = requests.patch(
        f"{API}/api/organizer/events/{eid}/dynamic-pricing",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": True, "surge_threshold_pct": 25, "surge_multiplier": 1.5},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json()["dynamic_pricing"]["enabled"] is True


def test_set_dynamic_pricing_validates_bounds():
    eid = asyncio.run(_seed_tier_event())
    token = _login("organizer@allsale.events", "organizer123")
    r = requests.patch(
        f"{API}/api/organizer/events/{eid}/dynamic-pricing",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": True, "surge_threshold_pct": 200, "surge_multiplier": 1.5},
        timeout=10,
    )
    assert r.status_code in (400, 422)


def test_event_detail_returns_effective_price():
    """Seed a tier-event with 75 of 100 capacity filled, enable surge, fetch endpoint."""
    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        org = await db.users.find_one({"email": "organizer@allsale.events"}, {"_id": 0})
        eid = f"evt_dyn_test_{uuid.uuid4().hex[:6]}"
        await db.events.insert_one({
            "event_id": eid, "title": "Surge Test",
            "organizer_id": org["user_id"], "category": "music",
            "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
            "image_url": "", "status": "approved",
            "tiers": [{"name": "GA", "price": 100.0, "capacity": 100, "sold": 0}],
            "has_seatmap": False,
            "dynamic_pricing": {"enabled": True, "surge_threshold_pct": 30, "surge_multiplier": 1.5},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Fill 75 of 100 → 25% remaining → surge fires
        for i in range(75):
            await db.bookings.insert_one({
                "booking_id": f"bkg_dyn_fill_{uuid.uuid4().hex[:8]}",
                "event_id": eid, "event_title": "Surge Test",
                "event_date": "2026-12-31T20:00:00+00:00",
                "user_id": f"u_{i}", "user_email": f"u{i}@example.com",
                "user_name": f"u {i}", "tier_name": "GA",
                "quantity": 1, "seats": [], "amount": 100.0,
                "currency": "usd", "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        client.close()
        return eid

    eid = asyncio.run(_setup())
    body = requests.get(f"{API}/api/events/{eid}", timeout=10).json()
    ga = body["tiers"][0]
    assert ga["surging"] is True
    assert ga["effective_price"] == 150.0
    assert body["surging"] is True


# ---------------------------------------------------------------------------
# Waitlist count surfacing in /events list
# ---------------------------------------------------------------------------
def test_events_list_includes_waitlist_count_when_present():
    """Seed a tier event, mark it sold out via filled bookings, register a user, join waitlist, then check /events shows waitlist_count."""
    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        org = await db.users.find_one({"email": "organizer@allsale.events"}, {"_id": 0})
        eid = f"evt_dyn_test_wl_{uuid.uuid4().hex[:6]}"
        await db.events.insert_one({
            "event_id": eid, "title": "WL Count Test",
            "organizer_id": org["user_id"], "category": "music",
            "city": "wl_count_city", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
            "image_url": "", "status": "approved",
            "tiers": [{"name": "GA", "price": 25.0, "capacity": 1, "sold": 0}],
            "has_seatmap": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.bookings.insert_one({
            "booking_id": f"bkg_wlc_{uuid.uuid4().hex[:6]}", "event_id": eid,
            "event_title": "WL Count Test", "event_date": "2026-12-31T20:00:00+00:00",
            "user_id": "u_fill", "user_email": "fill@example.com", "user_name": "fill",
            "tier_name": "GA", "quantity": 1, "amount": 25,
            "currency": "usd", "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()
        return eid

    eid = asyncio.run(_seed())
    # Register & join waitlist
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"wlc_{suffix}@example.com", "password": "TestPass123!",
        "name": f"WLC {suffix}", "role": "attendee",
    }, timeout=10)
    token = r.json()["token"]
    requests.post(f"{API}/api/events/{eid}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    # List events filtered by city
    items = requests.get(f"{API}/api/events?city=wl_count_city", timeout=10).json()
    target = next((e for e in items if e["event_id"] == eid), None)
    assert target is not None
    assert target.get("waitlist_count") == 1
    # Cleanup waitlist user
    async def _cleanup_user():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.delete_many({"email": f"wlc_{suffix}@example.com"})
        client.close()
    asyncio.run(_cleanup_user())


# ---------------------------------------------------------------------------
# Recommendations endpoint
# ---------------------------------------------------------------------------
def test_recommendations_requires_auth():
    r = requests.get(f"{API}/api/me/recommendations", timeout=10)
    assert r.status_code == 401


def test_recommendations_returns_items_for_new_user():
    """New user with no past bookings should get trending fallback."""
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"rec_new_{suffix}@example.com", "password": "TestPass123!",
        "name": f"RecNew {suffix}", "role": "attendee",
    }, timeout=10)
    token = r.json()["token"]
    r = requests.get(f"{API}/api/me/recommendations",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) > 0
    assert "event" in body["items"][0]
    assert "reason" in body["items"][0]


def test_recommendations_returns_cached_on_second_call():
    """Second call within TTL should be served from cache."""
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"rec_cache_{suffix}@example.com", "password": "TestPass123!",
        "name": f"RecCache {suffix}", "role": "attendee",
    }, timeout=10)
    token = r.json()["token"]
    first = requests.get(f"{API}/api/me/recommendations",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15).json()
    second = requests.get(f"{API}/api/me/recommendations",
                          headers={"Authorization": f"Bearer {token}"}, timeout=15).json()
    assert second.get("cached") is True
    assert len(first["items"]) == len(second["items"])
