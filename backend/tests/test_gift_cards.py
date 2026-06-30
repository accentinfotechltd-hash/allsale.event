"""Gift cards (c1) — core helpers.

We test the redemption path directly (atomic balance decrement, currency
guard, depleted state). The Stripe purchase + webhook minting is mocked.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from models import HoldIn  # noqa: E402
from routers.gift_cards import (  # noqa: E402
    _gen_gift_code, _normalize_code, redeem_gift_card_for_booking,
    finalize_gift_card_purchase,
)
from routers.bookings import create_hold  # noqa: E402


def test_gen_gift_code_format():
    for _ in range(20):
        code = _gen_gift_code()
        assert code.startswith("GIFT-")
        parts = code.split("-")
        assert len(parts) == 4
        assert all(len(p) == 4 for p in parts[1:])


def test_normalize_code_strips_whitespace_and_uppercases():
    assert _normalize_code("  gift-abcd-efgh-ijkl  ") == "GIFT-ABCD-EFGH-IJKL"
    assert _normalize_code(" gift abcd ") == "GIFTABCD"


async def test_redeem_gift_card_partial_and_depletion():
    code = _gen_gift_code()
    card_id = f"gc_{uuid.uuid4().hex[:8]}"
    await db.gift_cards.insert_one({
        "card_id": card_id,
        "code": code,
        "amount": 100.0,
        "balance": 100.0,
        "currency": "NZD",
        "status": "active",
        "redemptions": [],
        "created_at": utc_now().isoformat(),
    })
    try:
        # Spend $40 → balance $60, still active
        r1 = await redeem_gift_card_for_booking(code, 40.0, "bkg_test1", "NZD")
        assert r1["applied"] == 40.0
        assert r1["remaining_balance"] == 60.0
        card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert card["balance"] == 60.0
        assert card["status"] == "active"
        assert len(card["redemptions"]) == 1

        # Try to spend $200 → only $60 available → depletes
        r2 = await redeem_gift_card_for_booking(code, 200.0, "bkg_test2", "NZD")
        assert r2["applied"] == 60.0
        assert r2["remaining_balance"] == 0
        card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert card["status"] == "depleted"

        # Next redemption fails (no balance)
        with pytest.raises(HTTPException) as ex:
            await redeem_gift_card_for_booking(code, 5.0, "bkg_test3", "NZD")
        assert ex.value.status_code == 400
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_redeem_rejects_wrong_currency():
    code = _gen_gift_code()
    card_id = f"gc_{uuid.uuid4().hex[:8]}"
    await db.gift_cards.insert_one({
        "card_id": card_id, "code": code,
        "amount": 50.0, "balance": 50.0, "currency": "NZD",
        "status": "active", "redemptions": [],
        "created_at": utc_now().isoformat(),
    })
    try:
        with pytest.raises(HTTPException) as ex:
            await redeem_gift_card_for_booking(code, 10.0, "bkg_test", "USD")
        assert ex.value.status_code == 400
        assert "currency" in ex.value.detail.lower()
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_finalize_purchase_activates_pending_card():
    code = _gen_gift_code()
    card_id = f"gc_{uuid.uuid4().hex[:8]}"
    await db.gift_cards.insert_one({
        "card_id": card_id, "code": code,
        "amount": 25.0, "balance": 25.0, "currency": "NZD",
        "status": "pending", "redemptions": [],
        "recipient_email": "nobody@example.com",
        "recipient_name": "Test",
        "purchaser_name": "Tester",
        "personal_note": None,
        "created_at": utc_now().isoformat(),
    })
    try:
        ok = await finalize_gift_card_purchase(card_id)
        assert ok is True
        card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert card["status"] == "active"
        # Idempotent — second call returns False
        ok2 = await finalize_gift_card_purchase(card_id)
        assert ok2 is False
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_booking_hold_applies_gift_card_amount():
    # Seed event + active gift card
    organizer_id = f"gco_{uuid.uuid4().hex[:6]}"
    event_id = f"evt_gc_{uuid.uuid4().hex[:8]}"
    from datetime import timedelta
    await db.events.insert_one({
        "event_id": event_id,
        "organizer_id": organizer_id,
        "organizer_name": "GC Org",
        "title": "GC Test Event",
        "description": "x",
        "category": "music",
        "venue": "v",
        "city": "Auckland",
        "country": "NZ",
        "date": (utc_now() + timedelta(days=3)).isoformat(),
        "image_url": "https://example.com/x.jpg",
        "currency": "NZD",
        "tiers": [{"name": "GA", "price": 100.0, "capacity": 100}],
        "has_seatmap": False,
        "status": "approved",
        "created_at": utc_now().isoformat(),
    })
    code = _gen_gift_code()
    card_id = f"gc_{uuid.uuid4().hex[:8]}"
    await db.gift_cards.insert_one({
        "card_id": card_id, "code": code,
        "amount": 30.0, "balance": 30.0, "currency": "NZD",
        "status": "active", "redemptions": [],
        "created_at": utc_now().isoformat(),
    })
    user_id = f"gcu_{uuid.uuid4().hex[:8]}"
    user = {"user_id": user_id, "email": f"{user_id}@t.local", "name": "GC Buyer", "role": "attendee"}
    req = MagicMock()
    req.query_params = {}
    req.cookies = {}
    try:
        b = await create_hold(
            HoldIn(event_id=event_id, tier_name="GA", quantity=1, gift_card_code=code),
            req,
            user,
        )
        # Booking face_value = $100, buyer_total ≈ $100 + fees, gift card $30 applied
        assert b["gift_card_code"] == code
        assert b["gift_card_amount"] == 30.0
        assert b["amount"] < 100.0  # gift card reduced charge
        # Card balance now 0
        card = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert card["balance"] == 0.0
        assert card["status"] == "depleted"
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})
        await db.bookings.delete_many({"event_id": event_id})
        await db.seat_holds.delete_many({"event_id": event_id})
        await db.events.delete_one({"event_id": event_id})

