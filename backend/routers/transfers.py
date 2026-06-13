"""Ticket transfers between attendees.

Recallable workflow:
  1. Owner sends a transfer to a recipient email.
  2. We invalidate the old QR code by rotating the booking's `qr_token`
     and emailing a claim link to the recipient.
  3. Recipient either accepts (booking re-assigned, fresh QR) or rejects
     (transfer cancelled, owner keeps original QR).
  4. Owner may recall at any time before acceptance.

State machine on `booking_transfers` collection:
  pending  → accepted | rejected | recalled | expired
  Expiry: 7 days. The scheduler can later sweep stale transfers.

Endpoints:
  POST   /api/me/bookings/{booking_id}/transfer    — owner creates transfer
  POST   /api/transfers/{transfer_id}/accept        — recipient (auth required) accepts
  POST   /api/transfers/{transfer_id}/reject        — recipient declines
  POST   /api/transfers/{transfer_id}/recall        — owner cancels
  GET    /api/transfers/{transfer_id}               — anyone with the link (recipient view)
  GET    /api/me/transfers                          — auth: my outgoing + incoming
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transfers"])

TRANSFER_EXPIRY_HOURS = 24 * 7  # 7 days


class TransferIn(BaseModel):
    recipient_email: EmailStr
    note: str | None = None


def _new_qr_token() -> str:
    return uuid.uuid4().hex


async def _email_recipient(transfer: dict, owner: dict, booking: dict, event: dict) -> None:
    """Send the recipient a claim link."""
    from emails import send_template_fireforget  # local import — avoid cycles
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    claim_url = f"{origin}/transfer/{transfer['transfer_id']}"
    try:
        send_template_fireforget(
            "ticket_transfer_offer",
            transfer["recipient_email"],
            {
                "sender_name": owner.get("name") or "An Allsale member",
                "event_title": event.get("title", "an event"),
                "event_date_iso": event.get("date"),
                "venue": f"{event.get('venue','')}, {event.get('city','')}",
                "claim_url": claim_url,
                "expires_at": transfer["expires_at"],
                "note": transfer.get("note") or "",
            },
            db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[transfer] email failed for {transfer['recipient_email']}: {exc}")


@router.post("/me/bookings/{booking_id}/transfer")
async def create_transfer(booking_id: str, payload: TransferIn, user: dict = Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.get("status") != "paid":
        raise HTTPException(status_code=400, detail="Only paid bookings can be transferred.")

    event = await db.events.find_one({"event_id": booking.get("event_id")}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    recipient_email = payload.recipient_email.strip().lower()
    if recipient_email == (user.get("email") or "").strip().lower():
        raise HTTPException(status_code=400, detail="You can't transfer a ticket to yourself.")

    # Block double-pending: refuse if there's already a pending transfer.
    existing = await db.booking_transfers.find_one(
        {"booking_id": booking_id, "status": "pending"},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="There's already a pending transfer for this ticket — recall it first.",
        )

    transfer_id = f"tx_{uuid.uuid4().hex[:14]}"
    expires_at = (utc_now() + timedelta(hours=TRANSFER_EXPIRY_HOURS)).isoformat()
    transfer = {
        "transfer_id": transfer_id,
        "booking_id": booking_id,
        "event_id": booking["event_id"],
        "sender_user_id": user["user_id"],
        "sender_email": user.get("email"),
        "recipient_email": recipient_email,
        "recipient_user_id": None,
        "status": "pending",
        "note": (payload.note or "").strip()[:500] or None,
        "expires_at": expires_at,
        "created_at": utc_now().isoformat(),
    }
    await db.booking_transfers.insert_one(transfer)

    # Don't invalidate the owner's QR yet — that happens on acceptance.
    # This preserves the "recallable" UX: the owner can keep scanning at
    # the door if they recall.

    owner = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0}) or user
    await _email_recipient(transfer, owner, booking, event)

    transfer.pop("_id", None)
    return transfer


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str):
    """Public read so the recipient (who may not yet be logged in) can
    see what they're being offered. Returns sanitized info — no QR."""
    t = await db.booking_transfers.find_one({"transfer_id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    booking = await db.bookings.find_one({"booking_id": t["booking_id"]}, {
        "_id": 0, "tier_name": 1, "quantity": 1, "seats": 1, "currency": 1, "amount": 1,
    }) or {}
    event = await db.events.find_one({"event_id": t["event_id"]}, {
        "_id": 0, "title": 1, "date": 1, "venue": 1, "city": 1, "image_url": 1,
    }) or {}
    sender = await db.users.find_one({"user_id": t["sender_user_id"]}, {
        "_id": 0, "name": 1,
    }) or {}
    return {
        "transfer_id": t["transfer_id"],
        "status": t["status"],
        "recipient_email": t["recipient_email"],
        "expires_at": t["expires_at"],
        "note": t.get("note"),
        "sender_name": sender.get("name") or "An Allsale member",
        "booking": booking,
        "event": event,
    }


@router.post("/transfers/{transfer_id}/accept")
async def accept_transfer(transfer_id: str, user: dict = Depends(get_current_user)):
    t = await db.booking_transfers.find_one({"transfer_id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if t["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Transfer is already {t['status']}.")
    if utc_now().isoformat() > t["expires_at"]:
        await db.booking_transfers.update_one(
            {"transfer_id": transfer_id},
            {"$set": {"status": "expired", "expired_at": utc_now().isoformat()}},
        )
        raise HTTPException(status_code=400, detail="This transfer has expired.")
    if (user.get("email") or "").strip().lower() != t["recipient_email"].strip().lower():
        raise HTTPException(
            status_code=403,
            detail=f"This transfer was sent to {t['recipient_email']} — sign in with that email to accept.",
        )

    # Rotate QR + re-assign booking to the new owner.
    new_qr_token = _new_qr_token()
    now_iso = utc_now().isoformat()
    await db.bookings.update_one(
        {"booking_id": t["booking_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "user_email": user.get("email"),
            "qr_token": new_qr_token,
            "transferred_at": now_iso,
            "transferred_from": t["sender_user_id"],
        }},
    )
    await db.booking_transfers.update_one(
        {"transfer_id": transfer_id},
        {"$set": {
            "status": "accepted",
            "recipient_user_id": user["user_id"],
            "accepted_at": now_iso,
        }},
    )
    # Audit row for compliance + customer support
    await db.booking_transfer_audit.insert_one({
        "audit_id": f"tax_{uuid.uuid4().hex[:12]}",
        "transfer_id": transfer_id,
        "booking_id": t["booking_id"],
        "from_user_id": t["sender_user_id"],
        "to_user_id": user["user_id"],
        "to_email": user.get("email"),
        "at": now_iso,
    })
    return {"ok": True, "booking_id": t["booking_id"], "status": "accepted"}


@router.post("/transfers/{transfer_id}/reject")
async def reject_transfer(transfer_id: str, user: dict = Depends(get_current_user)):
    t = await db.booking_transfers.find_one({"transfer_id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if t["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Transfer is already {t['status']}.")
    if (user.get("email") or "").strip().lower() != t["recipient_email"].strip().lower():
        raise HTTPException(status_code=403, detail="Not the intended recipient.")

    await db.booking_transfers.update_one(
        {"transfer_id": transfer_id},
        {"$set": {"status": "rejected", "rejected_at": utc_now().isoformat()}},
    )
    return {"ok": True, "status": "rejected"}


@router.post("/transfers/{transfer_id}/recall")
async def recall_transfer(transfer_id: str, user: dict = Depends(get_current_user)):
    t = await db.booking_transfers.find_one({"transfer_id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if t["sender_user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only the sender can recall.")
    if t["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Transfer is already {t['status']} — can't recall.")
    await db.booking_transfers.update_one(
        {"transfer_id": transfer_id},
        {"$set": {"status": "recalled", "recalled_at": utc_now().isoformat()}},
    )
    return {"ok": True, "status": "recalled"}


@router.get("/me/transfers")
async def my_transfers(user: dict = Depends(get_current_user)):
    """Return outgoing (I sent) + incoming (sent to my email) transfers."""
    outgoing = []
    async for t in db.booking_transfers.find(
        {"sender_user_id": user["user_id"]}, {"_id": 0},
    ).sort("created_at", -1):
        outgoing.append(t)

    incoming = []
    if user.get("email"):
        async for t in db.booking_transfers.find(
            {"recipient_email": (user["email"] or "").strip().lower()}, {"_id": 0},
        ).sort("created_at", -1):
            incoming.append(t)

    return {"outgoing": outgoing, "incoming": incoming}
