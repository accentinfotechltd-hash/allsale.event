"""Stripe Connect — OPTIONAL (Feb 2026 policy change).

Manual bank transfers are the platform default; Stripe Connect is an
opt-in upgrade that gives organizers automatic payouts. There is NO hard
gate blocking event publish based on Stripe status — a soft reminder
email fires instead.

These tests replaced the old `test_stripe_connect_publish_gate.py` when
we removed the 402 gate. If a future policy re-introduces the gate,
resurrect the old contract here.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

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
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 1. Paid event without Stripe → NOW ALLOWED (was 402 pre-Feb-2026)
# ---------------------------------------------------------------------------
def test_paid_event_publishes_without_stripe_connect():
    """Organizer with NO stripe_payouts_enabled: paid publish must succeed.

    The reminder email still fires as a soft nudge (see next test), but
    the event goes live via the normal moderation queue.
    """
    org = _register()
    token = org["token"]
    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=True),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code} body={r.text[:300]}"
    assert r.json()["event_id"].startswith("evt_")


# ---------------------------------------------------------------------------
# 2. FREE event without Stripe → allowed (unchanged)
# ---------------------------------------------------------------------------
def test_free_event_allowed_without_stripe_connect():
    """All-zero tiers → publish succeeds (unchanged behaviour)."""
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
# 3. Paid event WITH Stripe enabled → allowed (unchanged)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paid_event_allowed_when_stripe_payouts_enabled():
    """Sanity: connecting Stripe doesn't break anything either."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    org = _register()
    token = org["token"]

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


# ---------------------------------------------------------------------------
# 4. Admin also publishes cleanly
# ---------------------------------------------------------------------------
def test_admin_can_publish_paid_event_without_stripe():
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
    assert r.status_code == 200, f"admin publish: {r.text[:300]}"


# ---------------------------------------------------------------------------
# 5. Reminder-email template still exists (soft nudge)
# ---------------------------------------------------------------------------
def test_organizer_stripe_required_template_exists_in_registry():
    """The reminder template still exists — it fires as a soft nudge on
    paid publish without Stripe. Failure mode prevented: typo in TEMPLATES
    dict → organizer never gets the onboarding link.
    """
    from emails import TEMPLATES
    assert "organizer_stripe_required" in TEMPLATES, (
        "organizer_stripe_required template missing — nudge email won't send"
    )
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
# 6. Edit endpoint also no longer gates
# ---------------------------------------------------------------------------
def test_edit_allows_flipping_free_event_to_paid_without_stripe():
    """PATCH must ALSO no longer 402 on the free → paid flip."""
    org = _register()
    token = org["token"]

    r = requests.post(
        f"{API_URL}/api/events",
        json=_event_payload(paid=False, title="Free that goes paid"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code == 200
    event_id = r.json()["event_id"]

    patch_r = requests.patch(
        f"{API_URL}/api/events/{event_id}",
        json={"tiers": [{"name": "General", "price": 40.0, "capacity": 100}]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert patch_r.status_code == 200, f"flip-to-paid must succeed without Stripe: {patch_r.text[:300]}"
