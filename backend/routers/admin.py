"""Admin endpoints: events moderation + user management."""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, event_to_public, utc_now
from emails import send_template_fireforget

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_only(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# ---------- Events moderation ----------
@router.get("/events")
async def admin_events(user: dict = Depends(get_current_user)):
    _admin_only(user)
    cursor = db.events.find({}, {"_id": 0}).sort("created_at", -1)
    return [event_to_public(e) async for e in cursor]


@router.post("/events/{event_id}/approve")
async def admin_approve(event_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    result = await db.events.update_one({"event_id": event_id}, {"$set": {"status": "approved"}})
    if result.modified_count:
        event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
        if event:
            organizer = await db.users.find_one({"user_id": event.get("organizer_id")}, {"_id": 0}) or {}
            if organizer.get("email"):
                send_template_fireforget("organizer_event_approved", organizer["email"], {
                    "organizer_name": organizer.get("name", "organizer"),
                    "event_id": event_id,
                    "event_title": event.get("title", "Your event"),
                }, db)
    return {"ok": True}


@router.post("/events/{event_id}/reject")
async def admin_reject(event_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    await db.events.update_one({"event_id": event_id}, {"$set": {"status": "rejected"}})
    return {"ok": True}


@router.post("/events/{event_id}/feature")
async def admin_feature(event_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await db.events.update_one(
        {"event_id": event_id}, {"$set": {"featured": not e.get("featured", False)}}
    )
    return {"ok": True}


# ---------- Demo data wipe (one-shot cleanup) ----------
# Hard-coded list of titles that ship with `seed.py`. Used so we can target the
# exact demo events for deletion without nuking anything the organizer has
# created themselves. Keep this list in sync with `backend/seed.py:DEMO_EVENTS`.
_DEMO_EVENT_TITLES = {
    "Dune: Part Three — IMAX Premiere",
    "Studio Ghibli Retrospective — Spirited Away (35mm)",
    "Midnight Echoes — Live in Concert",
    "Stand-Up Saturday: The Roast",
    "AllBlacks vs Wallabies — Bledisloe Cup",
    "Hamilton — The Musical",
    "Future//Stack — Devs Conference 2026",
    "Ceramics Studio Weekend",
    "Splendour Open Air Festival",
    "Modernism Reframed — Art Exhibit",
}
_DEMO_USER_EMAILS = {"organizer@allsale.events", "attendee@allsale.events"}


@router.post("/wipe-demo-data")
async def admin_wipe_demo_data(user: dict = Depends(get_current_user)):
    """One-shot cleanup of seeded demo events + demo users.

    Only removes records that match the exact titles / emails shipped in
    `seed.py`. Real events and real users created by the organizer are
    completely untouched. Cascading cleanup mirrors `DELETE /api/events/{id}`
    so we don't leave orphaned bookings / holds / scanner tokens behind.
    """
    _admin_only(user)

    # 1) Find every event matching the demo titles.
    demo_events = await db.events.find(
        {"title": {"$in": list(_DEMO_EVENT_TITLES)}}, {"_id": 0, "event_id": 1, "title": 1},
    ).to_list(50)
    demo_event_ids = [e["event_id"] for e in demo_events]
    cascade_counts = {
        "events": 0, "bookings": 0, "holds": 0, "reservations": 0,
        "scanner_tokens": 0, "team_grants": 0, "discount_codes": 0,
        "waitlist": 0, "views": 0,
    }

    if demo_event_ids:
        # Cascade in the same order as the regular DELETE /events/{id} handler.
        cascade_counts["bookings"] = (await db.bookings.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["holds"] = (await db.seat_holds.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["reservations"] = (await db.seat_reservations.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["scanner_tokens"] = (await db.scanner_tokens.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["team_grants"] = (await db.team_members_event.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["discount_codes"] = (await db.discount_codes.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["waitlist"] = (await db.waitlist_entries.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["views"] = (await db.event_views.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count
        cascade_counts["events"] = (await db.events.delete_many(
            {"event_id": {"$in": demo_event_ids}})).deleted_count

    # 2) Remove the demo user accounts (admin stays).
    users_deleted = (await db.users.delete_many(
        {"email": {"$in": list(_DEMO_USER_EMAILS)}})).deleted_count

    return {
        "ok": True,
        "events_removed": cascade_counts["events"],
        "users_removed": users_deleted,
        "cascade": cascade_counts,
        "demo_event_titles_matched": [e["title"] for e in demo_events],
    }


# ---------- Public stats (used by the landing-page hero chip) ----------


# ---------- User management ----------
class RoleIn(BaseModel):
    role: str  # attendee | organizer | admin


@router.get("/users")
async def admin_list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    active: Optional[bool] = None,
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    query: dict = {}
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    if role in ("attendee", "organizer", "admin"):
        query["role"] = role
    if active is not None:
        if active:
            # active = NOT explicitly suspended (default = active)
            query["$and"] = query.get("$and", []) + [{"$or": [{"active": True}, {"active": {"$exists": False}}]}]
        else:
            query["active"] = False

    items = []
    async for u in db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(500):
        u["active"] = u.get("active", True)
        # Counts: bookings (as attendee) + events (as organizer)
        u["bookings_count"] = await db.bookings.count_documents({"user_id": u["user_id"]})
        u["events_count"] = await db.events.count_documents({"organizer_id": u["user_id"]})
        items.append(u)
    return items


@router.post("/users/{user_id}/role")
async def admin_change_role(user_id: str, payload: RoleIn, user: dict = Depends(get_current_user)):
    _admin_only(user)
    if payload.role not in ("attendee", "organizer", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if user_id == user["user_id"] and payload.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot demote yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Don't allow demoting the last remaining admin (avoids locking the system out)
    if target.get("role") == "admin" and payload.role != "admin":
        admin_count = await db.users.count_documents({"role": "admin"})
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last remaining admin")
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": payload.role, "role_updated_at": utc_now().isoformat()}},
    )
    return {"ok": True, "user_id": user_id, "role": payload.role}


@router.post("/users/{user_id}/suspend")
async def admin_suspend_user(user_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    if user_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot suspend yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one(
        {"user_id": user_id}, {"$set": {"active": False, "suspended_at": utc_now().isoformat()}}
    )
    # Invalidate any active sessions
    await db.user_sessions.delete_many({"user_id": user_id})
    return {"ok": True}


@router.post("/users/{user_id}/unsuspend")
async def admin_unsuspend_user(user_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one(
        {"user_id": user_id}, {"$set": {"active": True}, "$unset": {"suspended_at": ""}}
    )
    return {"ok": True}


@router.get("/users/stats")
async def admin_user_stats(user: dict = Depends(get_current_user)):
    """Summary stats for the user-management header."""
    _admin_only(user)
    total = await db.users.count_documents({})
    by_role = {}
    for r in ("attendee", "organizer", "admin"):
        by_role[r] = await db.users.count_documents({"role": r})
    suspended = await db.users.count_documents({"active": False})
    return {"total": total, "by_role": by_role, "suspended": suspended}


# ---------- Admin: user drill-down + contact edit ----------
# Declared AFTER /users/stats so FastAPI matches the literal path first.
class UserPatchIn(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


@router.get("/users/{user_id}")
async def admin_user_detail(user_id: str, user: dict = Depends(get_current_user)):
    """Full user record + their bookings + organized events (admin drill-down)."""
    _admin_only(user)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    bookings = []
    async for b in db.bookings.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(200):
        bookings.append({
            "booking_id": b.get("booking_id"),
            "event_id": b.get("event_id"),
            "event_title": b.get("event_title"),
            "event_date": b.get("event_date"),
            "tier_name": b.get("tier_name"),
            "seats": b.get("seats") or [],
            "quantity": b.get("quantity"),
            "amount": b.get("amount"),
            "currency": b.get("currency"),
            "status": b.get("status"),
            "checked_in": b.get("checked_in", False),
            "created_at": b.get("created_at"),
        })

    events = []
    async for e in db.events.find({"organizer_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(200):
        events.append({
            "event_id": e.get("event_id"),
            "title": e.get("title"),
            "venue": e.get("venue"),
            "city": e.get("city"),
            "date": e.get("date"),
            "status": e.get("status"),
            "category": e.get("category"),
            "capacity": e.get("capacity"),
        })

    target["active"] = target.get("active", True)
    target["bookings"] = bookings
    target["events"] = events
    target["bookings_count"] = len(bookings)
    target["events_count"] = len(events)
    return target


@router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, payload: UserPatchIn, user: dict = Depends(get_current_user)):
    """Admin edit a user's contact details (name, email, phone)."""
    _admin_only(user)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    update: dict = {}
    if payload.name is not None:
        nm = payload.name.strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        update["name"] = nm
    if payload.email is not None:
        new_email = payload.email.lower().strip()
        if new_email and new_email != target["email"]:
            clash = await db.users.find_one({"email": new_email, "user_id": {"$ne": user_id}})
            if clash:
                raise HTTPException(status_code=400, detail="That email is already taken")
            update["email"] = new_email
    if payload.phone is not None:
        update["phone"] = payload.phone.strip() or None

    if not update:
        return {"updated": False}

    update["admin_updated_at"] = utc_now().isoformat()
    update["admin_updated_by"] = user["user_id"]
    await db.users.update_one({"user_id": user_id}, {"$set": update})
    refreshed = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"updated": True, **refreshed}


# ---------- Email blast (admin-only) ----------
class BlastIn(BaseModel):
    subject: str
    body: str  # plain text; rendered with <br>
    target: str = "marketing_optins"  # marketing_optins | all_attendees | event_attendees
    event_id: Optional[str] = None  # required when target == event_attendees or to attach a CTA


@router.post("/blast")
async def admin_send_blast(payload: BlastIn, user: dict = Depends(get_current_user)):
    """Send a custom email to a filtered audience. Returns recipient count."""
    _admin_only(user)
    if not payload.subject.strip() or not payload.body.strip():
        raise HTTPException(status_code=400, detail="Subject and body are required")

    target = payload.target
    if target not in ("marketing_optins", "all_attendees", "event_attendees"):
        raise HTTPException(status_code=400, detail="Invalid target")
    if target == "event_attendees" and not payload.event_id:
        raise HTTPException(status_code=400, detail="event_id required for event_attendees target")

    event_doc = None
    if payload.event_id:
        event_doc = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
        if not event_doc:
            raise HTTPException(status_code=404, detail="Event not found")

    emails: set[str] = set()
    user_lookup: dict[str, str] = {}  # email → name

    if target == "marketing_optins":
        async for u in db.users.find({}, {"_id": 0, "email": 1, "name": 1, "notification_prefs": 1}):
            prefs = u.get("notification_prefs") or {}
            if prefs.get("email_marketing") and u.get("email"):
                emails.add(u["email"])
                user_lookup[u["email"]] = u.get("name") or u["email"].split("@")[0]
    elif target == "event_attendees":
        async for b in db.bookings.find(
            {"event_id": payload.event_id, "status": "paid"}, {"_id": 0, "user_email": 1, "user_name": 1},
        ):
            if b.get("user_email"):
                emails.add(b["user_email"])
                user_lookup[b["user_email"]] = b.get("user_name") or b["user_email"].split("@")[0]
    else:  # all_attendees — anyone who's ever had a paid booking
        async for b in db.bookings.find({"status": "paid"}, {"_id": 0, "user_email": 1, "user_name": 1}):
            if b.get("user_email"):
                emails.add(b["user_email"])
                user_lookup[b["user_email"]] = b.get("user_name") or b["user_email"].split("@")[0]

    if not emails:
        return {"sent": 0, "skipped": "no matching recipients"}

    from emails import send_template_fireforget
    from datetime import datetime as _dt
    def _fmt_when(iso: str) -> str:
        try:
            return _dt.fromisoformat(iso.replace("Z", "+00:00")).strftime("%a, %b %-d · %-I:%M %p")
        except Exception:
            return iso or ""

    ctx_base = {
        "subject": payload.subject,
        "body": payload.body,
    }
    if event_doc:
        ctx_base.update({
            "event_id": event_doc["event_id"],
            "event_title": event_doc.get("title", ""),
            "event_when": _fmt_when(event_doc.get("date") or ""),
        })

    sent = 0
    for email in emails:
        try:
            send_template_fireforget(
                "admin_blast",
                email,
                {**ctx_base, "user_name": user_lookup.get(email, "there")},
                db,
            )
            sent += 1
        except Exception:
            pass
    return {"sent": sent, "target": target, "event_id": payload.event_id}


# ---------- Email logs (audit trail) ----------
@router.get("/email-logs")
async def admin_email_logs(
    template: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    query: dict = {}
    if template:
        query["template"] = template
    if status in ("sent", "failed", "skipped"):
        query["status"] = status
    if q:
        query["to"] = {"$regex": q, "$options": "i"}
    items = []
    async for log in db.email_logs.find(query, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)):
        items.append(log)

    # Summary stats
    sent = await db.email_logs.count_documents({"status": "sent"})
    failed = await db.email_logs.count_documents({"status": "failed"})
    skipped = await db.email_logs.count_documents({"status": "skipped"})
    return {"items": items, "stats": {"sent": sent, "failed": failed, "skipped": skipped}}



@router.get("/email/diagnostics")
async def admin_email_diagnostics(user: dict = Depends(get_current_user)):
    """Reports the runtime config the email system is using so the admin can
    tell at a glance whether emails will work in production.

    Never returns the API key itself — only whether it's set and its prefix.
    """
    _admin_only(user)
    import os as _os
    try:
        from emails import RESEND_API_KEY, SENDER_EMAIL, REPLY_TO_EMAIL, APP_PUBLIC_URL, _RESEND_AVAILABLE
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "reason": f"emails module not importable: {exc}"}

    key_set = bool(RESEND_API_KEY)
    # `re_xxxxxx` is the Resend live-key prefix; warn if it's blank or odd.
    key_prefix = RESEND_API_KEY[:4] if key_set else None

    # A "sandbox" sender (anything @resend.dev) means Resend will reject
    # delivery to anything other than the verified account owner's email.
    # That's why test bookings can succeed but the customer never receives anything.
    sender_is_sandbox = SENDER_EMAIL.endswith("@resend.dev")

    recent_logs = []
    async for log in db.email_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(10):
        recent_logs.append({
            "template": log.get("template"),
            "to": log.get("to"),
            "status": log.get("status"),
            "reason": log.get("reason"),
            "subject": log.get("subject"),
            "created_at": log.get("created_at"),
        })

    sent = await db.email_logs.count_documents({"status": "sent"})
    failed = await db.email_logs.count_documents({"status": "failed"})
    skipped = await db.email_logs.count_documents({"status": "skipped"})

    return {
        "ok": _RESEND_AVAILABLE and key_set,
        "resend_available": _RESEND_AVAILABLE,
        "api_key_set": key_set,
        "api_key_prefix": key_prefix,
        "sender_email": SENDER_EMAIL,
        "sender_is_sandbox": sender_is_sandbox,
        "reply_to_email": REPLY_TO_EMAIL or None,
        "app_public_url": APP_PUBLIC_URL,
        "stats": {"sent": sent, "failed": failed, "skipped": skipped},
        "recent_logs": recent_logs,
    }


class _ResendBookingIn(BaseModel):
    booking_id: str


@router.get("/bookings/lookup")
async def admin_bookings_lookup(email: str, user: dict = Depends(get_current_user)):
    """Search paid bookings by customer email. Used by the email-resend admin
    UI so support staff don't have to dig through individual events to find
    a customer's booking IDs.
    """
    _admin_only(user)
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    results = []
    async for b in db.bookings.find(
        {"user_email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {"_id": 0, "booking_id": 1, "event_id": 1, "status": 1, "user_email": 1,
         "amount": 1, "currency": 1, "created_at": 1, "paid_at": 1},
    ).sort("created_at", -1).limit(50):
        ev = await db.events.find_one({"event_id": b.get("event_id")}, {"_id": 0, "title": 1, "date": 1})
        b["event_title"] = (ev or {}).get("title")
        b["event_date"] = (ev or {}).get("date")
        results.append(b)
    return {"ok": True, "email": email, "count": len(results), "bookings": results}


@router.post("/email/resend-booking")
async def admin_resend_booking_confirmation(
    payload: _ResendBookingIn,
    user: dict = Depends(get_current_user),
):
    """Manually resend the booking confirmation email for a given booking_id.
    Used by admin support when a customer reports their email never arrived
    (spam folder, bounce, address typo, etc.).
    """
    _admin_only(user)
    booking = await db.bookings.find_one({"booking_id": payload.booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") != "paid":
        raise HTTPException(
            status_code=400,
            detail=f"Booking status is '{booking.get('status')}' — only paid bookings can have their confirmation resent",
        )
    # Defer to the shared helper that's also used by webhook + reconcile.
    from routers.payments import _send_booking_confirmation_email
    await _send_booking_confirmation_email(payload.booking_id)
    return {
        "ok": True,
        "booking_id": payload.booking_id,
        "to": booking.get("user_email"),
        "message": "Confirmation email queued. Check /admin/email-logs in ~10 sec for delivery status.",
    }


class _SendTestIn(BaseModel):
    to: str
    subject: str | None = None


@router.post("/email/send-test")
async def admin_email_send_test(payload: _SendTestIn, user: dict = Depends(get_current_user)):
    """Send a tiny diagnostic email to verify the production Resend setup
    without paying for a real ticket. The response surfaces the underlying
    Resend response (including error message) so we can pinpoint config
    issues from a single click in the admin UI.
    """
    _admin_only(user)
    if not payload.to or "@" not in payload.to:
        raise HTTPException(status_code=400, detail="Invalid 'to' email")

    from emails import (
        RESEND_API_KEY, SENDER_EMAIL, REPLY_TO_EMAIL, SENDER_NAME,
        _RESEND_AVAILABLE, resend as _resend_sdk, _layout,
    )
    if not _RESEND_AVAILABLE or not RESEND_API_KEY or _resend_sdk is None:
        return {"ok": False, "reason": "Resend SDK or API key missing"}

    import asyncio
    subject = payload.subject or "Allsale Events — email delivery test"
    html = _layout(
        title=subject,
        preheader="If you can read this, your transactional emails are working.",
        body_html=(
            "<p style='font-family:Helvetica,Arial,sans-serif;color:#F5F5F0;"
            "font-size:15px;line-height:1.6;'>This is a diagnostic test email "
            "sent from the Allsale Events admin panel. If it landed in your "
            "inbox, the Resend integration is configured correctly and "
            "customers will start receiving booking confirmations.</p>"
        ),
    )
    text = "Allsale Events — email delivery test. If you can read this, transactional emails are working."

    params = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [payload.to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if REPLY_TO_EMAIL:
        params["reply_to"] = [REPLY_TO_EMAIL]

    try:
        result = await asyncio.to_thread(_resend_sdk.Emails.send, params)
        email_id = result.get("id") if isinstance(result, dict) else None
        await db.email_logs.insert_one({
            "log_id": f"test_{utc_now().isoformat()}",
            "template": "admin_test",
            "to": payload.to,
            "status": "sent",
            "subject": subject,
            "resend_id": email_id,
            "created_at": utc_now().isoformat(),
            "triggered_by": user["user_id"],
        })
        return {"ok": True, "to": payload.to, "from": params["from"], "reply_to": REPLY_TO_EMAIL or None, "resend_id": email_id}
    except Exception as exc:
        reason = str(exc)[:500]
        await db.email_logs.insert_one({
            "log_id": f"test_{utc_now().isoformat()}",
            "template": "admin_test",
            "to": payload.to,
            "status": "failed",
            "reason": reason,
            "subject": subject,
            "created_at": utc_now().isoformat(),
            "triggered_by": user["user_id"],
        })
        return {"ok": False, "to": payload.to, "from": params["from"], "reason": reason}
