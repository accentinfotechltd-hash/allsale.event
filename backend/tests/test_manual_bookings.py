"""Manual bookings — box office / cash / offline-card sales.

Covers:
  • Paid mode → booking status="paid" + qr_code + confirmation email fires.
  • Hold mode → status="manual_hold" + hold_expires_at set 24h out, seats
    marked held, NO qr_code generated yet.
  • Confirm-a-hold flips status → paid, stamps qr_code, releases held seats
    into booked.
  • Cancel-a-hold releases seats and marks the booking cancelled.
  • Auth: attendee → 403, other organizer's event → 403, admin → OK.
  • Tier-based events: capacity check rejects over-selling.
  • Seat-map events: DuplicateKeyError → 409 conflict.
  • Payment method + payer identity are stamped on the booking.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import manual_bookings as mb  # noqa: E402


async def _mk_user(role="organizer", **extra):
    uid = f"user_test_{uuid.uuid4().hex[:8]}"
    doc = {
        "user_id": uid,
        "email": f"{uid}@example.com",
        "name": "Test User",
        "phone": "+64 21 555 0000",
        "role": role,
        **extra,
    }
    await db.users.update_one({"user_id": uid}, {"$set": doc}, upsert=True)
    return doc


async def _mk_event(organizer, *, has_seatmap=False, **extra):
    eid = f"evt_test_{uuid.uuid4().hex[:10]}"
    base = {
        "event_id": eid,
        "organizer_id": organizer["user_id"],
        "organizer_name": organizer["name"],
        "title": "Manual Test Event",
        "description": "pytest",
        "category": "music",
        "venue": "Test Venue",
        "city": "Auckland",
        "country": "NZ",
        "timezone": "Pacific/Auckland",
        "date": "2027-05-15T20:00:00Z",
        "image_url": "https://example.com/x.jpg",
        "currency": "NZD",
        "status": "approved",
        "created_at": utc_now().isoformat(),
    }
    if has_seatmap:
        base.update({
            "has_seatmap": True,
            "seat_rows": 3, "seat_cols": 4,
            "seat_price": 25.0,
            "aisles": [],
            "tiers": [],
        })
    else:
        base.update({
            "has_seatmap": False,
            "tiers": [{"name": "General", "price": 50, "capacity": 20}],
        })
    base.update(extra)
    await db.events.insert_one(base)
    return base


async def _cleanup_event(event_id):
    await db.bookings.delete_many({"event_id": event_id})
    await db.seat_reservations.delete_many({"event_id": event_id})
    await db.seat_holds.delete_many({"event_id": event_id})
    await db.events.delete_one({"event_id": event_id})


async def _cleanup_user(user_id):
    await db.users.delete_one({"user_id": user_id})


# ---------------------------------------------------------------------------
# 1. Paid mode — tier event → booking paid + qr + confirmation email fires
# ---------------------------------------------------------------------------
async def test_create_manual_paid_tier_booking_fires_confirmation():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Alice Buyer", buyer_email="alice@example.com",
            payment_method="cash", mode="paid",
            tier_name="General", quantity=2,
        )
        with patch("routers.manual_bookings._send_paid_confirmation") as mock_send:
            result = await mb.create_manual_booking(event["event_id"], payload, organizer)
        assert result["status"] == "paid"
        assert result["face_value"] == 100.0
        assert result["amount_paid"] == 100.0
        assert mock_send.called

        booking = await db.bookings.find_one({"booking_id": result["booking_id"]}, {"_id": 0})
        assert booking["status"] == "paid"
        assert booking["payment_method"] == "cash"
        assert booking["manual_booking"] is True
        assert booking["created_by_user_id"] == organizer["user_id"]
        assert booking["user_email"] == "alice@example.com"
        assert booking.get("qr_code")
        assert booking.get("paid_at")
        assert booking.get("hold_expires_at") is None
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 2. Hold mode — no qr, hold_expires_at set 24h out, no email fired
# ---------------------------------------------------------------------------
async def test_create_manual_hold_stores_expiry_and_no_qr():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Bob Later", buyer_email="bob@example.com",
            payment_method="card_offline", mode="hold",
            tier_name="General", quantity=1,
        )
        with patch("routers.manual_bookings._send_paid_confirmation") as mock_send:
            result = await mb.create_manual_booking(event["event_id"], payload, organizer)
        assert result["status"] == "manual_hold"
        assert result["hold_expires_at"] is not None
        assert not mock_send.called  # holds don't fire the paid-confirmation email

        booking = await db.bookings.find_one({"booking_id": result["booking_id"]}, {"_id": 0})
        assert booking["status"] == "manual_hold"
        assert booking["payment_method"] == "card_offline"
        assert booking.get("qr_code") is None
        assert booking["hold_expires_at"] > utc_now().isoformat()
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 3. Confirm-a-hold flips manual_hold → paid, stamps qr, emails buyer.
# ---------------------------------------------------------------------------
async def test_confirm_manual_hold_flips_to_paid():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer)
    try:
        create_payload = mb.ManualBookingIn(
            buyer_name="Cindy", buyer_email="cindy@example.com",
            payment_method="cash", mode="hold",
            tier_name="General", quantity=1,
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            created = await mb.create_manual_booking(event["event_id"], create_payload, organizer)

        confirm_payload = mb.ConfirmManualIn(amount_paid=50.0, payment_method="cash")
        with patch("routers.manual_bookings._send_paid_confirmation") as mock_send:
            result = await mb.confirm_manual_booking(created["booking_id"], confirm_payload, organizer)
        assert result["status"] == "paid"
        assert mock_send.called

        booking = await db.bookings.find_one({"booking_id": created["booking_id"]}, {"_id": 0})
        assert booking["status"] == "paid"
        assert booking["qr_code"]
        assert booking["amount"] == 50.0
        assert booking["hold_expires_at"] is None
        assert booking["confirmed_by_user_id"] == organizer["user_id"]
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 4. Cancel-a-hold releases seats, marks cancelled.
# ---------------------------------------------------------------------------
async def test_cancel_manual_hold_releases_seats():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer, has_seatmap=True)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Dan", buyer_email="dan@example.com",
            payment_method="card_offline", mode="hold",
            seats=["A-1", "A-2"],
        )
        created = await mb.create_manual_booking(event["event_id"], payload, organizer)
        # Seat reservations should exist as "held"
        held = await db.seat_reservations.count_documents(
            {"event_id": event["event_id"], "booking_id": created["booking_id"], "status": "held"}
        )
        assert held == 2

        result = await mb.cancel_manual_booking(created["booking_id"], organizer)
        assert result["status"] == "cancelled"
        # Reservations must be GONE (delete_many) so the seats free up.
        remaining = await db.seat_reservations.count_documents(
            {"booking_id": created["booking_id"]}
        )
        assert remaining == 0
        booking = await db.bookings.find_one({"booking_id": created["booking_id"]}, {"_id": 0})
        assert booking["status"] == "cancelled"
        assert booking["cancelled_by_user_id"] == organizer["user_id"]
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 5. Seat-map paid mode books the seats correctly.
# ---------------------------------------------------------------------------
async def test_manual_paid_seatmap_marks_seats_booked():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer, has_seatmap=True)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Eva", buyer_email="eva@example.com",
            payment_method="cash", mode="paid",
            seats=["A-1", "A-2", "A-3"],
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            result = await mb.create_manual_booking(event["event_id"], payload, organizer)
        assert result["face_value"] == 75.0  # 3 × $25
        booked = await db.seat_reservations.count_documents(
            {"event_id": event["event_id"], "booking_id": result["booking_id"], "status": "booked"}
        )
        assert booked == 3
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 6. Seat conflict → 409.
# ---------------------------------------------------------------------------
async def test_manual_seat_conflict_returns_409():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer, has_seatmap=True)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Fran", buyer_email="fran@example.com",
            payment_method="cash", mode="paid",
            seats=["A-1"],
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            await mb.create_manual_booking(event["event_id"], payload, organizer)

        # Second booking targeting the same seat → conflict.
        payload_dup = mb.ManualBookingIn(
            buyer_name="Gus", buyer_email="gus@example.com",
            payment_method="cash", mode="paid",
            seats=["A-1"],
        )
        with pytest.raises(HTTPException) as ei:
            with patch("routers.manual_bookings._send_paid_confirmation"):
                await mb.create_manual_booking(event["event_id"], payload_dup, organizer)
        assert ei.value.status_code == 409
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 7. Tier capacity check — reject when we'd blow past capacity.
# ---------------------------------------------------------------------------
async def test_tier_capacity_check_rejects_oversell():
    organizer = await _mk_user(role="organizer")
    # Tiny tier — capacity 3.
    event = await _mk_event(
        organizer,
        tiers=[{"name": "Tiny", "price": 10, "capacity": 3}],
    )
    try:
        # Sell 2 first — OK.
        payload = mb.ManualBookingIn(
            buyer_name="Hank", buyer_email="hank@example.com",
            payment_method="cash", mode="paid",
            tier_name="Tiny", quantity=2,
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            await mb.create_manual_booking(event["event_id"], payload, organizer)
        # Attempt 2 more (would need 4, only 1 left) → 409.
        payload2 = mb.ManualBookingIn(
            buyer_name="Iris", buyer_email="iris@example.com",
            payment_method="cash", mode="paid",
            tier_name="Tiny", quantity=2,
        )
        with pytest.raises(HTTPException) as ei:
            with patch("routers.manual_bookings._send_paid_confirmation"):
                await mb.create_manual_booking(event["event_id"], payload2, organizer)
        assert ei.value.status_code == 409
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])


# ---------------------------------------------------------------------------
# 8. Auth — attendee 403, foreign organizer 403, admin OK.
# ---------------------------------------------------------------------------
async def test_attendee_gets_403():
    organizer = await _mk_user(role="organizer")
    attendee = await _mk_user(role="attendee")
    event = await _mk_event(organizer)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="X", buyer_email="x@example.com",
            payment_method="cash", mode="paid",
            tier_name="General", quantity=1,
        )
        with pytest.raises(HTTPException) as ei:
            await mb.create_manual_booking(event["event_id"], payload, attendee)
        assert ei.value.status_code == 403
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])
        await _cleanup_user(attendee["user_id"])


async def test_foreign_organizer_gets_403():
    owner = await _mk_user(role="organizer")
    intruder = await _mk_user(role="organizer")
    event = await _mk_event(owner)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="X", buyer_email="x@example.com",
            payment_method="cash", mode="paid",
            tier_name="General", quantity=1,
        )
        with pytest.raises(HTTPException) as ei:
            await mb.create_manual_booking(event["event_id"], payload, intruder)
        assert ei.value.status_code == 403
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(owner["user_id"])
        await _cleanup_user(intruder["user_id"])


async def test_admin_can_book_any_event():
    organizer = await _mk_user(role="organizer")
    admin = await _mk_user(role="admin")
    event = await _mk_event(organizer)
    try:
        payload = mb.ManualBookingIn(
            buyer_name="Admin Buy", buyer_email="ab@example.com",
            payment_method="cash", mode="paid",
            tier_name="General", quantity=1,
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            result = await mb.create_manual_booking(event["event_id"], payload, admin)
        assert result["status"] == "paid"
        booking = await db.bookings.find_one({"booking_id": result["booking_id"]}, {"_id": 0})
        assert booking["created_by_role"] == "admin"
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])
        await _cleanup_user(admin["user_id"])


# ---------------------------------------------------------------------------
# 9. List endpoint — filters + summary counts.
# ---------------------------------------------------------------------------
async def test_list_manual_bookings_endpoint():
    organizer = await _mk_user(role="organizer")
    event = await _mk_event(organizer)
    try:
        # 2 paid + 1 hold
        for i in range(2):
            payload = mb.ManualBookingIn(
                buyer_name=f"P{i}", buyer_email=f"p{i}@example.com",
                payment_method="cash", mode="paid",
                tier_name="General", quantity=1,
            )
            with patch("routers.manual_bookings._send_paid_confirmation"):
                await mb.create_manual_booking(event["event_id"], payload, organizer)
        payload = mb.ManualBookingIn(
            buyer_name="H", buyer_email="h@example.com",
            payment_method="card_offline", mode="hold",
            tier_name="General", quantity=1,
        )
        with patch("routers.manual_bookings._send_paid_confirmation"):
            await mb.create_manual_booking(event["event_id"], payload, organizer)

        result = await mb.list_manual_bookings(event["event_id"], organizer)
        assert result["ok"] is True
        assert len(result["items"]) == 3
        assert result["summary"].get("paid") == 2
        assert result["summary"].get("manual_hold") == 1
    finally:
        await _cleanup_event(event["event_id"])
        await _cleanup_user(organizer["user_id"])
