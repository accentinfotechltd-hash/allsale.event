"""Group-booking auto-discount.

Covers:
  - When `min_qty` is met, group discount applies to the booking subtotal
  - Below the threshold, no discount applies
  - Group discount stacks with a promo code (group first, promo on remainder)
  - When `min_qty` is 0 or `pct_off` is 0, feature is disabled (no discount)
"""
from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from models import HoldIn  # noqa: E402
from routers.bookings import create_hold  # noqa: E402


def _make_request():
    req = MagicMock()
    req.query_params = {}
    req.cookies = {}
    return req


async def _seed_event(group_discount):
    organizer_id = f"gd_org_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_gd_{uuid.uuid4().hex[:8]}"
    await db.events.insert_one({
        "event_id": event_id,
        "organizer_id": organizer_id,
        "organizer_name": "Group Org",
        "title": "Group Discount Test",
        "description": "x",
        "category": "music",
        "venue": "v",
        "city": "Auckland",
        "country": "NZ",
        "date": (utc_now() + timedelta(days=5)).isoformat(),
        "image_url": "https://example.com/x.jpg",
        "currency": "NZD",
        "tiers": [{"name": "GA", "price": 100.0, "capacity": 1000}],
        "has_seatmap": False,
        "status": "approved",
        "group_discount": group_discount,
        "created_at": utc_now().isoformat(),
    })
    user_id = f"gd_user_{uuid.uuid4().hex[:8]}"
    user = {
        "user_id": user_id,
        "email": f"{user_id}@test.local",
        "name": "Group Buyer",
        "role": "attendee",
    }
    return event_id, user


async def _cleanup(event_id):
    await db.bookings.delete_many({"event_id": event_id})
    await db.seat_holds.delete_many({"event_id": event_id})
    await db.events.delete_one({"event_id": event_id})


async def test_group_discount_applies_when_threshold_met():
    event_id, user = await _seed_event({"min_qty": 5, "pct_off": 20})
    try:
        # Below threshold → no discount
        b1 = await create_hold(
            HoldIn(event_id=event_id, tier_name="GA", quantity=3),
            _make_request(),
            user,
        )
        assert b1["subtotal"] == 300.0
        assert b1.get("group_discount_amount", 0) == 0

        # At threshold → 20% off 500 = 100
        b2 = await create_hold(
            HoldIn(event_id=event_id, tier_name="GA", quantity=5),
            _make_request(),
            user,
        )
        assert b2["group_discount_amount"] == 100.0
        assert b2["group_discount_pct"] == 20
        assert b2["subtotal"] == 400.0
    finally:
        await _cleanup(event_id)



async def test_group_discount_disabled_when_threshold_zero():
    event_id, user = await _seed_event({"min_qty": 0, "pct_off": 25})
    try:
        b = await create_hold(
            HoldIn(event_id=event_id, tier_name="GA", quantity=10),
            _make_request(),
            user,
        )
        assert b.get("group_discount_amount", 0) == 0
        assert b["subtotal"] == 1000.0
    finally:
        await _cleanup(event_id)



async def test_group_discount_stacks_with_promo_code():
    event_id, user = await _seed_event({"min_qty": 4, "pct_off": 10})
    code_id = f"dc_{uuid.uuid4().hex[:8]}"
    code = f"GD{uuid.uuid4().hex[:4].upper()}"
    ev = await db.events.find_one({"event_id": event_id}, {"organizer_id": 1})
    await db.discount_codes.insert_one({
        "code_id": code_id,
        "event_id": event_id,
        "code": code,
        "kind": "fixed",
        "value": 50.0,
        "active": True,
        "uses_count": 0,
        "max_uses": None,
        "min_quantity": 0,
        "tier_name": None,
        "created_by": ev["organizer_id"],
        "created_at": utc_now().isoformat(),
    })
    try:
        # qty=4 → subtotal $400, group 10% = $40 → $360, then promo $50 fixed → $310
        b = await create_hold(
            HoldIn(event_id=event_id, tier_name="GA", quantity=4, code=code),
            _make_request(),
            user,
        )
        assert b["group_discount_amount"] == 40.0
        assert b["discount_code"] == code
        assert b["discount_amount"] == 50.0
        # face_value reflects the final pre-fee buyer amount
        assert b["face_value"] == 310.0
    finally:
        await db.discount_codes.delete_one({"code_id": code_id})
        await _cleanup(event_id)

