"""Regression tests for multi-organizer revenue splits (Iteration 29).

All scenarios share a single `asyncio.run()` block so motor's connection
cache stays bound to one event loop (avoids "Event loop is closed"
errors when motor reconnects between tests).
"""
from __future__ import annotations

import asyncio
import os
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
    _resolve_recipients,
    _attempt_event_payout,
)


def _organizer_doc(*, verified: bool = True, suffix: str = "") -> dict:
    uid = f"rs_user_{suffix}_{uuid.uuid4().hex[:8]}"
    doc = {
        "user_id": uid,
        "email": f"{uid}@example.com",
        "role": "organizer",
        "name": f"Org {suffix}".strip(),
        "created_at": utc_now().isoformat(),
    }
    if verified:
        doc["stripe_account_id"] = f"acct_{uuid.uuid4().hex[:14]}"
        doc["stripe_payouts_enabled"] = True
        doc["stripe_charges_enabled"] = True
    return doc


def _event_doc(*, organizer_id: str, splits=None) -> dict:
    e = {
        "event_id": f"evt_rs_{uuid.uuid4().hex[:10]}",
        "organizer_id": organizer_id,
        "title": "Splits Test",
        "description": "x",
        "category": "music",
        "venue": "v",
        "city": "Auckland",
        "date": (utc_now() - timedelta(days=10)).isoformat(),
        "image_url": "https://example.com/x.jpg",
        "tiers": [{"name": "GA", "price": 10, "capacity": 100}],
        "status": "approved",
        "currency": "NZD",
    }
    if splits is not None:
        e["revenue_splits"] = splits
    return e


async def test_revenue_splits_end_to_end():
    org_a = _organizer_doc(suffix="A")
    org_b = _organizer_doc(suffix="B")
    org_c_unverified = _organizer_doc(verified=False, suffix="C")
    org_solo = _organizer_doc(suffix="solo")
    owner = _organizer_doc(suffix="owner")
    co_a = _organizer_doc(suffix="coA")
    attendee_uid = f"rs_att_{uuid.uuid4().hex[:8]}"
    attendee_doc = {
        "user_id": attendee_uid,
        "email": f"{attendee_uid}@example.com",
        "role": "attendee",
        "name": "Just Attendee",
        "created_at": utc_now().isoformat(),
    }
    ev_engine = _event_doc(organizer_id=org_a["user_id"], splits=[
        {"user_id": org_a["user_id"], "percent": 60},
        {"user_id": org_b["user_id"], "percent": 40},
    ])
    ev_http = _event_doc(organizer_id=owner["user_id"])

    await db.users.insert_many([
        org_a, org_b, org_c_unverified, org_solo,
        owner, co_a, attendee_doc,
    ])
    await db.events.insert_many([ev_engine, ev_http])

    try:
        # ===== Recipient resolution =====
        ev_solo = _event_doc(organizer_id=org_solo["user_id"])
        rcpts = await _resolve_recipients(db, ev_solo, 100.0)
        assert len(rcpts) == 1
        assert rcpts[0]["user_id"] == org_solo["user_id"]
        assert rcpts[0]["amount"] == 100.0

        ev_two = _event_doc(organizer_id=org_a["user_id"], splits=[
            {"user_id": org_a["user_id"], "label": "Promoter", "percent": 70},
            {"user_id": org_b["user_id"], "label": "Venue", "percent": 30},
        ])
        rcpts = await _resolve_recipients(db, ev_two, 100.0)
        assert len(rcpts) == 2
        amounts = {r["user_id"]: r["amount"] for r in rcpts}
        assert amounts[org_a["user_id"]] == 70.0
        assert amounts[org_b["user_id"]] == 30.0
        labels = {r["user_id"]: r["label"] for r in rcpts}
        assert labels[org_a["user_id"]] == "Promoter"

        # Mixed verified/unverified — unverified dropped
        ev_mixed = _event_doc(organizer_id=org_a["user_id"], splits=[
            {"user_id": org_a["user_id"], "percent": 50},
            {"user_id": org_c_unverified["user_id"], "percent": 50},
        ])
        rcpts = await _resolve_recipients(db, ev_mixed, 200.0)
        assert len(rcpts) == 1
        assert rcpts[0]["user_id"] == org_a["user_id"]
        assert rcpts[0]["amount"] == 100.0  # 50% of 200

        # Sum != 100 → fallback to organizer-only
        ev_bad = _event_doc(organizer_id=org_solo["user_id"], splits=[
            {"user_id": org_a["user_id"], "percent": 25},
            {"user_id": org_b["user_id"], "percent": 25},
        ])
        rcpts = await _resolve_recipients(db, ev_bad, 100.0)
        assert len(rcpts) == 1
        assert rcpts[0]["user_id"] == org_solo["user_id"]
        assert rcpts[0]["amount"] == 100.0

        # ===== Engine short-circuit =====
        res = await _attempt_event_payout(db, ev_engine, triggered_by="test")
        assert res["status"] == "skipped"
        assert res["reason"] == "no paid bookings"
        stored = await db.events.find_one({"event_id": ev_engine["event_id"]}, {"_id": 0})
        assert stored.get("payout_status") == "no_revenue"

        # ===== HTTP endpoint validation =====
        os.environ.setdefault("JWT_SECRET", "test-secret")
        from httpx import AsyncClient, ASGITransport  # noqa: WPS433
        from server import app  # noqa: WPS433
        import jwt as _jwt  # noqa: WPS433

        token = _jwt.encode(
            {"sub": owner["user_id"], "email": owner["email"], "role": "organizer"},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Empty splits → 400
            r = await client.put(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                json={"splits": []},
                headers=headers,
            )
            assert r.status_code == 400, r.text

            # Sum != 100 → 400
            r = await client.put(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                json={"splits": [
                    {"user_id": owner["user_id"], "percent": 60},
                    {"user_id": co_a["user_id"], "percent": 30},
                ]},
                headers=headers,
            )
            assert r.status_code == 400, r.text
            assert "100" in r.json().get("detail", "")

            # Attendee can't be a recipient → 400
            r = await client.put(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                json={"splits": [
                    {"user_id": owner["user_id"], "percent": 50},
                    {"user_id": attendee_uid, "percent": 50},
                ]},
                headers=headers,
            )
            assert r.status_code == 400, r.text
            assert "not an organizer" in r.json().get("detail", "").lower()

            # Valid 70/30 → 200 and persists
            r = await client.put(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                json={"splits": [
                    {"user_id": owner["user_id"], "label": "Promoter", "percent": 70},
                    {"user_id": co_a["user_id"], "label": "Venue", "percent": 30},
                ]},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total_percent"] == 100.0
            assert len(body["splits"]) == 2

            # GET returns the persisted splits hydrated
            r = await client.get(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                headers=headers,
            )
            assert r.status_code == 200
            got = r.json()
            assert got["configured"] is True
            labels = sorted(s["label"] for s in got["splits"])
            assert labels == ["Promoter", "Venue"]

            # DELETE clears
            r = await client.delete(
                f"/api/organizer/events/{ev_http['event_id']}/revenue-splits",
                headers=headers,
            )
            assert r.status_code == 200
            assert r.json()["cleared"] is True

            # Lookup by email finds co_a
            r = await client.get(
                f"/api/organizer/users/lookup?email={co_a['email']}",
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["user_id"] == co_a["user_id"]

            # Lookup unknown email → 404
            r = await client.get(
                "/api/organizer/users/lookup?email=ghost+nope@example.com",
                headers=headers,
            )
            assert r.status_code == 404
    finally:
        await db.users.delete_many({"user_id": {"$in": [
            org_a["user_id"], org_b["user_id"], org_c_unverified["user_id"],
            org_solo["user_id"], owner["user_id"], co_a["user_id"], attendee_uid,
        ]}})
        await db.events.delete_many({"event_id": {"$in": [
            ev_engine["event_id"], ev_http["event_id"],
        ]}})

