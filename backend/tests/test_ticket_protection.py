"""Ticket Protection — pricing + claim lifecycle."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers.ticket_protection import compute_protection_amount, TICKET_PROTECTION_PCT  # noqa: E402


def test_protection_amount_at_default_rate():
    # Default 6.5% → $30 → $1.95
    assert compute_protection_amount(30.0) == 1.95
    assert compute_protection_amount(100.0) == 6.5
    assert compute_protection_amount(0) == 0
    assert compute_protection_amount(-5) == 0


def test_protection_rate_is_6_5_percent():
    assert abs(TICKET_PROTECTION_PCT - 0.065) < 1e-6


async def test_claim_lifecycle_via_collection():
    """Insert a protected booking → file a claim → assert one pending claim row."""
    booking_id = f"bk_{uuid.uuid4().hex[:10]}"
    user_id = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await db.bookings.insert_one({
            "booking_id": booking_id,
            "user_id": user_id,
            "user_email": "test@example.com",
            "event_id": "evt_test",
            "event_title": "Test Event",
            "status": "paid",
            "amount": 31.95,
            "protection_opted": True,
            "protection_amount": 1.95,
            "currency": "NZD",
        })
        # Simulate filing a claim directly via the collection (the API
        # uses get_current_user; testing the persistence rule is enough
        # here — the HTTP layer is exercised separately in iteration_*).
        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        await db.protection_claims.insert_one({
            "claim_id": claim_id,
            "booking_id": booking_id,
            "user_id": user_id,
            "event_id": "evt_test",
            "reason": "Came down with the flu — doctor's note attached.",
            "status": "pending",
            "created_at": utc_now().isoformat(),
        })
        cnt = await db.protection_claims.count_documents({"booking_id": booking_id})
        assert cnt == 1
        row = await db.protection_claims.find_one({"booking_id": booking_id}, {"_id": 0})
        assert row["status"] == "pending"
        assert row["reason"].startswith("Came down")
    finally:
        await db.protection_claims.delete_many({"booking_id": booking_id})
        await db.bookings.delete_one({"booking_id": booking_id})

