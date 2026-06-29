"""Admin Stripe Connect Status Tab — endpoint tests.

Validates GET /api/admin/stripe-connect-status + POST /api/admin/stripe-connect-status/remind.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def attendee_token():
    """Non-admin user used to verify auth gating."""
    email = f"attendee_admin_gate_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        f"{API}/api/auth/register",
        json={"name": "Gate Test", "email": email, "password": "test1234", "role": "attendee", "phone": "+64 21 555 9999"},
        timeout=10,
    )
    assert r.status_code in (200, 201), f"register failed: {r.text}"
    return r.json()["token"]


def test_status_endpoint_returns_correct_shape(admin_token):
    r = requests.get(
        f"{API}/api/admin/stripe-connect-status",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert "summary" in body
    s = body["summary"]
    assert set(s.keys()) >= {"total", "connected", "onboarding", "not_connected"}
    # Counts must reconcile.
    assert s["connected"] + s["onboarding"] + s["not_connected"] == s["total"]
    assert isinstance(body["items"], list)
    if body["items"]:
        row = body["items"][0]
        assert {"user_id", "email", "name", "status", "events_count", "bookings_count",
                "lifetime_revenue", "platform_fees_collected", "currency"} <= set(row.keys())
        assert row["status"] in {"connected", "onboarding_incomplete", "not_connected"}


def test_status_sorted_by_revenue_desc(admin_token):
    r = requests.get(
        f"{API}/api/admin/stripe-connect-status",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    items = r.json()["items"]
    if len(items) > 1:
        # First row should have >= revenue than the last row.
        assert items[0]["lifetime_revenue"] >= items[-1]["lifetime_revenue"], \
            "Items must be sorted by lifetime_revenue DESC"


def test_status_blocks_non_admin(attendee_token):
    r = requests.get(
        f"{API}/api/admin/stripe-connect-status",
        headers={"Authorization": f"Bearer {attendee_token}"},
        timeout=10,
    )
    assert r.status_code == 403, r.text


def test_remind_blocks_non_admin(attendee_token):
    r = requests.post(
        f"{API}/api/admin/stripe-connect-status/remind",
        headers={"Authorization": f"Bearer {attendee_token}"},
        json={"user_ids": ["anyone"]},
        timeout=10,
    )
    assert r.status_code == 403, r.text


def test_remind_empty_target_returns_zero(admin_token):
    """Passing an unknown user_id should return sent=0 (no exception)."""
    r = requests.post(
        f"{API}/api/admin/stripe-connect-status/remind",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_ids": ["user_nonexistent_xxxx"]},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] == 0
    assert isinstance(body["errors"], list)
