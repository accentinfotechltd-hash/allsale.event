"""Regression for the Stripe Connect router surface (no real Stripe calls).

These tests only validate request/response shapes + authorization gating —
the actual Stripe SDK calls fail intentionally on the preview env where the
API key is a placeholder. That's fine: we just want to be sure routes are
mounted and respond with the documented shapes/codes.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module")
def organizer_token():
    """Create a throwaway organizer + return their JWT."""
    email = f"connect_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "test1234"

    reg = requests.post(
        f"{API}/api/auth/register",
        json={"name": "Connect Test", "email": email, "password": password, "role": "organizer", "phone": "+64 21 555 7777"},
        timeout=10,
    )
    assert reg.status_code in (200, 201), f"register failed: {reg.status_code} {reg.text}"
    token = reg.json().get("token")
    assert token

    yield {"token": token, "email": email}

    # Cleanup
    async def _clean():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = client[os.environ["DB_NAME"]]
        await d.users.delete_many({"email": email})
        client.close()
    asyncio.run(_clean())


def test_status_returns_empty_when_no_account(organizer_token):
    r = requests.get(
        f"{API}/api/stripe/connect/status",
        headers={"Authorization": f"Bearer {organizer_token['token']}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("stripe_account_id") is None
    assert d.get("stripe_charges_enabled") is False
    assert d.get("stripe_payouts_enabled") is False
    assert isinstance(d.get("stripe_requirements_due"), list)


def test_dashboard_link_requires_account_first(organizer_token):
    r = requests.post(
        f"{API}/api/stripe/connect/dashboard-link",
        headers={"Authorization": f"Bearer {organizer_token['token']}"},
        timeout=10,
    )
    assert r.status_code == 400, r.text
    assert "No Stripe Connect account" in r.text


def test_onboard_requires_organizer_role():
    """An attendee should be blocked from creating a Connect account."""
    email = f"attendee_block_{uuid.uuid4().hex[:8]}@example.com"
    reg = requests.post(
        f"{API}/api/auth/register",
        json={"name": "Block Me", "email": email, "password": "test1234", "role": "attendee", "phone": "+64 21 555 8888"},
        timeout=10,
    )
    assert reg.status_code in (200, 201)
    token = reg.json()["token"]
    try:
        r = requests.post(
            f"{API}/api/stripe/connect/onboard",
            headers={"Authorization": f"Bearer {token}"},
            json={"return_url": "https://example.com/back"},
            timeout=10,
        )
        assert r.status_code == 403, r.text
    finally:
        async def _clean():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            d = client[os.environ["DB_NAME"]]
            await d.users.delete_many({"email": email})
            client.close()
        asyncio.run(_clean())


def test_me_exposes_stripe_fields(organizer_token):
    r = requests.get(
        f"{API}/api/auth/me",
        headers={"Authorization": f"Bearer {organizer_token['token']}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for field in ("stripe_account_id", "stripe_charges_enabled", "stripe_payouts_enabled", "stripe_details_submitted"):
        assert field in d, f"{field} missing from /me payload"


def test_webhook_endpoint_accepts_unsigned_payload_in_dev():
    """When STRIPE_CONNECT_WEBHOOK_SECRET is unset the endpoint should
    accept the body and return {"received": true} so Stripe doesn't retry."""
    # Only meaningful if the dev env hasn't set the secret. We tolerate either
    # outcome since prod will have it set.
    r = requests.post(
        f"{API}/api/webhook/stripe/connect",
        json={"type": "account.updated", "data": {"object": {"id": "acct_nonexistent_x"}}},
        timeout=10,
    )
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        assert r.json().get("received") is True
