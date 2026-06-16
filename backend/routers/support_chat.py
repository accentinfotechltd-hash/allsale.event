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
import json
import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

try:
    # LLM client — re-used for the auto-translate flow. Optional import so the
    # router still loads if emergentintegrations isn't on the box.
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
except Exception:  # noqa: BLE001
    LlmChat = None  # type: ignore
    UserMessage = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support_chat"])

# Throttle the "new visitor message" admin email so a rapid-fire visitor
# (sending 6 quick lines) only produces ONE email per 5-minute window.
NEW_MSG_EMAIL_THROTTLE_MIN = int(os.environ.get("SUPPORT_EMAIL_THROTTLE_MIN", "5"))

MAX_MSG_LEN = 2000
MAX_NAME_LEN = 80
# Inline base64 attachments only — keeps the DB self-contained, no need to
# wire S3/Cloudflare R2 for screenshots. 800 KB is enough for a 1080p
# screenshot at decent JPEG quality.
MAX_ATTACHMENT_BYTES = 800 * 1024
ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif",
    "application/pdf",
}


class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    mime: str = Field(min_length=3, max_length=80)
    data_url: str = Field(min_length=12, max_length=int(MAX_ATTACHMENT_BYTES * 1.4))  # base64 overhead


class SupportMessageIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    text: Optional[str] = Field(default=None, max_length=MAX_MSG_LEN)
    name: Optional[str] = Field(default=None, max_length=MAX_NAME_LEN)
    email: Optional[str] = Field(default=None, max_length=120)
    attachment: Optional[AttachmentIn] = None


class AdminReplyIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=MAX_MSG_LEN)


def _validate_attachment(att: Optional[AttachmentIn]) -> None:
    """Sanity-check an incoming attachment so the DB doesn't blow up."""
    if not att:
        return
    if att.mime.lower() not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {att.mime}")
    # data_url looks like "data:image/png;base64,iVBORw…"; the base64 portion
    # should round-trip to no more than MAX_ATTACHMENT_BYTES bytes.
    head, _, body = att.data_url.partition(",")
    if "base64" not in head:
        raise HTTPException(status_code=400, detail="Attachment must be base64 data URL")
    # 4 base64 chars = 3 bytes, so estimate without decoding (cheap path)
    approx_bytes = (len(body) * 3) // 4
    if approx_bytes > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment too large ({approx_bytes // 1024} KB). Max is {MAX_ATTACHMENT_BYTES // 1024} KB.",
        )


# ---------------------------------------------------------------------------
# Auto-translate
# ---------------------------------------------------------------------------

async def _maybe_translate(text: str) -> tuple[Optional[str], Optional[str]]:
    """Detect language + return English translation if needed.

    Returns `(detected_lang, translated_text)`. Both can be None:
      • `None, None`  →  translation not available or English already.
      • `"hi", "..."`  →  detected Hindi, here's the English version.

    Fails silently — translation is a nicety, not a hard requirement. If the
    LLM is unreachable we just store the original text and admin sees it raw.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key or not LlmChat or not text or not text.strip():
        return None, None
    body = text.strip()
    if len(body) > 600:
        # Skip very long messages to keep latency + cost down. Admin can ask
        # the visitor to send shorter messages or use Google translate.
        return None, None
    # Fast-path: text that is *all* ASCII letters/punct is overwhelmingly
    # English; no need to spend an LLM call on "hi" or "Here's a screenshot".
    if all(ord(ch) < 128 for ch in body):
        return "en", None
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"chat-translate-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You detect language and translate. Return STRICT JSON: "
                '{"lang":"<ISO-639-1>","translated":"<english text or original if already english>"}. '
                "If the input is already English (or > 80% English) return lang=en and translated=<original>. "
                "Never include any commentary outside the JSON."
            ),
        ).with_model("openai", "gpt-5.1")
        resp = await chat.send_message(UserMessage(text=body))
        raw = resp.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip().rstrip("`").strip()
        parsed = json.loads(raw)
        lang = (parsed.get("lang") or "").lower()[:5] or None
        translated = (parsed.get("translated") or "").strip() or None
        # If already English (or detector said so), don't bother saving translation
        if lang and lang.startswith("en"):
            return lang, None
        return lang, translated
    except Exception:  # noqa: BLE001
        logger.warning("Auto-translate failed; storing original", exc_info=True)
        return None, None


def _try_get_user(request: Request) -> Optional[dict]:
    """Best-effort current-user lookup — chat works for anon visitors too."""
    # We can't call get_current_user directly (it raises on missing auth),
    # so we just check the header presence and let the upstream code grab
    # user info from the bearer-token cache if it's there.
    return getattr(request.state, "_cached_user", None)


async def _maybe_notify_admins(session_id: str, visitor_name: str, preview: str) -> None:
    """Fire-and-forget admin alert email + optional Slack post when a new
    visitor message lands.

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

    # Site-level support_chat settings (Slack webhook etc.)
    settings_doc = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    sc_settings = (settings_doc.get("support_chat") or {})
    slack_url = (sc_settings.get("slack_webhook_url") or "").strip()

    try:
        from emails import send_template_fireforget
    except Exception:  # noqa: BLE001
        send_template_fireforget = None

    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    admin_url = f"{origin}/admin"

    # Email blast to every admin
    if send_template_fireforget:
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

    # Slack post (if configured)
    if slack_url:
        try:
            import httpx
            payload = {
                "text": f"💬 *New support chat from {visitor_name}*",
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn",
                        "text": f"💬 *New support chat from {visitor_name}*\n>{preview[:280]}"}},
                    {"type": "actions", "elements": [
                        {"type": "button", "text": {"type": "plain_text", "text": "Open admin"},
                         "url": admin_url, "style": "primary"},
                    ]},
                ],
            }
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(slack_url, json=payload)
        except Exception:  # noqa: BLE001
            logger.exception("Slack webhook post failed for session %s", session_id)

    # Mark notified
    await db.support_chats.update_one(
        {"session_id": session_id},
        {"$set": {"last_admin_notified_at": utc_now().isoformat()}},
    )


@router.post("/support/chat/messages")
async def post_visitor_message(payload: SupportMessageIn, request: Request):
    """Visitor sends a message. Creates the session on first hit.

    Can include text, an attachment (image/PDF as base64 data URL), or both.
    """
    text = (payload.text or "").strip()
    _validate_attachment(payload.attachment)
    if not text and not payload.attachment:
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

    # Run translation in the background — don't block the send latency.
    # We'll patch the message doc once it returns.
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "session_id": payload.session_id,
        "sender": "visitor",
        "user_id": user_id,
        "text": text,
        "attachment": payload.attachment.model_dump() if payload.attachment else None,
        "created_at": now_iso,
    }
    await db.support_messages.insert_one(msg)

    async def _translate_and_patch():
        try:
            lang, translated = await _maybe_translate(text)
            if lang or translated:
                await db.support_messages.update_one(
                    {"message_id": msg["message_id"]},
                    {"$set": {"original_lang": lang, "translated_text": translated}},
                )
        except Exception:  # noqa: BLE001
            logger.exception("translate-and-patch failed")

    if text:
        asyncio.create_task(_translate_and_patch())

    # Background email + Slack to admins (throttled).
    visitor_name = (payload.name or (user.get("name") if user else None) or "Anonymous").strip() or "Anonymous"
    preview = text or "[attachment]"
    asyncio.create_task(_maybe_notify_admins(payload.session_id, visitor_name, preview))

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


# ---------------------------------------------------------------------------
# Emoji reactions — tiny "👍 ❤️ 😂 🎉" toolbar on each message.
# ---------------------------------------------------------------------------

# Reactions are stored on the message doc as { "👍": ["sid1", "sid2"], "❤️": [...] }
# Identity is either user_id (auth'd) or session_id (anon).
ALLOWED_EMOJI = {"👍", "❤️", "😂", "🎉", "😮", "😢", "🔥"}


class ReactionIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message_id: str
    emoji: str
    actor_id: Optional[str] = None  # falls back to session_id when anon


@router.post("/support/chat/reactions")
async def toggle_reaction(payload: ReactionIn, request: Request):
    """Toggle an emoji reaction on a message — same actor twice removes it.

    Works for both anon visitors (keyed by session_id) and authenticated
    admins (keyed by user_id). The frontend doesn't care which identifier
    it uses — both end up as strings in the message's reactions map.
    """
    if payload.emoji not in ALLOWED_EMOJI:
        raise HTTPException(status_code=400, detail="Unsupported emoji")

    msg = await db.support_messages.find_one({"message_id": payload.message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.get("session_id") != payload.session_id:
        raise HTTPException(status_code=403, detail="Message belongs to another session")

    actor = payload.actor_id or payload.session_id

    user = _try_get_user(request)
    if user:
        actor = user["user_id"]

    reactions = msg.get("reactions") or {}
    bucket = list(reactions.get(payload.emoji) or [])
    if actor in bucket:
        bucket = [a for a in bucket if a != actor]
    else:
        bucket.append(actor)
    if bucket:
        reactions[payload.emoji] = bucket
    else:
        reactions.pop(payload.emoji, None)

    await db.support_messages.update_one(
        {"message_id": payload.message_id},
        {"$set": {"reactions": reactions}},
    )
    return {"message_id": payload.message_id, "reactions": reactions}


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
    # Inject a "system" message that prompts the visitor to rate the chat.
    # Polling will pick it up; the frontend renders a 5-star widget for any
    # message with sender="system" and kind="rating_prompt".
    now_iso = utc_now().isoformat()
    await db.support_messages.insert_one({
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "session_id": session_id,
        "sender": "system",
        "kind": "rating_prompt",
        "text": "How was your support experience today?",
        "created_at": now_iso,
    })
    await db.support_chats.update_one(
        {"session_id": session_id},
        {"$set": {
            "status": "closed",
            "closed_at": now_iso,
            "last_msg_at": now_iso,
        }},
    )
    return {"ok": True}


class RatingIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    stars: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=600)


@router.post("/support/chat/rate")
async def visitor_rate(payload: RatingIn):
    """Visitor submits CSAT rating. One per session — re-submitting overwrites
    so the visitor can change their mind without complicating the schema."""
    rating_doc = {
        "stars": payload.stars,
        "comment": (payload.comment or "").strip() or None,
        "rated_at": utc_now().isoformat(),
    }
    r = await db.support_chats.update_one(
        {"session_id": payload.session_id},
        {"$set": {"rating": rating_doc}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    # Insert a confirmation system message so the visitor sees their rating reflected.
    await db.support_messages.insert_one({
        "message_id": f"msg_{uuid.uuid4().hex[:12]}",
        "session_id": payload.session_id,
        "sender": "system",
        "kind": "rating_received",
        "text": f"You rated this chat {payload.stars}/5 — thanks!",
        "created_at": utc_now().isoformat(),
    })
    return {"ok": True, "rating": rating_doc}


@router.get("/admin/support/sessions/{session_id}/export.csv")
async def export_chat_csv(session_id: str, user: dict = Depends(get_current_user)):
    """Download a chat transcript as CSV. Useful for compliance, training,
    or pasting into a ticket system."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    import csv
    import io
    from fastapi.responses import StreamingResponse

    sess = await db.support_chats.find_one({"session_id": session_id}, {"_id": 0}) or {}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "sender", "sender_name", "text", "attachment_filename", "original_lang", "translated_text"])
    async for m in db.support_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1):
        att = (m.get("attachment") or {}).get("filename") if m.get("attachment") else ""
        writer.writerow([
            m.get("created_at", ""),
            m.get("sender", ""),
            m.get("sender_name") or sess.get("visitor_name") or "",
            (m.get("text") or "").replace("\n", " "),
            att,
            m.get("original_lang") or "",
            (m.get("translated_text") or "").replace("\n", " "),
        ])
    buf.seek(0)
    fname = f"chat_{session_id}_{utc_now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
