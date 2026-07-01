"""Regression tests for the Stripe-Connect per-event payout engine.

Combined into a single asyncio.run() block so the shared motor client stays
bound to one event loop across all scenarios (avoiding `Event loop is closed`
errors when motor reconnects between tests).

We never actually contact Stripe — the engine short-circuits to `skipped`
when Connect isn't verified or no paid bookings exist. End-to-end happy path
is covered by manual smoke tests on production with a live test-mode key.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from connect_payouts_engine import (  # noqa: E402
    _attempt_event_payout,
    PAYOUT_HOLD_HOURS,
)


def _event_doc(*, days_ago: int, organizer_id: str, status: str = "approved") -> dict:
    return {
        "event_id": f"evt_payout_{uuid.uuid4().hex[:10]}",
        "organizer_id": organizer_id,
        "title": "Payout Test",
        "description": "x",
        "category": "music",
        "venue": "v",
        "city": "Auckland",
        "date": (utc_now() - timedelta(days=days_ago)).isoformat(),
        "image_url": "https://example.com/x.jpg",
        "tiers": [{"name": "GA", "price": 10, "capacity": 100}],
        "status": status,
        "currency": "NZD",
    }


async def test_payout_engine_branches():
    org_no_connect = f"user_no_connect_{uuid.uuid4().hex[:8]}"
    org_verified = f"user_verified_{uuid.uuid4().hex[:8]}"
    org_paid = f"user_paid_{uuid.uuid4().hex[:8]}"

    ev_no_connect = _event_doc(days_ago=10, organizer_id=org_no_connect)
    ev_no_revenue = _event_doc(days_ago=10, organizer_id=org_verified)
    ev_already_paid = _event_doc(days_ago=10, organizer_id=org_paid)
    ev_already_paid["payout_status"] = "paid"
    ev_already_paid["payout_transfer_id"] = "tr_already_done"

    await db.users.insert_many([
        {
            "user_id": org_no_connect,
            "email": f"{org_no_connect}@example.com",
            "role": "organizer",
            "name": "No Connect",
            "created_at": utc_now().isoformat(),
        },
        {
            "user_id": org_verified,
            "email": f"{org_verified}@example.com",
            "role": "organizer",
            "name": "Verified",
            "created_at": utc_now().isoformat(),
            "stripe_account_id": "acct_fake_test",
            "stripe_payouts_enabled": True,
        },
        {
            "user_id": org_paid,
            "email": f"{org_paid}@example.com",
            "role": "organizer",
            "name": "Already Paid",
            "created_at": utc_now().isoformat(),
            "stripe_account_id": "acct_fake_test",
            "stripe_payouts_enabled": True,
        },
    ])
    await db.events.insert_many([ev_no_connect, ev_no_revenue, ev_already_paid])

    try:
        # Branch 1: organizer has no Connect — should skip with that reason.
        res1 = await _attempt_event_payout(db, ev_no_connect, triggered_by="test")
        assert res1["status"] == "skipped"
        assert res1["reason"] == "connect not verified"

        # Branch 2: verified but no paid bookings — should mark `no_revenue`
        # so the scheduler never re-attempts.
        res2 = await _attempt_event_payout(db, ev_no_revenue, triggered_by="test")
        assert res2["status"] == "skipped"
        assert res2["reason"] in ("no paid bookings", "net <= 0")
        stored = await db.events.find_one({"event_id": ev_no_revenue["event_id"]}, {"_id": 0})
        assert stored.get("payout_status") == "no_revenue"

        # Branch 3: already-paid event — should be idempotent / skipped.
        res3 = await _attempt_event_payout(db, ev_already_paid, triggered_by="test")
        assert res3["status"] == "skipped"
        assert res3["reason"] == "already paid"
    finally:
        await db.users.delete_many({"user_id": {"$in": [org_no_connect, org_verified, org_paid]}})
        await db.events.delete_many({"event_id": {"$in": [
            ev_no_connect["event_id"], ev_no_revenue["event_id"], ev_already_paid["event_id"],
        ]}})



def test_hold_hours_default_is_five_days():
    """Document the default 5-day hold so a future env change is obvious."""
    assert PAYOUT_HOLD_HOURS == 120
