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

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support_chat"])

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
    msg.pop("_id", None)
    return msg


@router.get("/support/chat/{session_id}")
async def get_my_chat(session_id: str):
    """Visitor pulls the full thread (oldest → newest). Anon-friendly; we
    don't restrict by user since the session_id IS the secret."""
    msgs = []
    async for m in db.support_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1):
        msgs.append(m)
    session = await db.support_chats.find_one({"session_id": session_id}, {"_id": 0}) or {}
    return {"session": session, "messages": msgs}


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
