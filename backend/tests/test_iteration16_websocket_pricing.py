"""Iteration 16 — Live WebSocket seat updates + seat-section pricing.

Covers:
- WebSocket endpoint accepts connections and emits an initial snapshot.
- `seat_section_for_row` correctly maps a row index → its containing section.
- `seat_price_for` picks the section price if set, else falls back to base.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest_asyncio
import requests
import websockets
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, seat_section_for_row, seat_price_for  # noqa: E402

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"
WS_API = API.replace("http", "ws")


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _cleanup_module():
    yield
    try:
        ids = [e["event_id"] async for e in db.events.find(
            {"event_id": {"$regex": "^evt_ws_test_"}}, {"_id": 0, "event_id": 1},
        )]
        if ids:
            await db.events.delete_many({"event_id": {"$in": ids}})
            await db.seat_reservations.delete_many({"event_id": {"$in": ids}})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Section pricing helpers (pure functions)
# ---------------------------------------------------------------------------
def test_seat_section_for_row_no_sections_returns_none():
    event = {"seatmap_sections": []}
    assert seat_section_for_row(event, 0) is None
    assert seat_section_for_row(event, 5) is None


def test_seat_section_for_row_picks_correct_section():
    """Layout: rows 0-2 = front zone (no section); rows 3-5 = Mezzanine; rows 6+ = Balcony."""
    event = {"seatmap_sections": [
        {"after_row": 2, "label": "Mezzanine", "price": 80},
        {"after_row": 5, "label": "Balcony", "price": 50},
    ]}
    # Front zone (no section)
    assert seat_section_for_row(event, 0) is None
    assert seat_section_for_row(event, 2) is None
    # Mezzanine
    assert seat_section_for_row(event, 3)["label"] == "Mezzanine"
    assert seat_section_for_row(event, 5)["label"] == "Mezzanine"
    # Balcony
    assert seat_section_for_row(event, 6)["label"] == "Balcony"
    assert seat_section_for_row(event, 10)["label"] == "Balcony"


def test_seat_price_for_uses_section_price_when_set():
    event = {
        "seat_price": 60.0,
        "seatmap_sections": [
            {"after_row": 2, "label": "Mezzanine", "price": 80},
        ],
    }
    # Front zone → falls back to base
    assert seat_price_for(event, "A-5") == 60.0
    assert seat_price_for(event, "C-5") == 60.0
    # Mezzanine → 80
    assert seat_price_for(event, "D-5") == 80.0


def test_seat_price_for_falls_back_when_section_has_no_price():
    event = {
        "seat_price": 60.0,
        "seatmap_sections": [
            {"after_row": 2, "label": "Mezzanine"},  # no price
        ],
    }
    assert seat_price_for(event, "D-5") == 60.0  # falls back to base


def test_seat_price_for_handles_invalid_seat_id():
    event = {"seat_price": 50.0, "seatmap_sections": [{"after_row": 1, "price": 100}]}
    assert seat_price_for(event, "nonsense") == 50.0
    assert seat_price_for(event, "") == 50.0


# ---------------------------------------------------------------------------
# WebSocket connection
# ---------------------------------------------------------------------------
async def _seed_tier_event() -> str:
    # Use the current Feb-2026+ seed; legacy organizer@allsale.events was removed.
    org = await db.users.find_one({"email": "orgtester@allsale.events"}, {"_id": 0})
    if not org:
        # Fall back to any admin if the seed wasn't run on this DB.
        org = await db.users.find_one({"role": "admin"}, {"_id": 0})
    eid = f"evt_ws_test_{uuid.uuid4().hex[:6]}"
    await db.events.insert_one({
        "event_id": eid, "title": "WS Test",
        "organizer_id": org["user_id"], "category": "music",
        "city": "x", "venue": "x", "date": "2026-12-31T20:00:00+00:00",
        "image_url": "", "status": "approved",
        "tiers": [{"name": "GA", "price": 50, "capacity": 100, "sold": 0}],
        "has_seatmap": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return eid


async def test_websocket_sends_initial_snapshot():
    eid = await _seed_tier_event()
    url = f"{WS_API}/api/ws/events/{eid}"
    async with websockets.connect(url) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
    snap = json.loads(raw)
    assert snap["type"] == "snapshot"
    assert "tier_status" in snap
    assert len(snap["tier_status"]) == 1
    assert snap["tier_status"][0]["name"] == "GA"
    assert snap["sold_out"] is False


async def test_websocket_unknown_event_still_connects_with_empty_snapshot():
    """A WS for a deleted/unknown event_id should not crash; returns empty snapshot."""
    url = f"{WS_API}/api/ws/events/evt_nonexistent_xxx"
    async with websockets.connect(url) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
    snap = json.loads(raw)
    assert snap["type"] == "snapshot"
    assert snap.get("booked") == []
    assert snap.get("held") == []
