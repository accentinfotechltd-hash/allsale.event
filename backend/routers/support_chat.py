"""Live support chat — lightweight, persistent, no websockets needed.

Architecture:
  • Visitors get a `session_id` stored in localStorage; they don't need to
    sign in to start a conversation. Authenticated users have their
    `user_id` attached server-side so admins know who they're talking to.
  • Visitors poll `GET /support/chat/:session_id` every few seconds for
    new admin replies. Bandwidth is tiny because the response is just
    JSON deltas (sorted by `created_at`).
  • Admins see pending sessions in `GET /admin/support/sessions` ordered
    by `last_visitor_msg_at desc` so the busiest threads bubble to top.

Why not websockets? They'd add infra cost, a connection-management layer
on Railway, and aren't justified for the volume an early-stage ticketing
platform sees. Polling every 5–6s on the open chat panel is plenty
responsive and gracefully degrades on flaky mobile networks.
"""
from __future__ import annotations

import os
import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support_chat"])

# Throttle the "new visitor message" admin email so a rapid-fire visitor
# (sending 6 quick lines) only produces ONE email per 5-minute window.
NEW_MSG_EMAIL_THROTTLE_MIN = int(os.environ.get("SUPPORT_EMAIL_THROTTLE_MIN", "5"))

MAX_MSG_LEN = 2000
MAX_NAME_LEN = 80


class SupportMessageIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=MAX_MSG_LEN)
    name: Optional[str] = Field(default=None, max_length=MAX_NAME_LEN)
    email: Optional[str] = Field(default=None, max_length=120)


class AdminReplyIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=MAX_MSG_LEN)


def _try_get_user(request: Request) -> Optional[dict]:
    """Best-effort current-user lookup — chat works for anon visitors too."""
    # We can't call get_current_user directly (it raises on missing auth),
    # so we just check the header presence and let the upstream code grab
    # user info from the bearer-token cache if it's there.
    return getattr(request.state, "_cached_user", None)


async def _maybe_notify_admins(session_id: str, visitor_name: str, preview: str) -> None:
    """Fire-and-forget admin alert email when a new visitor message lands.

    Throttled per session so a chatty visitor doesn't blast the inbox.
    Stores the last-notified timestamp on the session doc.
    """
    # Throttle check — bail if we emailed about this session recently.
    session_doc = await db.support_chats.find_one(
        {"session_id": session_id},
        {"_id": 0, "last_admin_notified_at": 1},
    ) or {}
    last_iso = session_doc.get("last_admin_notified_at")
    if last_iso:
        try:
            last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
            now = utc_now()
            if (now - last_dt).total_seconds() < NEW_MSG_EMAIL_THROTTLE_MIN * 60:
                return
        except Exception:  # noqa: BLE001
            pass  # malformed timestamp — proceed and overwrite below

    try:
        from emails import send_template_fireforget
    except Exception:  # noqa: BLE001
        return  # emails module not configured — silently skip

    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    admin_url = f"{origin}/admin"

    async for admin in db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}):
        try:
            send_template_fireforget(
                to=admin["email"],
                subject=f"New support chat from {visitor_name}",
                template="generic",
                params={
                    "title": "New support chat 💬",
                    "preheader": f"{visitor_name}: {preview[:80]}",
                    "body_html": (
                        f"<p><strong>{visitor_name}</strong> just started (or continued) a live chat:</p>"
                        f"<blockquote style=\"border-left:3px solid #F08A2A;padding-left:12px;color:#555;\">{preview}</blockquote>"
                        f"<p><a href=\"{admin_url}\" style=\"display:inline-block;padding:10px 20px;background:#F08A2A;color:#0F2A3A;text-decoration:none;border-radius:8px;\">Open admin → Live chat</a></p>"
                    ),
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to email admin %s about new chat", admin.get("email"))

    # Mark notified
    await db.support_chats.update_one(
        {"session_id": session_id},
        {"$set": {"last_admin_notified_at": utc_now().isoformat()}},
    )


@router.post("/support/chat/messages")
async def post_visitor_message(payload: SupportMessageIn, request: Request):
    """Visitor sends a message. Creates the session on first hit."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message can't be empty")

    user = _try_get_user(request)
    user_id = user["user_id"] if user else None
    user_email = (user.get("email") if user else None) or (payload.email or "").strip().lower() or None

    now_iso = utc_now().isoformat()

    # Upsert the session document so the admin inbox always sees the latest meta.
    session_update = {
        "$set": {
            "session_id": payload.session_id,
            "last_visitor_msg_at": now_iso,
            "last_msg_at": now_iso,
            "user_id": user_id,
            "visitor_name": (payload.name or (user.get("name") if user else None) or "Anonymous")[:MAX_NAME_LEN],
            "visitor_email": user_email,
            "status": "open",
        },
        "$setOnInsert": {"created_at": now_iso},
        "$inc": {"unread_admin_count": 1},
    }
    await db.support_chats.update_one(
        {"session_id": payload.session_id},
        session_update,
        upsert=True,
    )

    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "session_id": payload.session_id,
        "sender": "visitor",
        "user_id": user_id,
        "text": text,
        "created_at": now_iso,
    }
    await db.support_messages.insert_one(msg)

    # Background email to admins (throttled). asyncio.create_task keeps the
    # response snappy — the user shouldn't wait for SMTP.
    visitor_name = (payload.name or (user.get("name") if user else None) or "Anonymous").strip() or "Anonymous"
    asyncio.create_task(_maybe_notify_admins(payload.session_id, visitor_name, text))

    msg.pop("_id", None)
    return msg


class TypingIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)


@router.post("/support/chat/typing")
async def visitor_typing(payload: TypingIn):
    """Visitor signals 'I'm typing'. Admin sees the indicator within ~2s on
    their next poll. We just write a timestamp on the session doc; the
    admin's GET endpoint compares it to `now` to decide whether to render
    a typing bubble."""
    await db.support_chats.update_one(
        {"session_id": payload.session_id},
        {"$set": {"visitor_typing_at": utc_now().isoformat()}},
        upsert=True,
    )
    return {"ok": True}


@router.post("/admin/support/typing")
async def admin_typing(payload: TypingIn, user: dict = Depends(get_current_user)):
    """Admin equivalent — the visitor sees 'Allsale is typing…' bubble."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    await db.support_chats.update_one(
        {"session_id": payload.session_id},
        {"$set": {"admin_typing_at": utc_now().isoformat()}},
    )
    return {"ok": True}


@router.get("/support/chat/{session_id}")
async def get_my_chat(session_id: str):
    """Visitor pulls the full thread (oldest → newest). Anon-friendly; we
    don't restrict by user since the session_id IS the secret."""
    msgs = []
    async for m in db.support_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1):
        msgs.append(m)
    session = await db.support_chats.find_one({"session_id": session_id}, {"_id": 0}) or {}
    # Compute "admin is typing" — true if admin_typing_at within last 5s.
    session["admin_is_typing"] = _is_typing_active(session.get("admin_typing_at"))
    return {"session": session, "messages": msgs}


def _is_typing_active(ts_iso: Optional[str]) -> bool:
    """True if a typing-at timestamp is within the last 5 seconds.

    5s is the sweet spot: long enough that polling at 4s intervals reliably
    catches it (typing bubble feels persistent), short enough that the bubble
    disappears within a second of the user stopping.
    """
    if not ts_iso:
        return False
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return (utc_now() - ts) < timedelta(seconds=5)
    except Exception:  # noqa: BLE001
        return False


@router.get("/admin/support/sessions")
async def list_admin_sessions(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    out = []
    async for s in db.support_chats.find({}, {"_id": 0}).sort("last_msg_at", -1).limit(100):
        # Tack on the latest message preview so the admin list is scannable.
        last = await db.support_messages.find_one(
            {"session_id": s["session_id"]},
            {"_id": 0, "text": 1, "sender": 1, "created_at": 1},
            sort=[("created_at", -1)],
        ) or {}
        s["last_message_preview"] = (last.get("text") or "")[:140]
        s["last_message_sender"] = last.get("sender")
        out.append(s)
    return out


@router.get("/admin/support/sessions/{session_id}")
async def get_admin_session(session_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    # Clear the admin unread badge FIRST so the returned session reflects
    # the post-read state (otherwise the UI shows a stale "1 unread" badge
    # until the next poll).
    await db.support_chats.update_one(
        {"session_id": session_id},
        {"$set": {"unread_admin_count": 0}},
    )
    msgs = []
    async for m in db.support_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1):
        msgs.append(m)
    session = await db.support_chats.find_one({"session_id": session_id}, {"_id": 0}) or {}
    session["visitor_is_typing"] = _is_typing_active(session.get("visitor_typing_at"))
    return {"session": session, "messages": msgs}


@router.post("/admin/support/reply")
async def admin_reply(payload: AdminReplyIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    now_iso = utc_now().isoformat()
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "session_id": payload.session_id,
        "sender": "admin",
        "user_id": user["user_id"],
        "sender_name": user.get("name") or "Support",
        "text": payload.text.strip(),
        "created_at": now_iso,
    }
    await db.support_messages.insert_one(msg)
    await db.support_chats.update_one(
        {"session_id": payload.session_id},
        {"$set": {"last_msg_at": now_iso, "last_admin_msg_at": now_iso, "status": "open"},
         "$inc": {"unread_visitor_count": 1}},
    )
    msg.pop("_id", None)
    return msg


@router.post("/admin/support/{session_id}/close")
async def admin_close(session_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    await db.support_chats.update_one(
        {"session_id": session_id},
        {"$set": {"status": "closed", "closed_at": utc_now().isoformat()}},
    )
    return {"ok": True}
