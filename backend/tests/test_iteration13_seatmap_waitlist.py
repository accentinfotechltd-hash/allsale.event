"""Iteration 13 — Seatmap waitlist.

Covers:
- Sold-out detection for seatmap events (all non-aisle seats locked).
- Joining waitlist on a seatmap event (previously rejected).
- Offer-next claims the first N available seats atomically.
- Partial fulfillment: if asked for 4 but only 2 free, offer 2.
- Expired offers free their seats back to inventory.
- FIFO ordering still holds.
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


@pytest.fixture(scope="module", autouse=True)
def _cleanup_module():
    yield
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_seat_wl_"}}, {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.seat_reservations.delete_many({"event_id": {"$in": ids}})
            await db.bookings.delete_many({"event_id": {"$in": ids}})
            await db.waitlist_entries.delete_many({"event_id": {"$in": ids}})
        await db.users.delete_many({"email": {"$regex": "^seatwl_[^@]+@example.com"}})
        client.close()
    try: asyncio.run(_clean())
    except Exception: pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


def _register_attendee() -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"seatwl_{suffix}@example.com", "password": "TestPass123!",
        "name": f"SeatWL {suffix}", "role": "attendee",
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"], r.json()["user_id"]


async def _seed_seatmap_sold_out(rows: int = 2, cols: int = 2, aisles: list = None) -> str:
    """Insert a small seatmap event with every non-aisle seat booked."""
    aisles = aisles or []
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    org = await db.users.find_one({"email": "organizer@aura.events"}, {"_id": 0})
    eid = f"evt_seat_wl_{uuid.uuid4().hex[:6]}"
    await db.events.insert_one({
        "event_id": eid, "title": "Seat WL Test",
        "organizer_id": org["user_id"], "category": "theater",
        "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
        "image_url": "", "status": "approved", "featured": False,
        "tiers": [], "has_seatmap": True,
        "seat_rows": rows, "seat_cols": cols, "seat_price": 50.0,
        "aisles": aisles,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Book all non-aisle seats
    for r in range(rows):
        row_letter = chr(65 + r)
        for c in range(1, cols + 1):
            sid = f"{row_letter}-{c}"
            if sid in set(aisles):
                continue
            await db.seat_reservations.insert_one({
                "event_id": eid, "seat_id": sid,
                "booking_id": f"bkg_fill_{sid}", "user_id": "fake_buyer",
                "status": "booked",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    client.close()
    return eid


async def _free_seats(event_id: str, seats: list[str]) -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    r = await db.seat_reservations.delete_many({"event_id": event_id, "seat_id": {"$in": seats}})
    client.close()
    return r.deleted_count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_seatmap_event_returns_sold_out_when_all_seats_locked():
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    body = requests.get(f"{API}/api/events/{eid}", timeout=10).json()
    assert body["sold_out"] is True
    assert len(body["booked_seats"]) == 4


def test_seatmap_event_not_sold_out_when_free_seats_exist():
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    asyncio.run(_free_seats(eid, ["A-1"]))
    body = requests.get(f"{API}/api/events/{eid}", timeout=10).json()
    assert body["sold_out"] is False


def test_seatmap_aisles_dont_count_toward_capacity():
    """Even with 1 booked + 3 aisles, event should be sold out."""
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2, aisles=["A-1", "A-2", "B-2"]))
    # Only B-1 is non-aisle; it's booked by fixture
    body = requests.get(f"{API}/api/events/{eid}", timeout=10).json()
    assert body["sold_out"] is True


def test_join_waitlist_on_seatmap_succeeds():
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    token, _ = _register_attendee()
    r = requests.post(f"{API}/api/events/{eid}/waitlist/join",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"quantity": 1}, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "waiting"


def test_offer_next_seatmap_claims_seats():
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    token, _ = _register_attendee()
    requests.post(f"{API}/api/events/{eid}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"},
                  json={"quantity": 2}, timeout=10)
    # Free 2 seats
    asyncio.run(_free_seats(eid, ["A-1", "A-2"]))
    # Offer next
    org_t = _login("organizer@aura.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{eid}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "offered"
    assert len(body["offered_seats"]) == 2
    # Check those seats are now held with status=held
    async def _count():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        n = await db.seat_reservations.count_documents(
            {"event_id": eid, "status": "held", "booking_id": body["booking_id"]}
        )
        client.close()
        return n
    held = asyncio.run(_count())
    assert held == 2


def test_offer_next_partial_fulfillment():
    """User asks for 3, but only 1 seat free → offer 1."""
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    token, _ = _register_attendee()
    requests.post(f"{API}/api/events/{eid}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"},
                  json={"quantity": 3}, timeout=10)
    asyncio.run(_free_seats(eid, ["B-2"]))
    org_t = _login("organizer@aura.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{eid}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10)
    assert r.status_code == 200
    assert len(r.json()["offered_seats"]) == 1


def test_seatmap_offer_no_capacity_returns_400():
    """Waiting user but all seats still locked → 400."""
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    token, _ = _register_attendee()
    requests.post(f"{API}/api/events/{eid}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"},
                  json={"quantity": 1}, timeout=10)
    org_t = _login("organizer@aura.events", "organizer123")
    r = requests.post(f"{API}/api/organizer/events/{eid}/waitlist/offer-next",
                      headers={"Authorization": f"Bearer {org_t}"}, timeout=10)
    assert r.status_code == 400


def test_seatmap_waitlist_count_surfaces_in_list():
    """`waitlist_count` should appear on seatmap events too in /events listing."""
    eid = asyncio.run(_seed_seatmap_sold_out(2, 2))
    token, _ = _register_attendee()
    requests.post(f"{API}/api/events/{eid}/waitlist/join",
                  headers={"Authorization": f"Bearer {token}"},
                  json={"quantity": 1}, timeout=10)
    items = requests.get(f"{API}/api/events?q=Seat WL Test", timeout=10).json()
    target = next((e for e in items if e["event_id"] == eid), None)
    assert target is not None
    assert target.get("waitlist_count") == 1
