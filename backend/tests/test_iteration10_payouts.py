"""Iteration 10 — Commission & payouts.

Covers:
- Commission helper math (percent + flat fee).
- GET/PUT /api/admin/platform-settings (admin auth, validation).
- GET /api/organizer/payouts/balance — eligible bookings, lifetime, pending.
- POST /api/organizer/payouts/request — creates payout, locks bookings.
- GET /api/organizer/payouts — only own payouts.
- GET /api/admin/payouts — all, with totals + status filter.
- POST /api/admin/payouts/{id}/mark-paid — status transition + email log.
- POST /api/admin/payouts/{id}/reject — rolls back bookings to eligible.
- AuthZ: attendee 403, non-admin 403 on admin routes.
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

from routers.payouts import _compute_commission  # noqa: E402

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


# Cleanup test users + payouts created during this module so they don't
# pile up in the seeded DB.
@pytest.fixture(scope="module", autouse=True)
def _cleanup_after_module():
    yield
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_test_"}},
            {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.bookings.delete_many({"event_id": {"$in": ids}})
            await db.payouts.delete_many({"organizer_id": {"$regex": "^user_"}, "event_id": {"$in": ids}})
        user_ids = [u["user_id"] async for u in db.users.find(
            {"email": {"$regex": "^org_[^@]+@example.com"}},
            {"_id": 0, "user_id": 1},
        )]
        if user_ids:
            await db.users.delete_many({"user_id": {"$in": user_ids}})
            await db.payouts.delete_many({"organizer_id": {"$in": user_ids}})
        client.close()
    try: asyncio.run(_clean())
    except Exception: pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def login(email: str, password: str) -> tuple[str, dict]:
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    body = r.json()
    return body["token"], body


def admin_token() -> str:
    t, _ = login("admin@aura.events", "admin123")
    return t


def attendee_token() -> str:
    t, _ = login("attendee@aura.events", "attendee123")
    return t


async def _seed_organizer_with_paid_bookings(num_bookings: int = 3) -> tuple[str, str]:
    """Insert an isolated organizer + event + paid bookings.
    Returns (organizer_user_id, organizer_password) — bcrypt-hashed password unknown,
    so we'll use the returned token logic differently. We register via API instead.
    """
    suffix = uuid.uuid4().hex[:8]
    email = f"org_{suffix}@example.com"
    password = "TestPass123!"
    r = requests.post(f"{API}/api/auth/register", json={
        "email": email, "password": password, "name": f"Org {suffix}", "role": "organizer",
    }, timeout=10)
    r.raise_for_status()
    token = r.json()["token"]
    user_id = r.json()["user_id"]

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    event_id = f"evt_test_{suffix}"
    await db.events.insert_one({
        "event_id": event_id, "title": f"Test Event {suffix}",
        "organizer_id": user_id, "category": "Music", "city": "Test City",
        "venue": "Test Venue", "date": "2026-12-31T20:00:00+00:00",
        "image_url": "", "status": "approved", "featured": False,
        "tiers": [{"name": "GA", "price": 50.0, "capacity": 100, "sold": 0}],
        "has_seatmap": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    booking_ids = []
    for i in range(num_bookings):
        bid = f"bkg_test_{suffix}_{i}"
        booking_ids.append(bid)
        await db.bookings.insert_one({
            "booking_id": bid, "event_id": event_id,
            "event_title": f"Test Event {suffix}",
            "event_date": "2026-12-31T20:00:00+00:00",
            "user_id": "user_buyer", "user_email": "buyer@test.com",
            "user_name": "Test Buyer",
            "tier_name": "GA", "quantity": 1, "seats": [],
            "amount": 100.0, "subtotal": 100.0,
            "currency": "usd", "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    client.close()
    return token, user_id, event_id, booking_ids


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------
def test_commission_math_basic():
    comm, flat, net = _compute_commission(gross=1000.0, tickets=50, percent=8.0, flat_per_ticket=0.5)
    assert comm == 80.0
    assert flat == 25.0
    assert net == 895.0


def test_commission_math_zero_tickets():
    comm, flat, net = _compute_commission(0.0, 0, 8.0, 0.5)
    assert comm == 0 and flat == 0 and net == 0


def test_commission_math_high_fees_clamped_to_zero():
    # Fees larger than gross should not produce negative net
    comm, flat, net = _compute_commission(gross=10.0, tickets=100, percent=8.0, flat_per_ticket=0.5)
    assert net >= 0


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------
def test_get_settings_attendee_403():
    r = requests.get(f"{API}/api/admin/platform-settings",
                     headers={"Authorization": f"Bearer {attendee_token()}"}, timeout=10)
    assert r.status_code == 403


def test_get_settings_admin_ok():
    r = requests.get(f"{API}/api/admin/platform-settings",
                     headers={"Authorization": f"Bearer {admin_token()}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "commission_percent" in body
    assert "commission_flat_fee_per_ticket" in body


def test_update_settings_validates_bounds():
    r = requests.put(f"{API}/api/admin/platform-settings",
                     headers={"Authorization": f"Bearer {admin_token()}"},
                     json={"commission_percent": 80, "commission_flat_fee_per_ticket": 0.5}, timeout=10)
    assert r.status_code in (400, 422)  # over 50% rejected


def test_update_settings_persists():
    t = admin_token()
    r = requests.put(f"{API}/api/admin/platform-settings",
                     headers={"Authorization": f"Bearer {t}"},
                     json={"commission_percent": 10.0, "commission_flat_fee_per_ticket": 0.75}, timeout=10)
    assert r.status_code == 200
    assert r.json()["commission_percent"] == 10.0
    # Restore default
    requests.put(f"{API}/api/admin/platform-settings",
                 headers={"Authorization": f"Bearer {t}"},
                 json={"commission_percent": 8.0, "commission_flat_fee_per_ticket": 0.5}, timeout=10)


# ---------------------------------------------------------------------------
# Payout E2E flow
# ---------------------------------------------------------------------------
def test_balance_request_paid_flow():
    token, org_user_id, event_id, booking_ids = asyncio.run(_seed_organizer_with_paid_bookings(3))

    # 1. Balance reflects 3 bookings × $100 = $300 gross
    r = requests.get(f"{API}/api/organizer/payouts/balance",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    b = r.json()
    assert b["available"]["gross"] == 300.0
    assert b["available"]["bookings"] == 3
    assert b["available"]["tickets"] == 3
    assert b["available"]["net"] == 300.0 - 24.0 - 1.5  # 8% + $0.50/ticket
    assert b["lifetime_paid"] == 0.0
    assert b["pending"] == 0.0

    # 2. Request payout
    r = requests.post(f"{API}/api/organizer/payouts/request",
                      headers={"Authorization": f"Bearer {token}"}, json={"notes": "test"}, timeout=10)
    assert r.status_code == 200
    payout = r.json()
    pid = payout["payout_id"]
    assert payout["status"] == "requested"
    assert payout["bookings_count"] == 3
    assert payout["net_amount"] == 300.0 - 24.0 - 1.5

    # 3. Balance now zero, pending = the payout
    r = requests.get(f"{API}/api/organizer/payouts/balance",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    b = r.json()
    assert b["available"]["gross"] == 0
    assert b["pending"] == payout["net_amount"]

    # 4. Second request fails (no eligible bookings)
    r = requests.post(f"{API}/api/organizer/payouts/request",
                      headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    assert r.status_code == 400

    # 5. Admin marks paid
    r = requests.post(f"{API}/api/admin/payouts/{pid}/mark-paid",
                      headers={"Authorization": f"Bearer {admin_token()}"},
                      json={"reference": "TEST_WIRE_001"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "paid"

    # 6. Cannot mark same payout paid twice
    r = requests.post(f"{API}/api/admin/payouts/{pid}/mark-paid",
                      headers={"Authorization": f"Bearer {admin_token()}"},
                      json={}, timeout=10)
    assert r.status_code == 400

    # 7. Balance now: lifetime_paid populated
    r = requests.get(f"{API}/api/organizer/payouts/balance",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    b = r.json()
    assert b["lifetime_paid"] == payout["net_amount"]
    assert b["lifetime_paid_count"] == 1
    assert b["pending"] == 0


def test_reject_rolls_back_bookings():
    token, _, _, _ = asyncio.run(_seed_organizer_with_paid_bookings(2))
    # Request
    r = requests.post(f"{API}/api/organizer/payouts/request",
                      headers={"Authorization": f"Bearer {token}"}, json={}, timeout=10)
    pid = r.json()["payout_id"]
    # Reject
    r = requests.post(f"{API}/api/admin/payouts/{pid}/reject",
                      headers={"Authorization": f"Bearer {admin_token()}"},
                      json={"reason": "duplicate request"}, timeout=10)
    assert r.status_code == 200
    # Balance should be restored
    r = requests.get(f"{API}/api/organizer/payouts/balance",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.json()["available"]["bookings"] == 2


def test_organizer_payouts_lists_only_own():
    token_a, _, _, _ = asyncio.run(_seed_organizer_with_paid_bookings(1))
    token_b, _, _, _ = asyncio.run(_seed_organizer_with_paid_bookings(1))
    # Each requests a payout
    requests.post(f"{API}/api/organizer/payouts/request",
                  headers={"Authorization": f"Bearer {token_a}"}, json={}, timeout=10)
    requests.post(f"{API}/api/organizer/payouts/request",
                  headers={"Authorization": f"Bearer {token_b}"}, json={}, timeout=10)
    # B should see only their own
    r = requests.get(f"{API}/api/organizer/payouts",
                     headers={"Authorization": f"Bearer {token_b}"}, timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["bookings_count"] == 1


def test_admin_payouts_authz():
    # Attendee blocked
    r = requests.get(f"{API}/api/admin/payouts",
                     headers={"Authorization": f"Bearer {attendee_token()}"}, timeout=10)
    assert r.status_code == 403


def test_admin_payouts_status_filter():
    r = requests.get(f"{API}/api/admin/payouts?status=paid",
                     headers={"Authorization": f"Bearer {admin_token()}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "totals" in body
    for item in body["items"]:
        assert item["status"] == "paid"


def test_organizer_balance_requires_organizer_role():
    r = requests.get(f"{API}/api/organizer/payouts/balance",
                     headers={"Authorization": f"Bearer {attendee_token()}"}, timeout=10)
    assert r.status_code == 403
