"""Iteration 14 enhancements: review badges, gift card redemptions panel,
auto-applied referral credits at payout request.
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
from routers.events import list_events, get_event  # noqa: E402
from routers.gift_cards import organizer_gift_card_redemptions  # noqa: E402
from routers.payouts import organizer_request_payout, admin_reject_payout, PayoutRequestIn, RejectIn  # noqa: E402


def test_event_list_annotates_avg_stars_when_at_least_three_reviews():
    async def run():
        organizer_id = f"org_{uuid.uuid4().hex[:6]}"
        event_id = f"evt_rv_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": organizer_id,
            "title": "Reviewed Event", "description": "x", "category": "music",
            "venue": "v", "city": "Auckland", "country": "NZ",
            "date": (utc_now() + timedelta(days=2)).isoformat(),
            "image_url": "https://example.com/x.jpg", "currency": "NZD",
            "tiers": [{"name": "GA", "price": 50.0, "capacity": 50}],
            "has_seatmap": False, "status": "approved",
            "created_at": utc_now().isoformat(),
        })
        for s in (5, 5, 4):
            await db.event_feedback.insert_one({
                "event_id": event_id, "booking_id": f"bkg_{uuid.uuid4().hex[:6]}",
                "stars": s, "submitted_at": utc_now().isoformat(),
            })
        try:
            items = await list_events(q=None, category=None, city=None, country=None, past=False, limit=50)
            mine = next((e for e in items if e["event_id"] == event_id), None)
            assert mine is not None
            assert mine["avg_stars"] == 4.7
            assert mine["reviews_count"] == 3
            # Single event endpoint should expose the same
            detail = await get_event(event_id)
            assert detail["avg_stars"] == 4.7
            assert detail["reviews_count"] == 3
        finally:
            await db.event_feedback.delete_many({"event_id": event_id})
            await db.events.delete_one({"event_id": event_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_event_list_skips_badge_when_fewer_than_three_reviews():
    async def run():
        organizer_id = f"org_{uuid.uuid4().hex[:6]}"
        event_id = f"evt_rv_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": organizer_id,
            "title": "Lonely Event", "description": "x", "category": "music",
            "venue": "v", "city": "Auckland", "country": "NZ",
            "date": (utc_now() + timedelta(days=2)).isoformat(),
            "image_url": "https://example.com/x.jpg", "currency": "NZD",
            "tiers": [{"name": "GA", "price": 50.0, "capacity": 50}],
            "has_seatmap": False, "status": "approved",
            "created_at": utc_now().isoformat(),
        })
        # Only 2 reviews
        for _ in range(2):
            await db.event_feedback.insert_one({
                "event_id": event_id, "booking_id": f"bkg_{uuid.uuid4().hex[:6]}",
                "stars": 5, "submitted_at": utc_now().isoformat(),
            })
        try:
            items = await list_events(q=None, category=None, city=None, country=None, past=False, limit=50)
            mine = next((e for e in items if e["event_id"] == event_id), None)
            assert mine is not None
            assert "avg_stars" not in mine
            assert "reviews_count" not in mine
        finally:
            await db.event_feedback.delete_many({"event_id": event_id})
            await db.events.delete_one({"event_id": event_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_organizer_gift_card_redemptions_lists_only_my_events():
    async def run():
        org = f"org_{uuid.uuid4().hex[:6]}"
        other_org = f"org_{uuid.uuid4().hex[:6]}"
        event_id = f"evt_gcr_{uuid.uuid4().hex[:8]}"
        other_event_id = f"evt_gcr_{uuid.uuid4().hex[:8]}"
        await db.events.insert_many([
            {"event_id": event_id, "organizer_id": org, "title": "Mine", "status": "approved", "created_at": utc_now().isoformat()},
            {"event_id": other_event_id, "organizer_id": other_org, "title": "Theirs", "status": "approved", "created_at": utc_now().isoformat()},
        ])
        # Two paid bookings on MY event with a gift card, one on the other
        for evid, gc_amount in [(event_id, 25.0), (event_id, 10.0), (other_event_id, 5.0)]:
            await db.bookings.insert_one({
                "booking_id": f"bkg_{uuid.uuid4().hex[:8]}",
                "event_id": evid, "event_title": "X",
                "user_id": "buyer1", "user_email": "b@t.local", "user_name": "Buyer",
                "tier_name": "GA", "quantity": 1, "seats": [],
                "currency": "NZD", "status": "paid",
                "gift_card_code": "GIFT-XXXX-YYYY-ZZZZ",
                "gift_card_amount": gc_amount,
                "created_at": utc_now().isoformat(),
            })
        try:
            user = {"user_id": org, "role": "organizer", "name": "Me", "email": "me@t.local"}
            res = await organizer_gift_card_redemptions(user)
            assert res["totals"]["count"] == 2
            assert res["totals"]["amount"] == 35.0
            assert len(res["recent"]) == 2
            assert all(r["event_id"] == event_id for r in res["recent"])
        finally:
            await db.bookings.delete_many({"event_id": {"$in": [event_id, other_event_id]}})
            await db.events.delete_many({"event_id": {"$in": [event_id, other_event_id]}})

    asyncio.get_event_loop().run_until_complete(run())


def test_payout_request_auto_applies_credits_and_reject_releases_them():
    async def run():
        org = f"org_{uuid.uuid4().hex[:6]}"
        await db.users.insert_one({
            "user_id": org, "name": "Me", "email": "me@example.com",
            "role": "organizer", "created_at": utc_now().isoformat(),
        })
        event_id = f"evt_p_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": org,
            "title": "Paid Event", "status": "approved",
            "date": (utc_now() - timedelta(days=10)).isoformat(),  # past so it's payout-eligible
            "currency": "NZD", "tiers": [{"name": "GA", "price": 100.0, "capacity": 10}],
            "has_seatmap": False,
            "created_at": utc_now().isoformat(),
        })
        booking_id = f"bkg_{uuid.uuid4().hex[:8]}"
        await db.bookings.insert_one({
            "booking_id": booking_id, "event_id": event_id,
            "user_id": "buyer", "user_email": "b@t.local", "user_name": "Buyer",
            "tier_name": "GA", "quantity": 1, "seats": [],
            "amount": 100.0, "face_value": 100.0,
            "currency": "NZD", "status": "paid",
            "paid_at": (utc_now() - timedelta(days=8)).isoformat(),
            "created_at": (utc_now() - timedelta(days=8)).isoformat(),
        })
        credit_id = f"crd_{uuid.uuid4().hex[:8]}"
        await db.organizer_credits.insert_one({
            "credit_id": credit_id, "user_id": org,
            "amount": 50.0, "currency": "NZD",
            "reason": "referral_payout", "status": "available",
            "created_at": utc_now().isoformat(),
        })
        try:
            user = {"user_id": org, "role": "organizer", "name": "Me", "email": "me@example.com"}
            payout = await organizer_request_payout(PayoutRequestIn(notes="test"), user)
            assert payout["credit_applied"] == 50.0
            assert payout["credit_ids_applied"] == [credit_id]
            c = await db.organizer_credits.find_one({"credit_id": credit_id}, {"_id": 0})
            assert c["status"] == "applied"
            assert c["applied_to_payout_id"] == payout["payout_id"]

            # Reject → credits released
            admin = {"user_id": "admin", "role": "admin"}
            await admin_reject_payout(payout["payout_id"], RejectIn(reason="test reject"), admin)
            c2 = await db.organizer_credits.find_one({"credit_id": credit_id}, {"_id": 0})
            assert c2["status"] == "available"
            assert "applied_to_payout_id" not in c2
        finally:
            await db.payouts.delete_many({"organizer_id": org})
            await db.bookings.delete_many({"booking_id": booking_id})
            await db.events.delete_one({"event_id": event_id})
            await db.organizer_credits.delete_one({"credit_id": credit_id})
            await db.users.delete_one({"user_id": org})

    asyncio.get_event_loop().run_until_complete(run())
