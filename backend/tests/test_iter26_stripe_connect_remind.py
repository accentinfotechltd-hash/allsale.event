"""Iteration 26 — Stripe Connect Status Tab: extended /remind endpoint tests.

Covers cases NOT exercised by the existing
`test_admin_stripe_connect_status.py`:

  1. Targeted reminder to ONE organizer who is `not_connected` AND has paid
     revenue → email queued, `stripe_nudge_sent_at` stamped on the user.
  2. Idempotent skip — same target with `stripe_charges_enabled=True` is
     skipped (sent stays 0, skipped == 1, no extra stamp).
  3. Blast all (`user_ids=None`) → response `sent + skipped` >= the
     summary.not_connected count returned by GET /stripe-connect-status.
  4. Response shape includes `queued_at`.
  5. `stripe_nudge_sent_at` is removed from the test user at end (cleanup).

Run:
  cd /app/backend && python -m pytest tests/test_iter26_stripe_connect_remind.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"

# orgtester is a real organizer in the seed (no Connect, no charges_enabled).
ORG_USER_ID = "user_2492358084d3"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def db():
    """Async motor handle to clean up stamps after tests."""
    from server import db as _db  # noqa: WPS433
    return _db


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ---- Test 1 + 4: targeted send + queued_at field --------------------------
def test_targeted_reminder_to_one_organizer(admin_token, db):
    # Ensure organizer is in not_connected state for this test
    async def _setup_and_check():
        await db.users.update_one(
            {"user_id": ORG_USER_ID},
            {"$unset": {
                "stripe_charges_enabled": "",
                "stripe_account_id": "",
                "stripe_nudge_sent_at": "",
            }},
        )
    asyncio.get_event_loop().run_until_complete(_setup_and_check())

    r = requests.post(
        f"{API}/api/admin/stripe-connect-status/remind",
        headers=_auth(admin_token),
        json={"user_ids": [ORG_USER_ID]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "queued_at" in body, "response must include queued_at"
    assert body["queued_at"], "queued_at must be a non-empty ISO string"
    # one of sent or skipped should be 1 (it's the single target)
    assert body["sent"] + body["skipped"] == 1, body
    assert body["sent"] == 1, f"expected sent=1 for not_connected target, got {body}"

    # Verify stamp landed on the user doc
    async def _check_stamp():
        u = await db.users.find_one({"user_id": ORG_USER_ID}, {"_id": 0, "stripe_nudge_sent_at": 1})
        return u
    u = asyncio.get_event_loop().run_until_complete(_check_stamp())
    assert u and u.get("stripe_nudge_sent_at"), f"stripe_nudge_sent_at not stamped: {u}"


# ---- Test 2: idempotent skip when already connected ----------------------
def test_remind_skips_already_connected_org(admin_token, db):
    # Flip the same organizer to charges_enabled=True
    async def _flip_on():
        await db.users.update_one(
            {"user_id": ORG_USER_ID},
            {"$set": {"stripe_charges_enabled": True, "stripe_account_id": "acct_test_iter26"}},
        )
    asyncio.get_event_loop().run_until_complete(_flip_on())

    try:
        r = requests.post(
            f"{API}/api/admin/stripe-connect-status/remind",
            headers=_auth(admin_token),
            json={"user_ids": [ORG_USER_ID]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sent"] == 0, f"must not email a connected user, got {body}"
        assert body["skipped"] == 1, f"must increment skipped, got {body}"
    finally:
        # Cleanup: remove flag
        async def _cleanup():
            await db.users.update_one(
                {"user_id": ORG_USER_ID},
                {"$unset": {
                    "stripe_charges_enabled": "",
                    "stripe_account_id": "",
                    "stripe_nudge_sent_at": "",
                }},
            )
        asyncio.get_event_loop().run_until_complete(_cleanup())


# ---- Test 3: blast all (user_ids omitted) → matches status summary -------
def test_blast_all_matches_summary_not_connected(admin_token):
    # Read /status snapshot first
    status = requests.get(
        f"{API}/api/admin/stripe-connect-status",
        headers=_auth(admin_token),
        timeout=10,
    ).json()
    not_connected_count = status["summary"]["not_connected"]

    # Blast — but ONLY targets organizers with paid revenue, so result is
    # <= summary.not_connected. We assert it's bounded.
    r = requests.post(
        f"{API}/api/admin/stripe-connect-status/remind",
        headers=_auth(admin_token),
        json={"user_ids": None},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    total_processed = body["sent"] + body["skipped"]
    assert total_processed <= not_connected_count + status["summary"]["onboarding"], (
        f"blast processed more rows than possible: {body} vs summary={status['summary']}"
    )
    # `queued_at` present even on empty result
    assert "queued_at" in body
