"""Privacy guarantee — organizers must never see buyer-paid totals.

The `amount` field on every organizer-facing endpoint must equal the booking's
`face_value` (the organizer's gross revenue base), NOT the buyer-paid total
(which bakes in platform + Stripe fees). This test plants a booking with a
clear gap between the two so any regression that switches the field back to
buyer-paid will surface immediately.
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


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("token") or body.get("access_token")


@pytest.mark.asyncio
async def test_organizer_never_sees_buyer_paid_amount():
    suffix = uuid.uuid4().hex[:8]
    org_email = f"privtest_{suffix}@example.com"
    pwd = hash_password("Pass1234!")
    org_uid = f"u_p_{suffix}"
    evt = f"evt_p_{suffix}"
    when = (utc_now() + timedelta(days=14)).isoformat()
    paid_at = utc_now().isoformat()

    # face_value = $50 (organizer's ticket price)
    # platform_fee + stripe_fee = $1.95 (the gap)
    # amount = $51.95 (buyer-paid total)  ← MUST NEVER appear in organizer views
    FACE_VALUE = 50.0
    BUYER_PAID = 51.95
    PLATFORM_FEE = 1.50
    STRIPE_FEE = 0.45

    await db.users.insert_one({
        "user_id": org_uid, "name": "Privacy Org", "email": org_email,
        "password_hash": pwd, "role": "organizer", "phone": "+64215550100",
        "created_at": utc_now().isoformat(),
    })
    await db.events.insert_one({
        "event_id": evt, "organizer_id": org_uid, "title": "Privacy Show",
        "venue": "Hall P", "city": "Auckland", "date": when, "category": "music",
        "image_url": "", "currency": "NZD", "status": "approved",
        "created_at": utc_now().isoformat(),
        "tiers": [{"name": "GA", "price": 50, "capacity": 100}],
    })
    await db.bookings.insert_one({
        "booking_id": f"bk_p_{suffix}", "event_id": evt, "event_title": "Privacy Show",
        "event_date": when, "event_venue": "Hall P",
        "user_id": "u_buyer_priv", "user_name": "Alex Buyer",
        "user_email": f"alex_{suffix}@example.com",
        "tier_name": "GA", "quantity": 1, "seats": [],
        "face_value": FACE_VALUE,
        "platform_fee": PLATFORM_FEE,
        "stripe_fee_estimated": STRIPE_FEE,
        "service_fee": PLATFORM_FEE + STRIPE_FEE,
        "amount": BUYER_PAID,  # ← what the buyer was charged, MUST stay hidden
        "currency": "NZD", "status": "paid",
        "paid_at": paid_at, "created_at": paid_at, "checked_in": False,
    })

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await _login(client, org_email, "Pass1234!")
            h = {"Authorization": f"Bearer {tok}"}

            # 1. /organizer/buyers — amount must equal face_value, not buyer-paid.
            r = await client.get(f"{API}/organizer/buyers", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 1
            item = body["items"][0]
            assert item["amount"] == FACE_VALUE, (
                f"organizer/buyers leaked buyer-paid total: {item['amount']} ≠ {FACE_VALUE}"
            )
            # And the fee fields must not be present on the response.
            assert "platform_fee" not in item
            assert "stripe_fee_estimated" not in item
            assert "service_fee" not in item

            # 2. /organizer/events/{id}/attendees — same guarantee.
            r = await client.get(f"{API}/organizer/events/{evt}/attendees", headers=h)
            assert r.status_code == 200
            atts = r.json()
            assert len(atts) == 1
            assert atts[0]["amount"] == FACE_VALUE, (
                f"organizer/attendees leaked buyer-paid total: {atts[0]['amount']}"
            )
            # Fee fields stripped from the booking before returning.
            assert "platform_fee" not in atts[0]
            assert "stripe_fee_estimated" not in atts[0]
            assert "service_fee" not in atts[0]

            # 3. /organizer/analytics — total_revenue must use face_value.
            r = await client.get(f"{API}/organizer/analytics", headers=h)
            assert r.status_code == 200
            analytics = r.json()
            assert analytics["total_revenue"] == FACE_VALUE
            per_event = next((p for p in analytics["per_event"] if p["event_id"] == evt), None)
            assert per_event is not None
            assert per_event["revenue"] == FACE_VALUE

            # 4. /organizer/events/{id}/analytics — totals.revenue & tiers & days.
            r = await client.get(f"{API}/organizer/events/{evt}/analytics", headers=h)
            assert r.status_code == 200
            drill = r.json()
            assert drill["totals"]["revenue"] == FACE_VALUE
            assert any(t["revenue"] == FACE_VALUE for t in drill["tiers"])

            # 5. CSV exports — buyer-paid amount must not appear anywhere.
            r = await client.get(f"{API}/organizer/buyers.csv", headers=h)
            assert r.status_code == 200
            csv_text = r.text
            assert f"{FACE_VALUE:.2f}" in csv_text
            assert f"{BUYER_PAID:.2f}" not in csv_text, (
                "buyers.csv leaked buyer-paid amount"
            )
            assert "Revenue" in csv_text.splitlines()[0]  # header renamed

            r = await client.get(f"{API}/organizer/events/{evt}/attendees.csv", headers=h)
            assert r.status_code == 200
            csv_text = r.text
            assert f"{FACE_VALUE:.2f}" in csv_text
            assert f"{BUYER_PAID:.2f}" not in csv_text, (
                "attendees.csv leaked buyer-paid amount"
            )
    finally:
        await db.bookings.delete_one({"booking_id": f"bk_p_{suffix}"})
        await db.events.delete_one({"event_id": evt})
        await db.users.delete_one({"email": org_email})
