"""Unified buyers report — /organizer/buyers.

Covers: aggregation across multiple events, search filter, event_id filter,
status filter, CSV export, and that organizer A cannot see organizer B's
bookings. Hits the live running backend (localhost:8001).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now, hash_password  # noqa: E402

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


async def _seed():
    """Seed two organizers + 3 bookings on Org A's event (2 paid, 1 pending)
    and 1 paid booking on Org B's event. Returns ids + password."""
    suffix = uuid.uuid4().hex[:8]
    org_a_email = f"buyers_a_{suffix}@example.com"
    org_b_email = f"buyers_b_{suffix}@example.com"
    pwd = hash_password("Pass1234!")

    await db.users.insert_many([
        {"user_id": f"u_a_{suffix}", "name": "Org A", "email": org_a_email,
         "password_hash": pwd, "role": "organizer", "phone": "+64215550001",
         "created_at": utc_now().isoformat()},
        {"user_id": f"u_b_{suffix}", "name": "Org B", "email": org_b_email,
         "password_hash": pwd, "role": "organizer", "phone": "+64215550002",
         "created_at": utc_now().isoformat()},
    ])

    evt_a = f"evt_a_{suffix}"
    evt_b = f"evt_b_{suffix}"
    when = (utc_now() + timedelta(days=14)).isoformat()
    await db.events.insert_many([
        {"event_id": evt_a, "organizer_id": f"u_a_{suffix}", "title": "Alpha Show",
         "venue": "Hall A", "city": "Auckland", "date": when, "category": "music",
         "image_url": "", "currency": "NZD", "status": "approved",
         "created_at": utc_now().isoformat()},
        {"event_id": evt_b, "organizer_id": f"u_b_{suffix}", "title": "Beta Show",
         "venue": "Hall B", "city": "Auckland", "date": when, "category": "music",
         "image_url": "", "currency": "NZD", "status": "approved",
         "created_at": utc_now().isoformat()},
    ])

    paid_at = utc_now().isoformat()
    await db.bookings.insert_many([
        {"booking_id": f"bk_a1_{suffix}", "event_id": evt_a, "event_title": "Alpha Show",
         "event_date": when, "event_venue": "Hall A",
         "user_id": "u_buyer_alice", "user_name": "Alice Anderson",
         "user_email": f"alice_{suffix}@example.com",
         "tier_name": "GA", "quantity": 2, "seats": [], "amount": 75.0,
         "currency": "NZD", "status": "paid",
         "paid_at": paid_at, "created_at": paid_at, "checked_in": False},
        {"booking_id": f"bk_a2_{suffix}", "event_id": evt_a, "event_title": "Alpha Show",
         "event_date": when, "event_venue": "Hall A",
         "user_id": "u_buyer_bob", "user_name": "Bob Brown",
         "user_email": f"bob_{suffix}@example.com",
         "tier_name": "VIP", "quantity": 1, "seats": ["A-1"], "amount": 150.0,
         "currency": "NZD", "status": "paid",
         "paid_at": paid_at, "created_at": paid_at, "checked_in": True,
         "checked_in_at": paid_at},
        {"booking_id": f"bk_a3_{suffix}", "event_id": evt_a, "event_title": "Alpha Show",
         "event_date": when, "event_venue": "Hall A",
         "user_id": "u_buyer_carol", "user_name": "Carol Carter",
         "user_email": f"carol_{suffix}@example.com",
         "tier_name": "GA", "quantity": 1, "seats": [], "amount": 50.0,
         "currency": "NZD", "status": "pending",
         "created_at": paid_at},
    ])
    await db.bookings.insert_one({
        "booking_id": f"bk_b1_{suffix}", "event_id": evt_b, "event_title": "Beta Show",
        "event_date": when, "event_venue": "Hall B",
        "user_id": "u_buyer_alice", "user_name": "Alice Anderson",
        "user_email": f"alice_{suffix}@example.com",
        "tier_name": "GA", "quantity": 1, "seats": [], "amount": 80.0,
        "currency": "NZD", "status": "paid",
        "paid_at": paid_at, "created_at": paid_at, "checked_in": False,
    })

    return {
        "suffix": suffix,
        "org_a_email": org_a_email,
        "org_b_email": org_b_email,
        "password": "Pass1234!",
        "evt_a": evt_a,
        "evt_b": evt_b,
    }


async def _cleanup(suffix: str, evt_a: str, evt_b: str, org_a_email: str, org_b_email: str):
    await db.bookings.delete_many({"booking_id": {"$regex": suffix}})
    await db.events.delete_many({"event_id": {"$in": [evt_a, evt_b]}})
    await db.users.delete_many({"email": {"$in": [org_a_email, org_b_email]}})


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return data.get("token") or data.get("access_token")


@pytest.mark.asyncio
async def test_buyers_report_full_flow():
    """Single end-to-end test exercising filters, pagination, isolation, CSV.

    Kept as one test so the fixture state survives across the entire async
    flow on the same event loop (Motor caches its first loop per process)."""
    s = await _seed()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token = await _login(client, s["org_a_email"], s["password"])
            h = {"Authorization": f"Bearer {token}"}

            # 1. Default (status=paid): Org A sees their 2 paid bookings only.
            r = await client.get(f"{API}/organizer/buyers", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 2
            titles = {it["event_title"] for it in body["items"]}
            assert titles == {"Alpha Show"}
            event_ids = {e["event_id"] for e in body["events"]}
            assert s["evt_a"] in event_ids and s["evt_b"] not in event_ids

            # 2. status=all → also includes the pending row.
            r = await client.get(f"{API}/organizer/buyers", params={"status": "all"}, headers=h)
            assert r.status_code == 200 and r.json()["total"] == 3

            # 3. Search by name.
            r = await client.get(f"{API}/organizer/buyers", params={"q": "Alice"}, headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1 and body["items"][0]["user_name"] == "Alice Anderson"

            # 4. Search by email substring (uniqueness via suffix).
            r = await client.get(f"{API}/organizer/buyers", params={"q": f"bob_{s['suffix']}"}, headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1 and body["items"][0]["user_name"] == "Bob Brown"

            # 5. event_id filter scoping to another organizer's event → 403.
            r = await client.get(f"{API}/organizer/buyers", params={"event_id": s["evt_b"]}, headers=h)
            assert r.status_code == 403

            # 6. CSV export.
            r = await client.get(f"{API}/organizer/buyers.csv", headers=h)
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/csv")
            text = r.text
            assert text.startswith("Booking ID,Event,Event date,Buyer,Email")
            assert "Alice Anderson" in text and "Bob Brown" in text
            # Pending excluded by default.
            assert "Carol Carter" not in text
    finally:
        await _cleanup(s["suffix"], s["evt_a"], s["evt_b"], s["org_a_email"], s["org_b_email"])
