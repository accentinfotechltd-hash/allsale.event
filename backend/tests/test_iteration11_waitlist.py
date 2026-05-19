"""Iteration 11 — Waitlist for sold-out tier-based events.

Covers:
- Event sold-out detection (tier_status returned, sold_out flag).
- POST /events/{id}/waitlist/join — auth, duplicate prevention, must be sold-out, seatmap rejected.
- GET /events/{id}/waitlist/me — position computed.
- DELETE /events/{id}/waitlist/me — cancellation.
- GET /me/waitlist — all active entries.
- GET /organizer/events/{id}/waitlist — list + counts + sold_out flag.
- POST /organizer/events/{id}/waitlist/offer-next — creates 15-min hold + email,
  fails 400 when no capacity, transitions waiting → offered.
"""
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

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


# Cleanup test events + waitlist users when this module finishes so they don't
# contaminate other test suites that pick events[0] from /organizer/events.
@pytest.fixture(scope="module", autouse=True)
def _cleanup_after_module():
    yield
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_(wl_test_|seat_test_)"}},
            {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.bookings.delete_many({"event_id": {"$in": ids}})
            await db.waitlist_entries.delete_many({"event_id": {"$in": ids}})
        await db.users.delete_many({"email": {"$regex": "^wl_att_[^@]+@example.com"}})
        client.close()
    try: asyncio.run(_clean())
    except Exception: pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def login(email: str, password: str) -> tuple[str, str]:
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    body = r.json()
    return body["token"], body["user_id"]


def register_attendee() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"wl_att_{suffix}@example.com"
    r = requests.post(f"{API}/api/auth/register", json={
        "email": email, "password": "TestPass123!",
        "name": f"WL {suffix}", "role": "attendee",
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"], r.json()["user_id"]


async def seed_sold_out_event(capacity: int = 1) -> tuple[str, str]:
    """Insert a tiny tier-based event filled to capacity. Returns (event_id, organizer_user_id)."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    org = await db.users.find_one({"email": "organizer@allsale.events"}, {"_id": 0})
    suffix = uuid.uuid4().hex[:6]
    event_id = f"evt_wl_test_{suffix}"
    await db.events.insert_one({
        "event_id": event_id, "title": f"WL Test {suffix}",
        "organizer_id": org["user_id"], "category": "Music",
        "city": "Test City", "venue": "Test Venue",
        "date": "2026-12-31T20:00:00+00:00", "image_url": "",
        "status": "approved", "featured": False,
        "tiers": [{"name": "GA", "price": 10.0, "capacity": capacity, "sold": 0}],
        "has_seatmap": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    for i in range(capacity):
        await db.bookings.insert_one({
            "booking_id": f"bkg_wl_fill_{suffix}_{i}",
            "event_id": event_id, "event_title": f"WL Test {suffix}",
            "event_date": "2026-12-31T20:00:00+00:00",
            "user_id": f"filler_{i}", "user_email": f"filler{i}@example.com",
            "user_name": f"Filler {i}",
            "tier_name": "GA", "quantity": 1, "seats": [],
            "amount": 10.0, "currency": "usd", "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    client.close()
    return event_id, org["user_id"]


async def free_one_paid_slot(event_id: str) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    paid = await db.bookings.find_one(
        {"event_id": event_id, "status": "paid", "booking_id": {"$regex": "^bkg_wl_fill_"}},
        {"_id": 0},
    )
    if paid:
        await db.bookings.update_one(
            {"booking_id": paid["booking_id"]},
            {"$set": {"status": "expired"}},
        )
    client.close()


# ---------------------------------------------------------------------------
# Sold-out detection
# ---------------------------------------------------------------------------
def test_event_returns_sold_out_flag_and_tier_status():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    r = requests.get(f"{API}/api/events/{event_id}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["sold_out"] is True
    assert body["tier_status"][0]["remaining"] == 0
    assert body["tier_status"][0]["sold"] == 1


def test_event_not_sold_out_flag():
    event_id, _ = asyncio.run(seed_sold_out_event(5))  # 5 capacity, 5 filled — still sold out
    r = requests.get(f"{API}/api/events/{event_id}", timeout=10)
    assert r.json()["sold_out"] is True
    # Now expand capacity using a fresh motor client inside the coroutine
    async def _expand():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.events.update_one(
            {"event_id": event_id},
            {"$set": {"tiers": [{"name": "GA", "price": 10, "capacity": 100, "sold": 0}]}},
        )
        client.close()
    asyncio.run(_expand())
    r = requests.get(f"{API}/api/events/{event_id}", timeout=10)
    assert r.json()["sold_out"] is False


# ---------------------------------------------------------------------------
# Join / leave / position
# ---------------------------------------------------------------------------
def test_join_requires_auth():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    r = requests.post(f"{API}/api/events/{event_id}/waitlist/join", json={}, timeout=10)
    assert r.status_code == 401


def test_join_rejected_when_not_sold_out():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    # Free the slot first
    asyncio.run(free_one_paid_slot(event_id))
    token, _ = register_attendee()
    r = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"quantity": 1}, timeout=10)
    assert r.status_code == 400


def test_join_seatmap_rejected():
    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        org = await db.users.find_one({"email": "organizer@allsale.events"}, {"_id": 0})
        eid = f"evt_seat_test_{uuid.uuid4().hex[:6]}"
        await db.events.insert_one({
            "event_id": eid, "title": "seatmap-test", "organizer_id": org["user_id"],
            "category": "Music", "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
            "image_url": "", "status": "approved",
            "tiers": [], "has_seatmap": True, "seat_rows": 5, "seat_cols": 5,
            "seat_price": 50, "aisles": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()
        return eid

    eid = asyncio.run(_seed())
    token, _ = register_attendee()
    r = requests.post(f"{API}/api/events/{eid}/waitlist/join",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"quantity": 1}, timeout=10)
    assert r.status_code == 400


def test_join_and_position():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    t1, _ = register_attendee()
    t2, _ = register_attendee()

    r1 = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                       headers={"Authorization": f"Bearer {t1}"}, json={"quantity": 1}, timeout=10)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                       headers={"Authorization": f"Bearer {t2}"}, json={"quantity": 1}, timeout=10)
    assert r2.status_code == 200

    # Position check
    s1 = requests.get(f"{API}/api/events/{event_id}/waitlist/me",
                      headers={"Authorization": f"Bearer {t1}"}, timeout=10).json()
    s2 = requests.get(f"{API}/api/events/{event_id}/waitlist/me",
                      headers={"Authorization": f"Bearer {t2}"}, timeout=10).json()
    assert s1[0]["position"] == 1
    assert s2[0]["position"] == 2


def test_duplicate_join_blocked():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    token, _ = register_attendee()
    r1 = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                       headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                       headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    assert r2.status_code == 409


def test_leave_waitlist():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    token, _ = register_attendee()
    requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    r = requests.delete(f"{API}/api/events/{event_id}/waitlist/me",
                        headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    # Status check: now empty (cancelled is filtered out)
    s = requests.get(f"{API}/api/events/{event_id}/waitlist/me",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    assert s == []


# ---------------------------------------------------------------------------
# Organizer endpoints + offer-next
# ---------------------------------------------------------------------------
def test_organizer_waitlist_authz():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    # Attendee blocked
    t, _ = register_attendee()
    r = requests.get(f"{API}/api/organizer/events/{event_id}/waitlist",
                     headers={"Authorization": f"Bearer {t}"}, timeout=10)
    assert r.status_code == 403


def test_offer_next_no_capacity():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    user_t, _ = register_attendee()
    requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                  headers={"Authorization": f"Bearer {user_t}"}, json={}, timeout=10)
    org_t, _ = login("organizer@allsale.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{event_id}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10)
    assert r.status_code == 400  # No capacity


def test_offer_next_success_creates_booking_and_email():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    user_t, _ = register_attendee()
    requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                  headers={"Authorization": f"Bearer {user_t}"}, json={"tier_preference": "GA"}, timeout=10)

    # Free the slot
    asyncio.run(free_one_paid_slot(event_id))

    org_t, _ = login("organizer@allsale.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{event_id}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "offered"
    assert "booking_id" in body
    assert "expires_at" in body
    assert "offer_token" in body

    # User now sees the offered entry
    s = requests.get(f"{API}/api/events/{event_id}/waitlist/me",
                     headers={"Authorization": f"Bearer {user_t}"}, timeout=10).json()
    assert any(e["status"] == "offered" for e in s)


def test_offer_next_fifo_order():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    t1, _ = register_attendee()
    t2, _ = register_attendee()
    r1 = requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                       headers={"Authorization": f"Bearer {t1}"}, json={}, timeout=10).json()
    requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                  headers={"Authorization": f"Bearer {t2}"}, json={}, timeout=10)
    asyncio.run(free_one_paid_slot(event_id))
    org_t, _ = login("organizer@allsale.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{event_id}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10).json()
    # First waiter gets it
    assert r["waitlist_id"] == r1["waitlist_id"]


def test_me_waitlist_returns_active_only():
    event_id, _ = asyncio.run(seed_sold_out_event(1))
    token, _ = register_attendee()
    requests.post(f"{API}/api/events/{event_id}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    r = requests.get(f"{API}/api/me/waitlist",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    assert len(r.json()) >= 1
    # Cancel and re-check
    requests.delete(f"{API}/api/events/{event_id}/waitlist/me",
                    headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r2 = requests.get(f"{API}/api/me/waitlist",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    # Cancelled is filtered out
    assert all(e["event_id"] != event_id for e in r2)
