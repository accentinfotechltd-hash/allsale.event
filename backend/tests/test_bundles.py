"""Bundles / season passes (c2) — happy-path bundle creation + finalize."""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers.bundles import (  # noqa: E402
    BundleIn, create_bundle, finalize_bundle_purchase, get_bundle,
)


async def _seed_two_events(organizer_id):
    eids = []
    for i in range(2):
        eid = f"evt_bn_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": eid, "organizer_id": organizer_id,
            "organizer_name": "Bundle Org",
            "title": f"Bundle Event {i}",
            "description": "x", "category": "music", "venue": "v", "city": "Auckland",
            "country": "NZ",
            "date": (utc_now() + timedelta(days=5 + i)).isoformat(),
            "image_url": "https://example.com/x.jpg",
            "currency": "NZD",
            "tiers": [{"name": "GA", "price": 80.0, "capacity": 100}],
            "has_seatmap": False,
            "status": "approved",
            "created_at": utc_now().isoformat(),
        })
        eids.append(eid)
    return eids


def test_create_bundle_rejects_foreign_events():
    async def run():
        my_org = f"org_{uuid.uuid4().hex[:6]}"
        other_org = f"org_{uuid.uuid4().hex[:6]}"
        ev_mine = await _seed_two_events(my_org)
        ev_other = await _seed_two_events(other_org)
        try:
            user = {"user_id": my_org, "name": "Me", "email": "me@t.local", "role": "organizer"}
            payload = BundleIn(
                title="Mixed Bundle",
                event_ids=ev_mine + ev_other[:1],
                price=150.0,
            )
            with pytest.raises(HTTPException) as ex:
                await create_bundle(payload, user)
            assert ex.value.status_code == 403
        finally:
            await db.events.delete_many({"organizer_id": {"$in": [my_org, other_org]}})
            await db.bundles.delete_many({"organizer_id": my_org})

    asyncio.get_event_loop().run_until_complete(run())


def test_create_and_get_bundle_computes_savings():
    async def run():
        org = f"org_{uuid.uuid4().hex[:6]}"
        eids = await _seed_two_events(org)
        try:
            user = {"user_id": org, "name": "Me", "email": "me@t.local", "role": "organizer"}
            payload = BundleIn(
                title="Summer Pass",
                description="Both shows",
                event_ids=eids,
                price=120.0,  # vs $160 separately (2 x $80)
            )
            created = await create_bundle(payload, user)
            assert created["bundle_id"]
            assert created["currency"] == "NZD"
            # Public detail
            detail = await get_bundle(created["bundle_id"])
            assert len(detail["events"]) == 2
            assert detail["total_separate"] == 160.0
            assert detail["savings"] == 40.0
        finally:
            await db.bundles.delete_many({"organizer_id": org})
            await db.events.delete_many({"organizer_id": org})

    asyncio.get_event_loop().run_until_complete(run())


def test_finalize_purchase_creates_bookings_per_event():
    async def run():
        org = f"org_{uuid.uuid4().hex[:6]}"
        eids = await _seed_two_events(org)
        try:
            user = {"user_id": org, "name": "Me", "email": "me@t.local", "role": "organizer"}
            payload = BundleIn(
                title="Twin Pass", event_ids=eids, price=100.0,
            )
            bundle = await create_bundle(payload, user)
            buyer_id = f"buyer_{uuid.uuid4().hex[:6]}"
            purchase_id = f"bp_{uuid.uuid4().hex[:8]}"
            await db.bundle_purchases.insert_one({
                "purchase_id": purchase_id,
                "bundle_id": bundle["bundle_id"],
                "user_id": buyer_id,
                "user_email": "buyer@t.local",
                "user_name": "Buyer",
                "stripe_session_id": "sess_test",
                "amount": 100.0,
                "currency": "NZD",
                "status": "pending",
                "booking_ids": [],
                "created_at": utc_now().isoformat(),
            })
            ok = await finalize_bundle_purchase(purchase_id)
            assert ok is True
            # 2 paid bookings created
            bookings = []
            async for b in db.bookings.find({"bundle_purchase_id": purchase_id}, {"_id": 0}):
                bookings.append(b)
            assert len(bookings) == 2
            assert all(b["status"] == "paid" for b in bookings)
            assert all(b.get("qr_code") for b in bookings)
            # Idempotency
            ok2 = await finalize_bundle_purchase(purchase_id)
            assert ok2 is False
            # sold_count bumped exactly once
            refreshed = await db.bundles.find_one({"bundle_id": bundle["bundle_id"]}, {"_id": 0})
            assert refreshed["sold_count"] == 1
        finally:
            await db.bookings.delete_many({"bundle_purchase_id": {"$regex": "^bp_"}})
            await db.bundle_purchases.delete_many({"bundle_id": {"$regex": "^bnd_"}})
            await db.bundles.delete_many({"organizer_id": org})
            await db.events.delete_many({"organizer_id": org})

    asyncio.get_event_loop().run_until_complete(run())
