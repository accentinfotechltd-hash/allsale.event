"""Iteration 15 — Attendee → Organizer self-serve upgrade.

Covers:
- POST /api/auth/become-organizer requires auth.
- Attendee upgrades successfully → role flips to organizer.
- Endpoint is idempotent — calling on an organizer/admin keeps role unchanged
  and returns `upgraded=False`.
- After upgrade, attendee can hit organizer-only endpoints (e.g., POST /events).
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest_asyncio
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db  # noqa: E402

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _cleanup_module():
    yield
    try:
        await db.users.delete_many({"email": {"$regex": "^upgr15_[^@]+@example.com"}})
    except Exception:
        pass


def _register(role: str = "attendee") -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    r = requests.post(f"{API}/api/auth/register", json={
        "email": f"upgr15_{suffix}@example.com", "password": "TestPass123!",
        "name": f"Upgr15 {suffix}", "role": role,
        "phone": "+64 21 555 0099",  # mandatory since Feb 2026
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"], r.json()["user_id"]


def test_become_organizer_requires_auth():
    r = requests.post(f"{API}/api/auth/become-organizer", timeout=10)
    assert r.status_code == 401


def test_attendee_upgrade_flips_role():
    token, _ = _register("attendee")
    me = requests.get(f"{API}/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    assert me["role"] == "attendee"

    r = requests.post(f"{API}/api/auth/become-organizer",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "organizer"
    assert body["upgraded"] is True
    assert "upgraded_at" in body

    me2 = requests.get(f"{API}/api/auth/me",
                       headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    assert me2["role"] == "organizer"


def test_organizer_upgrade_is_idempotent():
    token, _ = _register("organizer")
    r = requests.post(f"{API}/api/auth/become-organizer",
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["role"] == "organizer"
    assert r.json()["upgraded"] is False


def test_admin_upgrade_does_not_downgrade():
    # admin@allsale.events is seeded admin
    r = requests.post(f"{API}/api/auth/login", json={
        "email": "admin@allsale.events", "password": "admin123",
    }, timeout=10)
    token = r.json()["token"]
    r2 = requests.post(f"{API}/api/auth/become-organizer",
                       headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"
    assert r2.json()["upgraded"] is False


def test_attendee_cannot_create_event_before_upgrade():
    token, _ = _register("attendee")
    payload = {
        "title": "blocked", "description": "x", "category": "music",
        "venue": "x", "city": "x", "date": "2026-12-31T20:00:00Z",
        "image_url": "https://example.com/img.png",
        "tiers": [{"name": "GA", "price": 0, "capacity": 10}],
    }
    r = requests.post(f"{API}/api/events",
                      headers={"Authorization": f"Bearer {token}"},
                      json=payload, timeout=10)
    assert r.status_code == 403


async def test_attendee_can_create_event_after_upgrade():
    token, _ = _register("attendee")
    requests.post(f"{API}/api/auth/become-organizer",
                  headers={"Authorization": f"Bearer {token}"}, timeout=10)
    # Use a free tier so the post-upgrade attendee bypasses the paid-event
    # Stripe-Connect gate (added in Feb 2026). The point of this test is to
    # prove the role flip lets them call POST /events at all — payment
    # routing is exercised elsewhere.
    payload = {
        "title": f"After Upgrade {uuid.uuid4().hex[:6]}",
        "description": "x", "category": "music",
        "venue": "x", "city": "x", "date": "2026-12-31T20:00:00Z",
        "image_url": "https://example.com/img.png",
        "tiers": [{"name": "GA", "price": 0, "capacity": 10}],
    }
    r = requests.post(f"{API}/api/events",
                      headers={"Authorization": f"Bearer {token}"},
                      json=payload, timeout=10)
    assert r.status_code == 200
    # Cleanup the event via the session-loop's shared db (no asyncio.run!)
    eid = r.json()["event_id"]
    await db.events.delete_one({"event_id": eid})
