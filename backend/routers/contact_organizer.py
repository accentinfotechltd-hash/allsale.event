"""Public organizer profile + contact-organizer flow.

Visitors can:
  - GET /organizers/<organizer_id>           → public profile + list of upcoming events
  - POST /organizers/<organizer_id>/contact  → send a message (stored + emailed)

Organizers can:
  - GET /organizer/messages                  → inbox of received messages
  - POST /organizer/messages/<id>/read       → mark read/unread
  - DELETE /organizer/messages/<id>          → delete a message
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import db, get_current_user, utc_now, event_to_public
from emails import send_template_fireforget

router = APIRouter(tags=["contact-organizer"])


# ---------- Public organizer profile ----------

@router.get("/organizers/{organizer_id}")
async def public_organizer_profile(organizer_id: str):
    """Return the organizer's public profile + their upcoming approved events.

    Strips PII (email, phone, password). Used by the `/organizer/<id>` page
    so visitors can browse everything a given organizer is running and click
    "Contact" to reach them.
    """
    user = await db.users.find_one(
        {"user_id": organizer_id, "role": "organizer"},
        {"_id": 0, "user_id": 1, "name": 1, "picture": 1, "bio": 1, "created_at": 1},
    )
    if not user:
        raise HTTPException(status_code=404, detail="Organizer not found")

    now_iso = utc_now().isoformat()
    events_cursor = db.events.find(
        {
            "organizer_id": organizer_id,
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": now_iso},
        },
        {"_id": 0},
    ).sort("date", 1).limit(20)
    events = [event_to_public(e) async for e in events_cursor]

    # Total events ever hosted (for the "X events hosted" trust signal).
    total_events = await db.events.count_documents(
        {"organizer_id": organizer_id, "status": {"$in": ["approved", "published"]}},
    )

    return {
        "organizer": {
            **user,
            "total_events": total_events,
            "joined_at": user.get("created_at"),
        },
        "upcoming_events": events,
    }


# ---------- Public contact-organizer submission ----------

class ContactOrganizerIn(BaseModel):
    from_name: str = Field(..., min_length=1, max_length=120)
    from_email: EmailStr
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=4000)
    event_id: Optional[str] = None  # optional — pre-filled when contacting from an event page


@router.post("/organizers/{organizer_id}/contact")
async def contact_organizer(
    organizer_id: str,
    payload: ContactOrganizerIn,
    request: Request,
):
    """Store a contact message in the organizer's inbox + email them.

    Open to anonymous visitors — we capture `from_name` and `from_email` on
    the form itself rather than requiring login. Light rate limiting is
    handled by tracking the IP in the message doc so admin can spot abuse
    via the existing email-logs panel if needed.
    """
    organizer = await db.users.find_one(
        {"user_id": organizer_id, "role": "organizer"}, {"_id": 0},
    )
    if not organizer:
        raise HTTPException(status_code=404, detail="Organizer not found")

    event = None
    if payload.event_id:
        event = await db.events.find_one(
            {"event_id": payload.event_id, "organizer_id": organizer_id},
            {"_id": 0, "event_id": 1, "title": 1, "date": 1, "venue": 1},
        )
        # We DON'T 404 on mismatch — just drop the event link so a forged
        # event_id can't be used to enumerate other organizers' events.
        if not event:
            payload.event_id = None

    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    msg = {
        "message_id": msg_id,
        "organizer_id": organizer_id,
        "from_name": payload.from_name.strip(),
        "from_email": payload.from_email.lower().strip(),
        "subject": payload.subject.strip(),
        "message": payload.message.strip(),
        "event_id": payload.event_id,
        "event_title": (event or {}).get("title") if event else None,
        "read": False,
        "created_at": utc_now().isoformat(),
        # Best-effort IP capture for abuse triage (works behind Railway / Vercel).
        "from_ip": (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else None)
        ),
    }
    await db.organizer_messages.insert_one(msg)

    # Notify the organizer by email. Best-effort — message is persisted
    # whether or not the email goes out.
    try:
        send_template_fireforget(
            "organizer_contact_message",
            organizer["email"],
            {
                "organizer_name": organizer.get("name") or "there",
                "from_name": msg["from_name"],
                "from_email": msg["from_email"],
                "subject": msg["subject"],
                "message_preview": msg["message"][:500],
                "event_title": msg["event_title"],
                "reply_url": f"mailto:{msg['from_email']}?subject={('Re: ' + msg['subject'])[:120]}",
            },
            db,
        )
    except Exception:  # noqa: BLE001
        pass

    # Also notify all admins so they can see what their organizers are receiving.
    try:
        async for admin in db.users.find(
            {"role": "admin", "active": {"$ne": False}},
            {"_id": 0, "email": 1, "name": 1},
        ):
            if not admin.get("email"):
                continue
            send_template_fireforget(
                "admin_new_enquiry",
                admin["email"],
                {
                    "admin_name": admin.get("name") or "Admin",
                    "organizer_name": organizer.get("name") or "Organizer",
                    "from_name": msg["from_name"],
                    "from_email": msg["from_email"],
                    "subject": msg["subject"],
                    "message_preview": msg["message"][:500],
                    "event_title": msg.get("event_title"),
                },
                db,
            )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "message_id": msg_id,
        "message": "Your message has been sent. The organizer will reply to your email address directly.",
    }


# ---------- Organizer inbox ----------

@router.get("/organizer/messages")
async def organizer_inbox(user: dict = Depends(get_current_user)):
    """List contact messages received by the signed-in organizer.

    Most recent first. Includes an `unread_count` so the dashboard can render
    a notification badge.
    """
    if user.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Organizers only")
    messages = []
    async for m in db.organizer_messages.find(
        {"organizer_id": user["user_id"]}, {"_id": 0},
    ).sort("created_at", -1).limit(200):
        messages.append(m)
    unread = sum(1 for m in messages if not m.get("read"))
    return {"messages": messages, "unread_count": unread, "total": len(messages)}


class _ReadToggleIn(BaseModel):
    read: bool = True


@router.post("/organizer/messages/{message_id}/read")
async def mark_organizer_message_read(
    message_id: str,
    payload: _ReadToggleIn,
    user: dict = Depends(get_current_user),
):
    res = await db.organizer_messages.update_one(
        {"message_id": message_id, "organizer_id": user["user_id"]},
        {"$set": {"read": bool(payload.read), "read_at": utc_now().isoformat() if payload.read else None}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@router.delete("/organizer/messages/{message_id}")
async def delete_organizer_message(message_id: str, user: dict = Depends(get_current_user)):
    res = await db.organizer_messages.delete_one(
        {"message_id": message_id, "organizer_id": user["user_id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}
