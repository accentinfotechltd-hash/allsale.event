"""Stripe Connect gate on event publish.

Rule: an organizer cannot publish a PAID event (any tier with price > 0)
without a working Stripe Connect payout account (`stripe_payouts_enabled`).
Free events skip the gate. Admins are exempt.

Server emits a 402 with a structured detail and fires a one-shot reminder
email containing the 1-click onboarding URL.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

API_URL = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


def _register(email: str | None = None, **extra) -> dict:
    email = email or f"orgconnect_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email, "password": "testpass123",
            "name": "Connect Test", "phone": "+64 21 555 4321",
            "role": "organizer",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _event_payload(*, paid: bool, **extra) -> dict:
    base = {
        "title": "Test Event",
        "description": "test",
        "category": "music",
        "venue": "Test Venue", "city": "Auckland",
        "country": "NZ", "timezone": "Pacific/Auckland",
        "date": "2027-01-15T19:00:00Z",
        "image_url": "https://example.com/cover.jpg",
        "currency": "NZD",
        "tiers": [{"name": "General", "price": 25.0 if paid else 0.0, "capacity": 100}],
        "has_seatmap": False,
        # refund_policy is a dict on EventIn — omit to use the default rather
        # than passing a string (caused 422s during regression authoring).
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 1. Paid event without Stripe → 402
# ---------------------------------------------------------------------------
def test_paid_event_blocked_without_stripe_connect():
    """Organizer with NO stripe_payouts_enabled → 402 on paid publish."""
    org = _register()
    token = org["token"]
    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=True),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 402, f"expected 402, got {r.status_code} body={r.text[:300]}"
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "stripe_payouts_required"
    assert "stripe" in detail["message"].lower()
    assert detail["onboarding_path"] == "/organizer"


# ---------------------------------------------------------------------------
# 2. FREE event without Stripe → allowed (200)
# ---------------------------------------------------------------------------
def test_free_event_allowed_without_stripe_connect():
    """All-zero tiers → no Stripe required."""
    org = _register()
    token = org["token"]
    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=False, title="Free meetup"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, f"free event should publish: {r.text[:300]}"
    assert r.json()["event_id"].startswith("evt_")


# ---------------------------------------------------------------------------
# 3. Paid event WITH Stripe enabled → allowed (200)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paid_event_allowed_when_stripe_payouts_enabled():
    """Manually flip stripe_payouts_enabled in DB → publish succeeds."""
    import asyncio  # noqa: F401
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    org = _register()
    token = org["token"]

    # Simulate completed Stripe Connect onboarding
    await db.users.update_one(
        {"user_id": org["user_id"]},
        {"$set": {
            "stripe_account_id": f"acct_test_{uuid.uuid4().hex[:8]}",
            "stripe_charges_enabled": True,
            "stripe_payouts_enabled": True,
            "stripe_details_submitted": True,
        }},
    )

    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=True, title="Paid with Stripe"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, f"paid + stripe should publish: {r.text[:300]}"
    assert r.json()["event_id"].startswith("evt_")


# ---------------------------------------------------------------------------
# 4. Admin can publish a paid event without their own Stripe
# ---------------------------------------------------------------------------
def test_admin_can_publish_paid_event_without_stripe():
    """Admin override — they often publish on behalf of organizers who are
    still onboarding."""
    admin = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    ).json()
    token = admin["token"]
    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=True, title=f"Admin paid event {uuid.uuid4().hex[:4]}"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, f"admin should bypass Stripe gate: {r.text[:300]}"


# ---------------------------------------------------------------------------
# 5. The 402 fires the reminder email (template registry verified)
# ---------------------------------------------------------------------------
def test_organizer_stripe_required_template_exists_in_registry():
    """The reminder template MUST exist so the 402 email actually sends.

    Failure mode prevented: typo in TEMPLATES dict → 402 fires but email
    silently fails, organizer never gets the onboarding link.
    """
    from emails import TEMPLATES
    assert "organizer_stripe_required" in TEMPLATES, (
        "organizer_stripe_required template missing — 402 fires but no email"
    )
    # Render it once to catch a malformed template body.
    subject, html, text = TEMPLATES["organizer_stripe_required"]({
        "organizer_name": "Alex",
        "event_title": "Lunar Festival",
        "onboarding_url": "https://www.allsale.events/organizer?stripe_return=1",
    })
    assert "Lunar Festival" in subject
    assert "Connect Stripe" in html
    assert "stripe_return=1" in html
    assert "Lunar Festival" in text


# ---------------------------------------------------------------------------
# 6. Edit endpoint also gates — flipping a free event to paid without Stripe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_blocks_flipping_free_event_to_paid_without_stripe():
    """PATCH /events/{id} must enforce the same gate as POST /events."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    org = _register()
    token = org["token"]

    # 1) Publish a free event (no Stripe needed)
    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=False, title="Free draft"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200
    event_id = r.json()["event_id"]

    # 2) Try to flip a tier to paid without Stripe → must 402
    patch_r = requests.patch(
        f"{API_URL}/api/events/{event_id}",
        json={"tiers": [{"name": "General", "price": 40.0, "capacity": 100}]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert patch_r.status_code == 402, f"flip-to-paid should block: {patch_r.text[:300]}"
    detail = patch_r.json()["detail"]
    assert detail["code"] == "stripe_payouts_required"

    # 3) Now flip with Stripe enabled → succeeds
    await db.users.update_one(
        {"user_id": org["user_id"]},
        {"$set": {
            "stripe_account_id": f"acct_test_{uuid.uuid4().hex[:8]}",
            "stripe_payouts_enabled": True,
            "stripe_charges_enabled": True,
        }},
    )
    patch_r = requests.patch(
        f"{API_URL}/api/events/{event_id}",
        json={"tiers": [{"name": "General", "price": 40.0, "capacity": 100}]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert patch_r.status_code == 200, f"flip-to-paid with stripe should pass: {patch_r.text[:300]}"
