"""Tests for the buyer-pays-fees model (gross-up math + booking shape)."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402, F401
from fees import (  # noqa: E402
    compute_fees, PLATFORM_FEE_BPS, STRIPE_FEE_BPS, STRIPE_FEE_FLAT,
)


def test_compute_fees_known_math():
    """$20 ticket → buyer pays grossed-up total + organizer keeps face_value.

    Math is derived from the live PLATFORM_FEE_* / STRIPE_FEE_* constants so
    the test survives any admin-driven rate change.
    """
    from fees import PLATFORM_FEE_FLAT
    b = compute_fees(20.0, "NZD")
    assert round(b.face_value, 2) == 20.00

    # platform_fee = face_value * platform_pct + platform_flat (per-ticket)
    expected_platform = round(20.0 * (PLATFORM_FEE_BPS / 10000.0) + PLATFORM_FEE_FLAT, 2)
    assert round(b.platform_fee, 2) == expected_platform

    # buyer_total = (face + platform + stripe_flat) / (1 - stripe_pct)
    stripe_pct = STRIPE_FEE_BPS / 10000.0
    expected_buyer_total = round(
        (20.0 + expected_platform + STRIPE_FEE_FLAT) / (1 - stripe_pct), 2
    )
    assert round(b.buyer_total, 2) == expected_buyer_total
    assert round(b.service_fee, 2) == round(expected_buyer_total - 20.0, 2)

    # Verify the gross-up is exact: after Stripe's real cut, the platform
    # should retain exactly face_value + platform_fee.
    stripe_real = stripe_pct * b.buyer_total + STRIPE_FEE_FLAT
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


async def test_booking_stores_fee_breakdown():
    """End-to-end: creating a hold via the bookings router must populate
    `face_value`, `platform_fee`, `service_fee`, and bump `amount` to the
    grossed-up buyer total.

    Math is derived from the live admin platform_settings (the platform_pct
    and platform_flat are admin-configurable), not hard-coded against the
    fees.py constants — so this test survives admin rate changes.
    """
    import requests
    api = "http://localhost:8001"

    # Fetch the live admin-configured rates so the assertion uses whatever
    # the admin has set (compute_fees in bookings.py honors these).
    pub = requests.get(f"{api}/api/fees/public-settings", timeout=10).json()
    live_pct = float(pub["platform_pct"]) / 100.0
    live_flat = float(pub["platform_flat_per_ticket"])

    email = f"feestest_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "test1234"
    requests.post(f"{api}/api/auth/register", json={
        "name": "Fees Test", "email": email, "password": pwd, "role": "attendee",
        "phone": "+64 21 555 1234",  # mandatory since Feb 2026
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
        # Use the LIVE admin rate (not the env-var default) since
        # platform_settings overrides the env defaults at booking time.
        expected_platform = round(expected_face * live_pct + live_flat, 2)
        assert b.get("platform_fee") == expected_platform, (
            f"platform_fee={b.get('platform_fee')} vs expected {expected_platform} "
            f"(live_pct={live_pct*100}% + flat=${live_flat})"
        )
        assert b.get("service_fee") > 0
        assert b.get("amount") > b.get("face_value"), "amount must be grossed-up"
        # Verify the engine's expected total roughly matches what the fee
        # helper would have computed independently (compute_fees uses the
        # same admin rates via bookings.py — pass them explicitly here).
        independent = compute_fees(
            expected_face, b.get("currency", "NZD"),
            platform_pct=float(pub["platform_pct"]),
            platform_flat=live_flat,
            stripe_flat=float(pub["stripe_flat_per_ticket"]),
        )
        assert abs(b["amount"] - round(independent.buyer_total, 2)) < 0.05
    finally:
        await db.bookings.delete_one({"booking_id": booking_id})
        await db.seat_holds.delete_many({"booking_id": booking_id})
        await db.users.delete_many({"email": email})
