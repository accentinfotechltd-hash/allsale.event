"""Admin ↔ Organizer messaging — one ongoing thread per organizer.

Why a dedicated module instead of reusing the existing support-chat or
organizer-inbox plumbing?
- support-chat is keyed by an anonymous browser session and aimed at *visitors*
  contacting Allsale support. It doesn't have an authenticated organizer side.
- organizer_messages is a one-way attendee → organizer contact form, not a
  back-and-forth thread.

Design choices:
- ONE thread per organizer (Intercom-style). The thread_id is just the
  organizer's user_id — no separate collection to manage.
- Messages live in `admin_organizer_messages` with sender_role and read flags
  on both sides so we can compute unread badges in O(1) per side.
- Outbound email is sent fire-and-forget on every new message so the other
  party gets notified even if they're offline.
- Real-time delivery via the `chat_hub` WebSocket pub/sub (see below) so
  active sessions see the other side's reply instantly without polling. The
  existing email + unread badge stays as a fallback for offline parties.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core import JWT_ALGO, JWT_SECRET, db, get_current_user, utc_now
from emails import send_template_fireforget

router = APIRouter(tags=["admin_organizer_chat"])
logger = logging.getLogger("aura.adminchat")


class MessageIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# WebSocket hub — pub/sub keyed by organizer_id (= thread key).
# Single-process; OK for our single-pod backend. Multi-pod would need Redis.
# ---------------------------------------------------------------------------

class ChatHub:
    def __init__(self) -> None:
        self.subs: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def add(self, organizer_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.subs[organizer_id].add(ws)

    async def remove(self, organizer_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.subs.get(organizer_id, set()).discard(ws)
            if not self.subs.get(organizer_id):
                self.subs.pop(organizer_id, None)

    async def broadcast(self, organizer_id: str, message: dict) -> None:
        async with self.lock:
            targets = list(self.subs.get(organizer_id, set()))
        if not targets:
            return
        dead: List[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                for ws in dead:
                    self.subs.get(organizer_id, set()).discard(ws)


chat_hub = ChatHub()


def _admin_only(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


async def _ensure_organizer(organizer_id: str) -> dict:
    org = await db.users.find_one(
        {"user_id": organizer_id},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1},
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organizer not found")
    if org.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=400, detail="Target user is not an organizer")
    return org


async def _serialize_messages(organizer_id: str, limit: int = 200) -> List[dict]:
    out: List[dict] = []
    async for m in (
        db.admin_organizer_messages
        .find({"organizer_id": organizer_id}, {"_id": 0})
        .sort("created_at", 1)
        .limit(limit)
    ):
        out.append(m)
    return out


# ---------- Admin side ----------

@router.get("/admin/organizer-threads")
async def list_threads(user: dict = Depends(get_current_user)):
    """List every organizer with their last-message preview and admin-side unread count.

    Includes ALL organizers (even those with zero messages) so admin can start
    a fresh conversation with anyone.
    """
    _admin_only(user)
    threads = []
    async for org in db.users.find(
        {"role": "organizer"},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "picture": 1},
    ).sort("created_at", -1):
        last = await db.admin_organizer_messages.find_one(
            {"organizer_id": org["user_id"]},
            {"_id": 0, "body": 1, "created_at": 1, "sender_role": 1},
            sort=[("created_at", -1)],
        )
        unread = await db.admin_organizer_messages.count_documents(
            {"organizer_id": org["user_id"], "sender_role": "organizer", "read_by_admin": {"$ne": True}}
        )
        threads.append({
            "organizer_id": org["user_id"],
            "organizer_name": org.get("name") or org.get("email", "Organizer"),
            "organizer_email": org.get("email"),
            "organizer_picture": org.get("picture"),
            "last_message_preview": (last or {}).get("body", "")[:120],
            "last_message_at": (last or {}).get("created_at"),
            "last_sender_role": (last or {}).get("sender_role"),
            "unread_count": unread,
        })
    # Sort: threads with messages first (newest activity), then untouched organizers.
    threads.sort(key=lambda t: (t["last_message_at"] is None, -(0 if t["last_message_at"] is None else 1), t["last_message_at"] or ""), reverse=True)
    return threads


@router.get("/admin/organizer-threads/{organizer_id}/messages")
async def admin_get_messages(organizer_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    org = await _ensure_organizer(organizer_id)
    msgs = await _serialize_messages(organizer_id)
    # Mark organizer→admin messages as read upon admin opening the thread.
    await db.admin_organizer_messages.update_many(
        {"organizer_id": organizer_id, "sender_role": "organizer", "read_by_admin": {"$ne": True}},
        {"$set": {"read_by_admin": True}},
    )
    return {"organizer": org, "messages": msgs}


@router.post("/admin/organizer-threads/{organizer_id}/messages")
async def admin_send_message(organizer_id: str, payload: MessageIn, user: dict = Depends(get_current_user)):
    _admin_only(user)
    org = await _ensure_organizer(organizer_id)
    import uuid
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "organizer_id": organizer_id,
        "sender_role": "admin",
        "sender_user_id": user["user_id"],
        "sender_name": user.get("name") or "Allsale support",
        "body": payload.body.strip(),
        "created_at": utc_now().isoformat(),
        "read_by_admin": True,        # the sender has obviously read it
        "read_by_organizer": False,
    }
    await db.admin_organizer_messages.insert_one(msg)
    out_msg = {k: v for k, v in msg.items() if k != "_id"}
    # Real-time broadcast to anyone subscribed to this thread (admin or organizer side).
    await chat_hub.broadcast(organizer_id, {"type": "message", "message": out_msg})
    # Notify organizer by email (fire-and-forget).
    try:
        if org.get("email"):
            send_template_fireforget(
                "admin_message_to_organizer",
                org["email"],
                {
                    "organizer_name": org.get("name") or "there",
                    "admin_name": user.get("name") or "Allsale support",
                    "preview": payload.body,
                },
                db,
            )
    except Exception:
        pass
    return out_msg


@router.post("/admin/organizer-threads/{organizer_id}/read")
async def admin_mark_read(organizer_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    await _ensure_organizer(organizer_id)
    res = await db.admin_organizer_messages.update_many(
        {"organizer_id": organizer_id, "sender_role": "organizer", "read_by_admin": {"$ne": True}},
        {"$set": {"read_by_admin": True}},
    )
    if res.modified_count:
        await chat_hub.broadcast(organizer_id, {"type": "read", "by": "admin"})
    return {"marked_read": res.modified_count}


# ---------- Organizer side ----------

def _require_organizer(user: dict) -> None:
    if user.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Organizer only")


@router.get("/organizer/admin-thread")
async def organizer_get_thread(user: dict = Depends(get_current_user)):
    """Organizer fetches their own thread with admin."""
    _require_organizer(user)
    msgs = await _serialize_messages(user["user_id"])
    await db.admin_organizer_messages.update_many(
        {"organizer_id": user["user_id"], "sender_role": "admin", "read_by_organizer": {"$ne": True}},
        {"$set": {"read_by_organizer": True}},
    )
    return {"messages": msgs}


@router.post("/organizer/admin-thread")
async def organizer_send_message(payload: MessageIn, user: dict = Depends(get_current_user)):
    _require_organizer(user)
    import uuid
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "organizer_id": user["user_id"],
        "sender_role": "organizer",
        "sender_user_id": user["user_id"],
        "sender_name": user.get("name") or "Organizer",
        "body": payload.body.strip(),
        "created_at": utc_now().isoformat(),
        "read_by_admin": False,
        "read_by_organizer": True,
    }
    await db.admin_organizer_messages.insert_one(msg)
    out_msg = {k: v for k, v in msg.items() if k != "_id"}
    # Real-time broadcast to anyone subscribed to this thread.
    await chat_hub.broadcast(user["user_id"], {"type": "message", "message": out_msg})
    # Notify all admins by email.
    try:
        async for admin in db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}):
            if not admin.get("email"):
                continue
            send_template_fireforget(
                "organizer_message_to_admin",
                admin["email"],
                {
                    "admin_name": admin.get("name") or "Admin",
                    "organizer_name": user.get("name") or "Organizer",
                    "organizer_id": user["user_id"],
                    "preview": payload.body,
                },
                db,
            )
    except Exception:
        pass
    return out_msg


@router.get("/organizer/admin-thread/unread")
async def organizer_unread_count(user: dict = Depends(get_current_user)):
    """Cheap endpoint the organizer nav can poll for a red-dot badge."""
    _require_organizer(user)
    count = await db.admin_organizer_messages.count_documents({
        "organizer_id": user["user_id"],
        "sender_role": "admin",
        "read_by_organizer": {"$ne": True},
    })
    return {"unread": count}


@router.post("/organizer/admin-thread/read")
async def organizer_mark_read(user: dict = Depends(get_current_user)):
    _require_organizer(user)
    res = await db.admin_organizer_messages.update_many(
        {"organizer_id": user["user_id"], "sender_role": "admin", "read_by_organizer": {"$ne": True}},
        {"$set": {"read_by_organizer": True}},
    )
    if res.modified_count:
        await chat_hub.broadcast(user["user_id"], {"type": "read", "by": "organizer"})
    return {"marked_read": res.modified_count}


# ---------------------------------------------------------------------------
# WebSocket — real-time live updates for the thread.
# Path: /api/ws/admin-organizer-chat/{organizer_id}?token=<jwt>
# Auth: same JWT the HTTP API uses. Passed via ?token= because browser
# WebSocket can't set Authorization headers. Admins can subscribe to ANY
# thread; organizers can only subscribe to their own.
# ---------------------------------------------------------------------------

async def _user_from_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except pyjwt.PyJWTError:
        return None
    user = await db.users.find_one(
        {"user_id": payload.get("sub")},
        {"_id": 0, "password_hash": 0},
    )
    if not user or user.get("active") is False:
        return None
    return user


@router.websocket("/ws/admin-organizer-chat/{organizer_id}")
async def chat_socket(ws: WebSocket, organizer_id: str):
    """Subscribe to a single thread. Emits message + read events live."""
    # WebSocket query params are pre-parsed by Starlette; pull the token.
    token = ws.query_params.get("token")
    user = await _user_from_token(token)
    if not user:
        await ws.close(code=4401)  # custom code: unauthorized
        return

    role = user.get("role")
    if role == "admin":
        pass  # admin may listen to any thread
    elif role in ("organizer",) and user.get("user_id") == organizer_id:
        pass  # organizer may only listen to their own
    else:
        await ws.close(code=4403)  # forbidden
        return

    await ws.accept()
    await chat_hub.add(organizer_id, ws)
    try:
        # Send a welcome ping so the client knows the subscription is live.
        await ws.send_json({"type": "hello", "organizer_id": organizer_id})
        # Heartbeat keeps idle connections alive through proxies. Also handles
        # inbound `typing` events from this socket and re-broadcasts to all
        # OTHER subscribers of the same thread so the other side sees an
        # "X is typing…" indicator without polling.
        sender_name = user.get("name") or user.get("email") or "Someone"
        sender_role = user.get("role") or "organizer"
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=25.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
                continue
            # Parse inbound JSON; ignore non-JSON noise (older clients send empty pings).
            try:
                import json
                evt = json.loads(raw)
            except Exception:
                continue
            if evt.get("type") == "typing":
                # Broadcast typing to other subscribers only; we don't echo back
                # to the sender. The hub helper doesn't know about exclusion so
                # we replicate the iteration here.
                async with chat_hub.lock:
                    targets = [t for t in chat_hub.subs.get(organizer_id, set()) if t is not ws]
                payload = {
                    "type": "typing",
                    "by": sender_role,
                    "name": sender_name,
                    "is_typing": bool(evt.get("is_typing", True)),
                }
                for t in targets:
                    try:
                        await t.send_json(payload)
                    except Exception:
                        pass
    except WebSocketDisconnect:
        pass
    except Exception as e:  # pragma: no cover
        logger.warning(f"[ws-chat] {organizer_id} disconnected: {e}")
    finally:
        await chat_hub.remove(organizer_id, ws)
