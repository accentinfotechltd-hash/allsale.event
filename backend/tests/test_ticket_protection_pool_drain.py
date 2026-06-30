"""Ticket Protection — P2b: pool-drain accounting + destination-charge refund.

Covers:
  • approved claim stamps pool_drain + face_value_loss on both the claim AND
    the booking.
  • destination-charge refunds set reverse_transfer + refund_application_fee.
  • non-destination refunds DO NOT set those (Stripe rejects them).
  • admin stats endpoint reports pool_drain — not full booking amount — as
    the pool outflow. face_value losses are surfaced separately as
    gross_refunded_lifetime.
  • legacy claims (no pool_drain field) gracefully derive from booking.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import ticket_protection as tp  # noqa: E402


# --- helpers ---------------------------------------------------------------

def _seed_booking(booking_id, *, amount, face_value, destination=False, status="paid"):
    """Insert a protected booking for the approval flow to find."""
    return db.bookings.insert_one({
        "booking_id": booking_id,
        "user_id": f"u_{uuid.uuid4().hex[:8]}",
        "user_email": "buyer@example.com",
        "user_name": "Buyer",
        "event_id": "evt_test",
        "event_title": "Test Event",
        "status": status,
        "amount": amount,
        "face_value": face_value,
        "protection_opted": True,
        "protection_amount": round(amount * 0.065, 2),
        "currency": "NZD",
        "stripe_payment_intent": "pi_test_xxx",
        "stripe_destination_charge": destination,
    })


def _seed_claim(claim_id, booking_id, user_id, *, amount, status="pending"):
    return db.protection_claims.insert_one({
        "claim_id": claim_id,
        "booking_id": booking_id,
        "user_id": user_id,
        "user_email": "buyer@example.com",
        "event_id": "evt_test",
        "event_title": "Test Event",
        "amount": amount,
        "currency": "NZD",
        "reason": "Flu — doctor's note attached.",
        "status": status,
        "created_at": utc_now().isoformat(),
    })


# --- tests -----------------------------------------------------------------

def test_pool_drain_stamped_on_approval_non_destination():
    """$30 ticket → buyer paid $32.15. Approved → claim+booking should stamp
    pool_drain=$2.15 and face_value_loss=$30. No reverse_transfer in Stripe call."""
    async def run():
        booking_id = f"bk_{uuid.uuid4().hex[:10]}"
        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        try:
            await _seed_booking(booking_id, amount=32.15, face_value=30.0, destination=False)
            booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
            await _seed_claim(claim_id, booking_id, booking["user_id"], amount=32.15)

            # Stub Stripe so we can inspect the kwargs.
            captured = {}

            def fake_refund_create(**kwargs):
                captured.update(kwargs)
                return {"id": "re_test_abc"}

            with patch.object(tp, "_STRIPE", True), \
                 patch.object(tp, "_stripe", MagicMock(api_key="sk_test", Refund=MagicMock(create=fake_refund_create))), \
                 patch.dict(os.environ, {"STRIPE_API_KEY": "sk_test"}):
                from routers.ticket_protection import approve_claim, DecisionIn
                resp = await approve_claim(
                    claim_id,
                    DecisionIn(admin_note=None),
                    user={"user_id": "admin_x", "role": "admin"},
                )

            assert resp["ok"] is True
            assert resp["amount_refunded"] == 32.15
            assert resp["pool_drain"] == 2.15
            assert resp["face_value_loss"] == 30.0
            assert resp["stripe_destination_charge"] is False
            assert resp["stripe_refund_id"] == "re_test_abc"

            # Stripe should NOT have been called with reverse_transfer.
            assert "reverse_transfer" not in captured
            assert "refund_application_fee" not in captured
            assert captured["amount"] == 3215  # cents
            assert captured["metadata"]["pool_drain"] == "2.15"
            assert captured["metadata"]["face_value_loss"] == "30.00"

            claim_row = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
            assert claim_row["status"] == "approved"
            assert claim_row["pool_drain"] == 2.15
            assert claim_row["face_value_loss"] == 30.0
            assert claim_row["stripe_destination_charge"] is False

            booking_row = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
            assert booking_row["status"] == "refunded"
            assert booking_row["protection_pool_drain"] == 2.15
            assert booking_row["protection_face_value_loss"] == 30.0
        finally:
            await db.protection_claims.delete_many({"booking_id": booking_id})
            await db.bookings.delete_one({"booking_id": booking_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_destination_charge_refund_sets_reverse_transfer():
    """Connect destination charge → refund must use reverse_transfer +
    refund_application_fee so face_value is clawed back from the connected
    account and the platform fee returns to the master account."""
    async def run():
        booking_id = f"bk_{uuid.uuid4().hex[:10]}"
        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        try:
            await _seed_booking(booking_id, amount=107.45, face_value=100.0, destination=True)
            booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
            await _seed_claim(claim_id, booking_id, booking["user_id"], amount=107.45)

            captured = {}

            def fake_refund_create(**kwargs):
                captured.update(kwargs)
                return {"id": "re_test_dest"}

            with patch.object(tp, "_STRIPE", True), \
                 patch.object(tp, "_stripe", MagicMock(api_key="sk_test", Refund=MagicMock(create=fake_refund_create))), \
                 patch.dict(os.environ, {"STRIPE_API_KEY": "sk_test"}):
                from routers.ticket_protection import approve_claim, DecisionIn
                resp = await approve_claim(
                    claim_id,
                    DecisionIn(admin_note="Approved — doctor's note verified."),
                    user={"user_id": "admin_x", "role": "admin"},
                )

            assert resp["ok"] is True
            assert resp["stripe_destination_charge"] is True
            assert resp["pool_drain"] == 7.45
            assert resp["face_value_loss"] == 100.0

            # Critical: destination-charge refunds MUST set both flags.
            assert captured["reverse_transfer"] is True
            assert captured["refund_application_fee"] is True
            assert captured["amount"] == 10745
        finally:
            await db.protection_claims.delete_many({"booking_id": booking_id})
            await db.bookings.delete_one({"booking_id": booking_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_admin_stats_uses_pool_drain_not_full_amount():
    """Stats must report pool_drain as the pool outflow, NOT the full
    booking amount. Separately surface gross_refunded for the full picture."""
    async def run():
        # Seed two approved claims:
        #  - one with pool_drain stamped (new approval)
        #  - one without pool_drain (legacy) — must derive from booking
        bk1 = f"bk_{uuid.uuid4().hex[:10]}"
        bk2 = f"bk_{uuid.uuid4().hex[:10]}"
        clm1 = f"clm_{uuid.uuid4().hex[:12]}"
        clm2 = f"clm_{uuid.uuid4().hex[:12]}"
        now = utc_now().isoformat()
        try:
            # Capture baseline so we can isolate our 2-claim delta from any
            # pre-existing approved claims sitting in the shared test DB.
            baseline = await tp.admin_protection_stats(user={"role": "admin", "user_id": "admin_x"})
            base_pool = baseline["claims_paid_lifetime"]
            base_gross = baseline["gross_refunded_lifetime"]

            # Booking 1: amount=32.15, face=30 → pool_drain=2.15 (stamped)
            await db.bookings.insert_one({
                "booking_id": bk1, "user_id": "u1", "amount": 32.15,
                "face_value": 30.0, "protection_opted": True,
                "protection_amount": 1.95, "status": "refunded",
                "currency": "NZD", "created_at": now,
            })
            await db.protection_claims.insert_one({
                "claim_id": clm1, "booking_id": bk1, "user_id": "u1",
                "amount": 32.15, "refund_amount": 32.15,
                "pool_drain": 2.15, "face_value_loss": 30.0,
                "status": "approved", "decided_at": now, "created_at": now,
            })
            # Booking 2: amount=107.45, face=100 → pool_drain=7.45 (legacy)
            await db.bookings.insert_one({
                "booking_id": bk2, "user_id": "u2", "amount": 107.45,
                "face_value": 100.0, "protection_opted": True,
                "protection_amount": 6.5, "status": "refunded",
                "currency": "NZD", "created_at": now,
            })
            await db.protection_claims.insert_one({
                "claim_id": clm2, "booking_id": bk2, "user_id": "u2",
                "amount": 107.45,  # legacy: no pool_drain field
                "status": "approved", "decided_at": now, "created_at": now,
            })

            stats = await tp.admin_protection_stats(user={"role": "admin", "user_id": "admin_x"})

            # Delta from our 2 new approved claims:
            # Pool outflow = 2.15 + 7.45 = 9.60
            # NOT 32.15 + 107.45 = 139.60 (that would double-count org's losses)
            pool_delta = round(stats["claims_paid_lifetime"] - base_pool, 2)
            gross_delta = round(stats["gross_refunded_lifetime"] - base_gross, 2)
            assert pool_delta == 9.60, f"pool delta got {pool_delta}"
            assert gross_delta == 139.60, f"gross delta got {gross_delta}"
        finally:
            await db.protection_claims.delete_many({"claim_id": {"$in": [clm1, clm2]}})
            await db.bookings.delete_many({"booking_id": {"$in": [bk1, bk2]}})

    asyncio.get_event_loop().run_until_complete(run())


def test_already_refunded_booking_is_idempotent():
    """Re-approving a claim where the booking is already refunded should
    be a no-op (no second Stripe call, no exception)."""
    async def run():
        booking_id = f"bk_{uuid.uuid4().hex[:10]}"
        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        try:
            await _seed_booking(booking_id, amount=32.15, face_value=30.0, status="refunded")
            await db.bookings.update_one(
                {"booking_id": booking_id},
                {"$set": {
                    "amount_refunded": 32.15,
                    "stripe_refund_id": "re_pre_existing",
                }},
            )
            booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
            await _seed_claim(claim_id, booking_id, booking["user_id"], amount=32.15)

            stripe_calls = {"count": 0}

            def fake_refund_create(**kwargs):
                stripe_calls["count"] += 1
                return {"id": "re_should_not_happen"}

            with patch.object(tp, "_STRIPE", True), \
                 patch.object(tp, "_stripe", MagicMock(api_key="sk_test", Refund=MagicMock(create=fake_refund_create))), \
                 patch.dict(os.environ, {"STRIPE_API_KEY": "sk_test"}):
                from routers.ticket_protection import approve_claim, DecisionIn
                resp = await approve_claim(
                    claim_id,
                    DecisionIn(admin_note=None),
                    user={"user_id": "admin_x", "role": "admin"},
                )

            assert resp["already_refunded"] is True
            assert stripe_calls["count"] == 0  # NEVER call Stripe again
        finally:
            await db.protection_claims.delete_many({"booking_id": booking_id})
            await db.bookings.delete_one({"booking_id": booking_id})

    asyncio.get_event_loop().run_until_complete(run())
