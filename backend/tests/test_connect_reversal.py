"""Regression for refund-aware transfer reversal logic.

Same pattern as the payout-engine tests — never contacts Stripe, just
asserts on the skip branches that exercise the eligibility logic.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from connect_payouts_engine import reverse_transfer_for_refund  # noqa: E402


def test_reverse_transfer_branches():
    """Cover all skip paths in one event-loop to avoid motor reuse issues."""
    booking_no_event = {"booking_id": "bkg_noevt", "face_value": 20}
    booking_event_unpaid = {"booking_id": "bkg_unpaid", "event_id": f"evt_unpaid_{uuid.uuid4().hex[:6]}", "face_value": 20}
    booking_no_transfer = {"booking_id": "bkg_notran", "event_id": f"evt_notran_{uuid.uuid4().hex[:6]}", "face_value": 20}
    booking_already_rev = {"booking_id": "bkg_rev_{}".format(uuid.uuid4().hex[:6]), "event_id": f"evt_rev_{uuid.uuid4().hex[:6]}", "face_value": 20}
    booking_zero_face = {"booking_id": "bkg_zero_{}".format(uuid.uuid4().hex[:6]), "event_id": f"evt_zero_{uuid.uuid4().hex[:6]}", "face_value": 0}

    async def _run():
        await db.events.insert_many([
            # event_unpaid → exists but has no payout_status
            {"event_id": booking_event_unpaid["event_id"], "title": "X", "status": "approved"},
            # event_notran → marked paid but missing transfer_id (defensive coverage)
            {"event_id": booking_no_transfer["event_id"], "title": "X", "status": "approved", "payout_status": "paid"},
            # event_rev → paid + transfer_id, will be hit by "already reversed" check
            {"event_id": booking_already_rev["event_id"], "title": "X", "status": "approved",
             "payout_status": "paid", "payout_transfer_id": "tr_test_reversed"},
            # event_zero → paid + transfer_id; booking has zero face
            {"event_id": booking_zero_face["event_id"], "title": "X", "status": "approved",
             "payout_status": "paid", "payout_transfer_id": "tr_test_zero"},
        ])
        await db.connect_payouts.insert_one({
            "payout_id": "rev_existing_{}".format(uuid.uuid4().hex[:6]),
            "stripe_reversal_id": "trr_existing",
            "reversal_for_booking_id": booking_already_rev["booking_id"],
            "status": "reversed",
        })
        try:
            r1 = await reverse_transfer_for_refund(db, booking_no_event)
            assert r1["status"] == "skipped" and "missing" in r1["reason"]

            r2 = await reverse_transfer_for_refund(db, booking_event_unpaid)
            assert r2["status"] == "skipped" and "not paid out" in r2["reason"]

            r3 = await reverse_transfer_for_refund(db, booking_no_transfer)
            assert r3["status"] == "skipped" and "no transfer" in r3["reason"]

            r4 = await reverse_transfer_for_refund(db, booking_already_rev)
            assert r4["status"] == "skipped" and r4["reason"] == "already reversed"
            assert r4["reversal_id"] == "trr_existing"

            r5 = await reverse_transfer_for_refund(db, booking_zero_face)
            assert r5["status"] == "skipped" and "refundable" in r5["reason"]
        finally:
            await db.events.delete_many({"event_id": {"$in": [
                booking_event_unpaid["event_id"], booking_no_transfer["event_id"],
                booking_already_rev["event_id"], booking_zero_face["event_id"],
            ]}})
            await db.connect_payouts.delete_many({"reversal_for_booking_id": booking_already_rev["booking_id"]})

    asyncio.run(_run())
