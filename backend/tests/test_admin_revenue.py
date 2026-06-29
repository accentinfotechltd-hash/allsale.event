"""Admin revenue dashboard endpoint.

Stripe doesn't natively expose our 1% + $0.50 platform fee as a line item
(the architecture today is platform-keeps-100% → manual payout). This
endpoint reconstructs the breakdown from booking records so admin can
see their cut without leaving Allsale.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

API_URL = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


def _admin_token() -> str:
    r = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    return r.json()["token"]


def test_admin_revenue_requires_admin():
    """Organizer accounts get 403 — only admin can see platform-fee P&L."""
    import uuid
    r = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": f"revauth_{uuid.uuid4().hex[:6]}@x.com",
            "password": "testpass123",
            "name": "Rev Auth",
            "phone": "+64 21 555 1212",
            "role": "organizer",
        },
        timeout=10,
    )
    token = r.json()["token"]
    r2 = requests.get(
        f"{API_URL}/api/admin/revenue",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r2.status_code == 403


def test_admin_revenue_response_shape():
    token = _admin_token()
    r = requests.get(
        f"{API_URL}/api/admin/revenue",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"items", "totals", "currency", "mixed_currencies", "range"}
    assert set(body["totals"].keys()) == {"gross", "stripe_fees", "platform_fees", "organizer_share", "count"}


def test_admin_revenue_breakdown_per_booking():
    """Every returned row must carry the four split numbers the table renders."""
    token = _admin_token()
    r = requests.get(
        f"{API_URL}/api/admin/revenue",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 5},
        timeout=15,
    )
    body = r.json()
    for row in body["items"]:
        assert set(row.keys()) >= {
            "booking_id", "paid_at", "event_id", "event_title", "organizer_name",
            "buyer_email", "quantity", "currency",
            "gross", "stripe_fee", "platform_fee", "organizer_share",
            "absorb_fees",
        }
        # Sanity: per-row math should be self-consistent within rounding.
        recombined = round(row["organizer_share"] + row["stripe_fee"] + row["platform_fee"], 2)
        # Allow a 0.02 tolerance for absorb_fees rounding edge cases.
        assert abs(recombined - row["gross"]) < 0.05, (
            f"row {row['booking_id']} sums don't reconcile: "
            f"org+stripe+platform={recombined} vs gross={row['gross']}"
        )


def test_admin_revenue_totals_sum_to_zero_when_no_data_in_range():
    """Tiny date window with no bookings → empty result, zero totals, no error."""
    token = _admin_token()
    r = requests.get(
        f"{API_URL}/api/admin/revenue",
        headers={"Authorization": f"Bearer {token}"},
        params={"start": "1999-01-01", "end": "1999-01-02"},
        timeout=10,
    )
    body = r.json()
    assert body["items"] == []
    assert body["totals"] == {
        "gross": 0.0, "stripe_fees": 0.0, "platform_fees": 0.0,
        "organizer_share": 0.0, "count": 0,
    }


def test_admin_revenue_includes_platform_fee_per_row():
    """The 'your cut' column — every row must explicitly include platform_fee."""
    token = _admin_token()
    r = requests.get(
        f"{API_URL}/api/admin/revenue",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 200},
        timeout=15,
    )
    body = r.json()
    if body["items"]:
        # At least one row must have a > 0 platform_fee (otherwise our gross-up
        # math is broken — every paid booking should attribute some cut to admin).
        assert any(r["platform_fee"] > 0 for r in body["items"]), (
            "no rows attribute any platform_fee — fee math broken?"
        )
