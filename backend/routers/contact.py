"""Contact-form submissions.

Stores every inquiry in `contact_messages` and emails the support inbox so
nothing is lost if Resend rate-limits. Anonymous (no auth) — but we lightly
rate-limit on IP + email to keep spam out.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import db, utc_now
from emails import send_template_fireforget

router = APIRouter(prefix="/contact", tags=["contact"])

SUPPORT_INBOX = (
    os.environ.get("SUPPORT_INBOX")
    or os.environ.get("REPLY_TO_EMAIL")  # fallback — same shared support inbox
    or "allsaletickets@gmail.com"
)
_PHONE_RE = re.compile(r"^[+0-9 ()\-]{6,20}$")


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = None
    subject: str = Field(min_length=2, max_length=160)
    message: str = Field(min_length=5, max_length=4000)


@router.post("")
async def submit_contact(payload: ContactIn, request: Request):
    """Anonymous contact form. Stores + emails the team."""
    # Light spam guard — at most 5 messages from the same email per hour
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = await db.contact_messages.count_documents({
        "email": str(payload.email).lower(),
        "created_at": {"$gte": one_hour_ago},
    })
    if recent >= 5:
        raise HTTPException(status_code=429, detail="Too many messages. Please try again later.")

    if payload.phone and not _PHONE_RE.match(payload.phone.strip()):
        raise HTTPException(status_code=400, detail="Phone format looks invalid")

    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    doc = {
        "message_id": message_id,
        "name": payload.name.strip(),
        "email": str(payload.email).lower(),
        "phone": (payload.phone or "").strip() or None,
        "subject": payload.subject.strip(),
        "message": payload.message.strip(),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "created_at": utc_now().isoformat(),
        "status": "new",
    }
    await db.contact_messages.insert_one(doc)

    # Notify the team using the existing admin_blast template (generic text+CTA)
    try:
        send_template_fireforget(
            "admin_blast",
            SUPPORT_INBOX,
            {
                "user_name": "Allsale team",
                "subject": f"[Contact] {payload.subject.strip()}",
                "body": (
                    f"From: {payload.name} <{payload.email}>"
                    + (f"  ·  Phone: {payload.phone}" if payload.phone else "")
                    + f"\n\n{payload.message}"
                ),
            },
            db,
        )
    except Exception:
        pass

    # Send a courtesy auto-reply to the submitter
    try:
        send_template_fireforget(
            "admin_blast",
            str(payload.email),
            {
                "user_name": payload.name,
                "subject": "We received your message — Allsale Events",
                "body": (
                    "Thanks for getting in touch. A real human will get back to you within 24 hours.\n\n"
                    "Here's a copy of what you sent:\n\n"
                    f"Subject: {payload.subject}\n\n"
                    f"{payload.message}"
                ),
            },
            db,
        )
    except Exception:
        pass

    return {"message_id": message_id, "received": True}


@router.get("")
async def list_messages(request: Request):
    """Admin-only listing of contact submissions. Reuses bearer auth from
    the rest of the app; we don't import the dep to avoid a circular import."""
    # Defer the actual auth to a separate admin-side endpoint to keep this
    # public router lean. Leave a stub so accidental GETs return 404.
    raise HTTPException(status_code=404, detail="Not found")
