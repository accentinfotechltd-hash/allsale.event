"""Tests for the buyer-pays-fees model (gross-up math + booking shape)."""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from fees import (  # noqa: E402
    compute_fees, PLATFORM_FEE_BPS, STRIPE_FEE_BPS, STRIPE_FEE_FLAT,
)


def test_compute_fees_known_math():
    """$20 ticket → buyer pays $21.89 (rounded), organizer keeps $20."""
    b = compute_fees(20.0, "NZD")
    assert round(b.face_value, 2) == 20.00
    assert round(b.platform_fee, 2) == 1.00
    assert round(b.buyer_total, 2) == 21.89
    assert round(b.service_fee, 2) == 1.89
    # Verify the gross-up is exact: after Stripe's real cut, the platform
    # should retain exactly face_value + platform_fee.
    stripe_real = (STRIPE_FEE_BPS / 10000.0) * b.buyer_total + STRIPE_FEE_FLAT
    remainder = b.buyer_total - stripe_real
    assert abs(remainder - (b.face_value + b.platform_fee)) < 0.01


def test_compute_fees_zero_face_is_free():
    """Comp tickets ($0 face) generate no fees — never charge Stripe for $0."""
    b = compute_fees(0.0, "NZD")
    assert b.face_value == 0
    assert b.platform_fee == 0
    assert b.stripe_fee == 0
    assert b.service_fee == 0
    assert b.buyer_total == 0


def test_compute_fees_serialises_to_dict():
    """Make sure `.as_dict()` includes the bps so the frontend can render
    the chosen fee config if it ever needs to."""
    d = compute_fees(50.0, "NZD").as_dict()
    assert d["face_value"] == 50.0
    assert d["platform_fee_bps"] == PLATFORM_FEE_BPS
    assert d["stripe_fee_bps"] == STRIPE_FEE_BPS
    assert d["stripe_fee_flat"] == STRIPE_FEE_FLAT


def test_booking_stores_fee_breakdown():
    """End-to-end: creating a hold via the bookings router must populate
    `face_value`, `platform_fee`, `service_fee`, and bump `amount` to the
    grossed-up buyer total."""
    import requests
    api = "http://localhost:8001"

    email = f"feestest_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "test1234"
    requests.post(f"{api}/api/auth/register", json={
        "name": "Fees Test", "email": email, "password": pwd, "role": "attendee",
    }, timeout=10)
    tok = requests.post(f"{api}/api/auth/login", json={"email": email, "password": pwd}, timeout=10).json()["token"]

    # Pull any approved event with a non-seatmap tier.
    events = requests.get(f"{api}/api/events?limit=5", timeout=10).json()
    event = next((e for e in events if e.get("tiers")), None)
    if event is None:
        # No event available in this test env — skip rather than fail.
        return

    tier_name = event["tiers"][0]["name"]
    expected_face = event["tiers"][0]["price"] * 1  # quantity 1

    hold_resp = requests.post(
        f"{api}/api/bookings/hold",
        headers={"Authorization": f"Bearer {tok}"},
        json={"event_id": event["event_id"], "tier_name": tier_name, "quantity": 1},
        timeout=10,
    )
    assert hold_resp.status_code == 200, hold_resp.text
    b = hold_resp.json()
    booking_id = b["booking_id"]

    try:
        assert b.get("face_value") == round(expected_face, 2)
        assert b.get("platform_fee") == round(expected_face * (PLATFORM_FEE_BPS / 10000.0), 2)
        assert b.get("service_fee") > 0
        assert b.get("amount") > b.get("face_value"), "amount must be grossed-up"
        # Verify the engine's expected total roughly matches what the fee
        # helper would have computed independently.
        independent = compute_fees(expected_face, b.get("currency", "NZD"))
        assert abs(b["amount"] - round(independent.buyer_total, 2)) < 0.05
    finally:
        async def _clean():
            await db.bookings.delete_one({"booking_id": booking_id})
            await db.seat_holds.delete_many({"booking_id": booking_id})
            await db.users.delete_many({"email": email})
        asyncio.run(_clean())
