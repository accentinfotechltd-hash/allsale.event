"""Iteration 17 — Event-views tracking + Demand sparkline + Sales velocity."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_module():
    yield
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_demand_test_"}}, {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.bookings.delete_many({"event_id": {"$in": ids}})
            await db.event_views.delete_many({"event_id": {"$in": ids}})
        client.close()
    try: asyncio.run(_clean())
    except Exception: pass


def _organizer_token() -> str:
    r = requests.post(f"{API}/api/auth/login", json={
        "email": "organizer@aura.events", "password": "organizer123",
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


async def _seed_event(capacity: int = 100, with_sales: int = 0) -> str:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    org = await db.users.find_one({"email": "organizer@aura.events"}, {"_id": 0})
    eid = f"evt_demand_test_{uuid.uuid4().hex[:6]}"
    await db.events.insert_one({
        "event_id": eid, "title": "Demand Test",
        "organizer_id": org["user_id"], "category": "music",
        "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
        "image_url": "", "status": "approved",
        "tiers": [{"name": "GA", "price": 25, "capacity": capacity, "sold": 0}],
        "has_seatmap": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    now = datetime.now(timezone.utc)
    for i in range(with_sales):
        # Spread sales across last 7 days
        paid_at = (now - timedelta(hours=i * 12)).isoformat()
        await db.bookings.insert_one({
            "booking_id": f"bkg_d_{uuid.uuid4().hex[:8]}", "event_id": eid,
            "event_title": "Demand Test", "event_date": "2026-12-31T20:00:00+00:00",
            "user_id": f"u_{i}", "user_email": f"u{i}@x.com", "user_name": f"u{i}",
            "tier_name": "GA", "quantity": 1, "amount": 25,
            "currency": "usd", "status": "paid",
            "paid_at": paid_at, "created_at": paid_at,
        })
    client.close()
    return eid


# ---------------------------------------------------------------------------
# View tracking
# ---------------------------------------------------------------------------
def test_view_endpoint_works_anonymously():
    eid = asyncio.run(_seed_event())
    r = requests.post(f"{API}/api/events/{eid}/view", timeout=10)
    assert r.status_code == 200


def test_view_endpoint_works_authenticated():
    eid = asyncio.run(_seed_event())
    token = _organizer_token()
    r = requests.post(f"{API}/api/events/{eid}/view",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200


def test_view_404_for_unknown_event():
    r = requests.post(f"{API}/api/events/evt_nonexistent_xyz/view", timeout=10)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Demand sparkline
# ---------------------------------------------------------------------------
def test_demand_endpoint_returns_7_buckets():
    eid = asyncio.run(_seed_event())
    # Record 3 views
    for _ in range(3):
        requests.post(f"{API}/api/events/{eid}/view", timeout=10)
    r = requests.get(f"{API}/api/events/{eid}/demand", timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 7
    # Each bucket has expected shape
    for bucket in items:
        assert "date" in bucket and "views" in bucket and "bookings" in bucket
    # Total views ≥ 3
    total_views = sum(b["views"] for b in items)
    assert total_views >= 3


def test_demand_includes_bookings():
    eid = asyncio.run(_seed_event(with_sales=5))
    r = requests.get(f"{API}/api/events/{eid}/demand", timeout=10)
    items = r.json()["items"]
    total_bookings = sum(b["bookings"] for b in items)
    assert total_bookings == 5


# ---------------------------------------------------------------------------
# Velocity widget
# ---------------------------------------------------------------------------
def test_velocity_returns_metrics():
    eid = asyncio.run(_seed_event(capacity=50, with_sales=10))
    token = _organizer_token()
    r = requests.get(f"{API}/api/organizer/events/{eid}/velocity",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["capacity"] == 50
    assert body["sold"] == 10
    assert body["remaining"] == 40
    assert body["sold_7d"] == 10
    assert "forecast_label" in body


def test_velocity_no_sales_returns_label():
    eid = asyncio.run(_seed_event(capacity=50, with_sales=0))
    token = _organizer_token()
    r = requests.get(f"{API}/api/organizer/events/{eid}/velocity",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    body = r.json()
    assert body["sold"] == 0
    assert body["forecast_label"] in ("No sales yet", "Not enough data")
    assert body["forecast_days"] is None


def test_velocity_requires_organizer():
    eid = asyncio.run(_seed_event())
    # Anon
    r = requests.get(f"{API}/api/organizer/events/{eid}/velocity", timeout=10)
    assert r.status_code == 401


def test_velocity_blocks_other_organizers():
    """Organizer A's velocity for Organizer B's event → 403."""
    eid = asyncio.run(_seed_event())
    # Register a fresh organizer (not the seed organizer)
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"vel_other_{suffix}@example.com", "password": "TestPass123!",
        "name": f"Other {suffix}", "role": "organizer",
    }, timeout=10)
    other_token = r.json()["token"]
    r = requests.get(f"{API}/api/organizer/events/{eid}/velocity",
                     headers={"Authorization": f"Bearer {other_token}"}, timeout=10)
    assert r.status_code == 403
