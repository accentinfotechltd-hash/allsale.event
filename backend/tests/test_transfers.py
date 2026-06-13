"""Ticket transfers between attendees — recallable workflow."""
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


def test_ticket_transfer_full_lifecycle():
    owner_id = f"trx_own_{uuid.uuid4().hex[:8]}"
    recipient_email = f"recv_{uuid.uuid4().hex[:6]}@example.com"
    recipient_id = f"trx_rec_{uuid.uuid4().hex[:8]}"
    intruder_id = f"trx_int_{uuid.uuid4().hex[:8]}"
    organizer_id = f"trx_org_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_trx_{uuid.uuid4().hex[:8]}"
    booking_id = f"bk_trx_{uuid.uuid4().hex[:8]}"

    async def _run():
        await db.users.insert_many([
            {"user_id": owner_id, "email": f"{owner_id}@example.com",
             "role": "attendee", "name": "Sender",
             "created_at": utc_now().isoformat()},
            {"user_id": recipient_id, "email": recipient_email,
             "role": "attendee", "name": "Receiver",
             "created_at": utc_now().isoformat()},
            {"user_id": intruder_id, "email": f"{intruder_id}@example.com",
             "role": "attendee", "name": "Stranger",
             "created_at": utc_now().isoformat()},
            {"user_id": organizer_id, "email": f"{organizer_id}@example.com",
             "role": "organizer", "name": "Org",
             "created_at": utc_now().isoformat()},
        ])
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": organizer_id, "status": "approved",
            "title": "Transfer Show", "date": (utc_now() + timedelta(days=14)).isoformat(),
            "currency": "NZD",
        })
        await db.bookings.insert_one({
            "booking_id": booking_id, "event_id": event_id, "user_id": owner_id,
            "status": "paid", "amount": 25.0, "face_value": 25.0, "service_fee": 0,
            "quantity": 1, "qr_token": "original-qr",
        })

        try:
            os.environ.setdefault("JWT_SECRET", "test-secret")
            from httpx import AsyncClient, ASGITransport  # noqa: WPS433
            from server import app  # noqa: WPS433
            import jwt as _jwt  # noqa: WPS433

            def _h(uid, role="attendee", email=None):
                tok = _jwt.encode(
                    {"sub": uid, "email": email or f"{uid}@example.com", "role": role},
                    os.environ["JWT_SECRET"],
                    algorithm="HS256",
                )
                return {"Authorization": f"Bearer {tok}"}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                # 1) Create a transfer
                r = await c.post(
                    f"/api/me/bookings/{booking_id}/transfer",
                    json={"recipient_email": recipient_email, "note": "Enjoy!"},
                    headers=_h(owner_id),
                )
                assert r.status_code == 200, r.text
                tx = r.json()
                assert tx["status"] == "pending"
                transfer_id = tx["transfer_id"]

                # 2) Refuse double-pending
                r = await c.post(
                    f"/api/me/bookings/{booking_id}/transfer",
                    json={"recipient_email": recipient_email},
                    headers=_h(owner_id),
                )
                assert r.status_code == 409

                # 3) Public read works (no auth)
                r = await c.get(f"/api/transfers/{transfer_id}")
                assert r.status_code == 200
                assert r.json()["status"] == "pending"
                assert r.json()["sender_name"] == "Sender"

                # 4) Intruder can't accept
                r = await c.post(
                    f"/api/transfers/{transfer_id}/accept",
                    headers=_h(intruder_id),
                )
                assert r.status_code == 403

                # 5) Owner recalls
                r = await c.post(
                    f"/api/transfers/{transfer_id}/recall",
                    headers=_h(owner_id),
                )
                assert r.status_code == 200
                assert r.json()["status"] == "recalled"

                # 6) Booking still belongs to original owner with original QR
                bk = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
                assert bk["user_id"] == owner_id
                assert bk["qr_token"] == "original-qr"

                # 7) New transfer for the same booking is now allowed
                r = await c.post(
                    f"/api/me/bookings/{booking_id}/transfer",
                    json={"recipient_email": recipient_email},
                    headers=_h(owner_id),
                )
                assert r.status_code == 200
                tx2_id = r.json()["transfer_id"]

                # 8) Recipient accepts — booking re-assigned + QR rotated
                r = await c.post(
                    f"/api/transfers/{tx2_id}/accept",
                    headers=_h(recipient_id, email=recipient_email),
                )
                assert r.status_code == 200, r.text
                bk = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
                assert bk["user_id"] == recipient_id
                assert bk["qr_token"] != "original-qr"
                assert bk["transferred_from"] == owner_id

                # 9) Second accept is rejected (already accepted)
                r = await c.post(
                    f"/api/transfers/{tx2_id}/accept",
                    headers=_h(recipient_id, email=recipient_email),
                )
                assert r.status_code == 400

                # 10) my-transfers listing
                r = await c.get("/api/me/transfers", headers=_h(owner_id))
                assert r.status_code == 200
                body = r.json()
                assert len(body["outgoing"]) == 2  # recalled + accepted

                r = await c.get("/api/me/transfers", headers=_h(recipient_id, email=recipient_email))
                assert r.status_code == 200
                assert len(r.json()["incoming"]) == 2  # both transfers were addressed to this email
        finally:
            await db.users.delete_many({"user_id": {"$in": [
                owner_id, recipient_id, intruder_id, organizer_id,
            ]}})
            await db.events.delete_one({"event_id": event_id})
            await db.bookings.delete_one({"booking_id": booking_id})
            await db.booking_transfers.delete_many({"booking_id": booking_id})
            await db.booking_transfer_audit.delete_many({"booking_id": booking_id})

    asyncio.run(_run())
