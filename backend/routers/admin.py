"""Admin endpoints: events moderation + user management."""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, event_to_public, utc_now
from emails import send_template_fireforget, send_template, TEMPLATES as EMAIL_TEMPLATES
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta, timezone
import uuid

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_only(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# ---------- Events moderation ----------
@router.get("/events")
async def admin_events(user: dict = Depends(get_current_user)):
    """List every event with sales rollups (tickets sold + revenue) attached.

    The dashboard table needs per-event sales numbers without paging through
    bookings client-side. We batch a single `$group` over `bookings` keyed by
    `event_id` so the response stays O(events + 1) regardless of how many
    paid bookings each event has.
    """
    _admin_only(user)
    items = [event_to_public(e) async for e in db.events.find({}, {"_id": 0}).sort("created_at", -1)]
    if not items:
        return []

    event_ids = [e["event_id"] for e in items]
    # One aggregation pass over bookings → revenue + tickets per event_id.
    # Only counts paid/confirmed bookings — pending holds and refunded rows
    # would mislead the dashboard about real revenue.
    sales_pipeline = [
        {"$match": {
            "event_id": {"$in": event_ids},
            "status": {"$in": ["paid", "confirmed"]},
        }},
        {"$group": {
            "_id": "$event_id",
            "tickets_sold": {"$sum": "$quantity"},
            "bookings_count": {"$sum": 1},
            "revenue": {"$sum": "$amount"},
            "face_value_total": {"$sum": "$face_value"},
        }},
    ]
    sales_map: dict = {}
    async for row in db.bookings.aggregate(sales_pipeline):
        sales_map[row["_id"]] = {
            "tickets_sold": int(row.get("tickets_sold") or 0),
            "bookings_count": int(row.get("bookings_count") or 0),
            "revenue": round(float(row.get("revenue") or 0), 2),
            "face_value_total": round(float(row.get("face_value_total") or 0), 2),
        }
    # Refunded amount per event so admin sees gross / net distinction.
    refund_pipeline = [
        {"$match": {"event_id": {"$in": event_ids}, "status": "refunded"}},
        {"$group": {"_id": "$event_id", "refunded": {"$sum": "$amount"}}},
    ]
    refund_map: dict = {}
    async for row in db.bookings.aggregate(refund_pipeline):
        refund_map[row["_id"]] = round(float(row.get("refunded") or 0), 2)

    for ev in items:
        s = sales_map.get(ev["event_id"]) or {
            "tickets_sold": 0, "bookings_count": 0, "revenue": 0, "face_value_total": 0,
        }
        ev["sales"] = {
            **s,
            "refunded": refund_map.get(ev["event_id"], 0),
            "net_revenue": round(s["revenue"] - refund_map.get(ev["event_id"], 0), 2),
        }
    return items


@router.get("/pending-events-count")
async def pending_events_count(user: dict = Depends(get_current_user)):
    """Cheap counter for the Admin nav badge — number of events awaiting
    moderation right now. Called by the layout every ~60 s."""
    _admin_only(user)
    n = await db.events.count_documents({"status": "pending"})
    return {"count": n}


@router.get("/events/submission-trend")
async def events_submission_trend(days: int = 14, user: dict = Depends(get_current_user)):
    """Mini-trend for the admin dashboard: how many events were submitted
    over the last N days, bucketed by day. Used to render a small sparkline
    showing whether organizer activity is trending up or down.

    Default is 14 days (covers 2 weeks). Capped at 90.
    """
    _admin_only(user)
    from datetime import timedelta
    days = max(1, min(90, int(days or 14)))
    since = (utc_now() - timedelta(days=days)).isoformat()
    last24 = (utc_now() - timedelta(hours=24)).isoformat()
    prev24 = (utc_now() - timedelta(hours=48)).isoformat()

    # Aggregate per-day submission counts via the `created_at` ISO string.
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "count": {"$sum": 1},
            "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = [r async for r in db.events.aggregate(pipeline)]
    series = [{"date": r["_id"], "count": r["count"], "pending": r["pending"]} for r in rows]

    submitted_24h = await db.events.count_documents({"created_at": {"$gte": last24}})
    submitted_prev_24h = await db.events.count_documents({"created_at": {"$gte": prev24, "$lt": last24}})
    if submitted_prev_24h > 0:
        delta_pct = round(((submitted_24h - submitted_prev_24h) * 100.0 / submitted_prev_24h), 1)
    else:
        delta_pct = None  # no comparison baseline

    return {
        "days": days,
        "series": series,
        "submitted_24h": submitted_24h,
        "submitted_prev_24h": submitted_prev_24h,
        "delta_pct": delta_pct,
        "total_in_window": sum(r["count"] for r in series),
    }


@router.post("/events/{event_id}/approve")
async def admin_approve(event_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    result = await db.events.update_one({"event_id": event_id}, {"$set": {"status": "approved"}})
    # We run the post-approval side effects (notification email, FIRST50
    # auto-promo) whenever the event ends up in `approved` state, even if
    # the update was a no-op (admin-authored events are created as
    # `approved`, so `modified_count` would be 0). Both side effects are
    # idempotent so re-running them is safe.
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if event and event.get("status") == "approved":
        if result.modified_count:
            organizer = await db.users.find_one({"user_id": event.get("organizer_id")}, {"_id": 0}) or {}
            if organizer.get("email"):
                send_template_fireforget("organizer_event_approved", organizer["email"], {
                    "organizer_name": organizer.get("name", "organizer"),
                    "event_id": event_id,
                    "event_title": event.get("title", "Your event"),
                }, db)
        # FIRST50 auto-promo runs every time an event is approved — the
        # `_maybe_seed_first50_promo` helper is idempotent on (code,
        # created_by) so a repeat call is a cheap no-op.
        try:
            await _maybe_seed_first50_promo(event)
        except Exception:  # noqa: BLE001 — never break the approval flow
            pass

        # Notify followers of this organizer that a new event was just
        # published. Fire-and-forget; the digest worker will catch missed
        # sends on its weekly run.
        try:
            await _notify_followers_of_new_event(event)
        except Exception as exc:  # noqa: BLE001
            import logging as _l
            _l.getLogger(__name__).warning(f"[follow-notify] failed: {exc}")

        # Referral program — first-event-approved triggers a $50 credit
        # to the REFERRER only (no welcome bonus for the new organizer).
        # Idempotent via `users.referral_credited_at`.
        try:
            from routers.organizer_referrals import maybe_grant_referral_on_first_approval
            await maybe_grant_referral_on_first_approval(event)
        except Exception as exc:  # noqa: BLE001
            import logging as _l
            _l.getLogger(__name__).warning(f"[referral] grant failed: {exc}")
    return {"ok": True}


async def _notify_followers_of_new_event(event: dict) -> int:
    """When an organizer's event is approved, email every follower a one-shot
    'new from <organizer>' alert. Returns how many emails were queued."""
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return 0
    organizer = await db.users.find_one(
        {"user_id": organizer_id},
        {"_id": 0, "user_id": 1, "name": 1},
    ) or {}
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    event_url = f"{origin}/events/{event['event_id']}"
    sent = 0
    async for f in db.follows.find(
        {"organizer_id": organizer_id, "notifications_enabled": {"$ne": False}},
        {"_id": 0, "user_id": 1},
    ):
        u = await db.users.find_one(
            {"user_id": f["user_id"]},
            {"_id": 0, "email": 1, "notification_email": 1, "name": 1},
        )
        if not u:
            continue
        target = u.get("notification_email") or u.get("email")
        if not target:
            continue
        try:
            send_template_fireforget(
                "follower_new_event",
                target,
                {
                    "follower_name": u.get("name") or "there",
                    "organizer_name": organizer.get("name") or "an organizer you follow",
                    "event_title": event.get("title", "New event"),
                    "event_date_iso": event.get("date"),
                    "venue": f"{event.get('venue','')}, {event.get('city','')}",
                    "event_url": event_url,
                },
                db,
            )
            sent += 1
        except Exception:  # noqa: BLE001
            continue
    return sent


async def _maybe_seed_first50_promo(event: dict) -> bool:
    """Create a 10%-off code valid for the first 50 buyers of this event.

    Idempotent — returns False if the organizer already has a `FIRST50` code
    or the event is configured to skip auto-promos.
    """
    import uuid as _uuid
    if event.get("auto_promo_disabled"):
        return False
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return False
    code_str = "FIRST50"
    existing = await db.discount_codes.find_one(
        {"code": code_str, "created_by": organizer_id},
        {"_id": 0, "code_id": 1},
    )
    if existing:
        return False
    # 7-day expiry so the urgency feels real; capped at 50 uses.
    from datetime import timedelta
    expires = (utc_now() + timedelta(days=7)).isoformat()
    await db.discount_codes.insert_one({
        "code_id": f"dc_{_uuid.uuid4().hex[:12]}",
        "code": code_str,
        "kind": "percent",
        "value": 10.0,
        "event_id": event.get("event_id"),
        "max_uses": 50,
        "uses_count": 0,
        "expires_at": expires,
        "restricted_tiers": [],
        "active": True,
        "created_by": organizer_id,
        "auto_generated": True,
        "auto_promo_reason": "first50_on_publish",
        "created_at": utc_now().isoformat(),
    })
    return True


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


class CreateUserIn(BaseModel):
    name: str
    email: str
    password: str
    role: str  # attendee | organizer | admin
    send_welcome_email: bool = True


@router.post("/users")
async def admin_create_user(payload: CreateUserIn, user: dict = Depends(get_current_user)):
    """Admin-only: create a new user with a chosen role (attendee / organizer / admin).

    Use case: onboarding an organizer who can't or won't self-register, or
    seeding a co-admin account. Optionally fires a welcome email so the new
    user gets their credentials and a one-click login link.
    """
    import uuid
    from core import hash_password

    _admin_only(user)
    email = (payload.email or "").lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if not (payload.password or "").strip() or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if payload.role not in ("attendee", "organizer", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "name": (payload.name or "").strip() or email.split("@")[0],
        "role": payload.role,
        "password_hash": hash_password(payload.password),
        "picture": None,
        "created_at": utc_now().isoformat(),
        "created_by_admin": user["user_id"],
        "auth_provider": "password",
        "active": True,
    }
    await db.users.insert_one(doc)

    if payload.send_welcome_email:
        try:
            from emails import send_template_fireforget
            send_template_fireforget(
                "admin_created_account",
                email,
                {
                    "user_name": doc["name"],
                    "user_email": email,
                    "temp_password": payload.password,
                    "role": payload.role,
                    "admin_name": user.get("name") or "An admin",
                },
                db,
            )
        except Exception:
            pass

    # Strip the password_hash AND the BSON _id Mongo inserts on save before returning.
    return {k: v for k, v in doc.items() if k not in ("password_hash", "_id")}


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
    # Optional override — when set, all automated notifications for this user
    # are re-routed to this address. Login email (`email`) stays unchanged.
    # Pass empty string "" to clear the override.
    notification_email: Optional[str] = None


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
    if payload.notification_email is not None:
        # Empty string clears the override; otherwise validate basic shape.
        clean = payload.notification_email.strip().lower()
        if clean and "@" not in clean:
            raise HTTPException(status_code=400, detail="notification_email looks invalid")
        update["notification_email"] = clean or None

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


# ---------- Marketing flyers (organizer / influencer recruitment pitches) ----------
FLYER_KINDS = {"organizer_features_flyer", "influencer_features_flyer"}


@router.get("/marketing/flyer-preview/{kind}", response_class=HTMLResponse)
async def admin_flyer_preview(kind: str, user: dict = Depends(get_current_user)):
    """Returns the rendered HTML of a recruitment flyer so admins can preview
    it in the browser before sending. Mounts at:
      GET /api/admin/marketing/flyer-preview/organizer_features_flyer
      GET /api/admin/marketing/flyer-preview/influencer_features_flyer
    """
    _admin_only(user)
    if kind not in FLYER_KINDS:
        raise HTTPException(status_code=404, detail="Unknown flyer kind")
    builder = EMAIL_TEMPLATES[kind]
    _, html, _ = builder({"name": "Sample Recipient"})
    return HTMLResponse(content=html)


class FlyerSendIn(BaseModel):
    kind: str  # organizer_features_flyer | influencer_features_flyer
    emails: list[str]  # Up to 200 if sending now; up to 5000 if scheduled
    scheduled_for: Optional[str] = None  # ISO datetime; None = send immediately
    label: Optional[str] = None  # Free-form campaign name shown in admin UI


@router.post("/marketing/flyer-send")
async def admin_send_flyer(payload: FlyerSendIn, user: dict = Depends(get_current_user)):
    """Send (or schedule) a recruitment flyer.

    • If `scheduled_for` is omitted, sends immediately via fire-and-forget
      (max 200 recipients — to keep the request fast).
    • If `scheduled_for` is provided, the campaign is queued in
      `flyer_campaigns`; the scheduler picks it up every 60 seconds, sends
      it in 200-recipient batches, and stamps progress on the doc. Allows
      up to 5000 recipients per scheduled campaign.

    Every send is recorded in `flyer_campaigns` with `resend_ids[email]` so
    the Resend webhook can map opens/clicks back for per-campaign analytics.
    """
    _admin_only(user)
    if payload.kind not in FLYER_KINDS:
        raise HTTPException(status_code=400, detail="Unknown flyer kind")
    # Normalize + dedupe (case-insensitive)
    seen, emails = set(), []
    for raw in payload.emails:
        e = (raw or "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            emails.append(e)
    if not emails:
        raise HTTPException(status_code=400, detail="At least one recipient required")

    scheduled_dt = None
    if payload.scheduled_for:
        try:
            scheduled_dt = datetime.fromisoformat(payload.scheduled_for.replace("Z", "+00:00"))
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduled_for ISO timestamp")
        if scheduled_dt <= utc_now() + timedelta(minutes=1):
            raise HTTPException(status_code=400, detail="scheduled_for must be at least 1 minute in the future")
        if len(emails) > 5000:
            raise HTTPException(status_code=400, detail="Max 5000 recipients per scheduled campaign")
    else:
        if len(emails) > 200:
            raise HTTPException(status_code=400, detail="Max 200 recipients when sending now — schedule it or batch it")

    # Cheap name lookup so the salutation reads naturally for known users.
    name_lookup: dict[str, str] = {}
    async for u in db.users.find({"email": {"$in": emails}}, {"_id": 0, "email": 1, "name": 1}):
        name_lookup[u["email"]] = u.get("name") or "there"

    campaign_id = f"cmp_{uuid.uuid4().hex[:12]}"
    base_doc = {
        "campaign_id": campaign_id,
        "kind": payload.kind,
        "label": (payload.label or "").strip()[:80] or None,
        "emails": emails,
        "total": len(emails),
        "scheduled_for": scheduled_dt.isoformat() if scheduled_dt else None,
        "created_by": user["user_id"],
        "created_at": utc_now().isoformat(),
        "sent_count": 0,
        "failed_count": 0,
        "resend_ids": {},  # email -> resend message id (for webhook lookup)
        "status": "scheduled" if scheduled_dt else "sending",
    }
    await db.flyer_campaigns.insert_one(base_doc)

    if scheduled_dt:
        return {
            "status": "scheduled",
            "campaign_id": campaign_id,
            "scheduled_for": scheduled_dt.isoformat(),
            "total_recipients": len(emails),
        }

    # Send immediately, in-process.
    sent, failed, resend_map = 0, 0, {}
    for email in emails:
        try:
            res = await send_template(payload.kind, email, {"name": name_lookup.get(email, "there")}, db)
            if res.get("status") == "sent":
                sent += 1
                rid = res.get("resend_id")
                if rid:
                    resend_map[email.replace(".", "_DOT_")] = rid  # mongo keys can't contain dots
            else:
                failed += 1
        except Exception:
            failed += 1
    await db.flyer_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {
            "status": "sent",
            "sent_count": sent,
            "failed_count": failed,
            "resend_ids": resend_map,
            "completed_at": utc_now().isoformat(),
        }},
    )
    return {"status": "sent", "campaign_id": campaign_id, "sent": sent, "failed": failed, "total_recipients": len(emails)}


@router.get("/marketing/flyer-campaigns")
async def admin_list_flyer_campaigns(user: dict = Depends(get_current_user), limit: int = 50):
    """List recent flyer campaigns with per-campaign open/click stats pulled
    from `email_events` (populated by the Resend webhook). Stats are computed
    on demand so they reflect events that arrived after the send completed.
    """
    _admin_only(user)
    cur = db.flyer_campaigns.find({}, {"_id": 0, "emails": 0}).sort("created_at", -1).limit(max(1, min(100, limit)))
    items = [doc async for doc in cur]
    # Compute opens / clicks per campaign by joining resend_ids → email_events
    for c in items:
        ids = list((c.get("resend_ids") or {}).values())
        if not ids:
            c["opened"] = 0
            c["clicked"] = 0
            c["bounced"] = 0
            continue
        events = await db.email_events.aggregate([
            {"$match": {"resend_id": {"$in": ids}}},
            {"$group": {"_id": "$event_type", "ids": {"$addToSet": "$resend_id"}}},
        ]).to_list(20)
        c["opened"] = next((len(e["ids"]) for e in events if e["_id"] in ("email.opened", "opened")), 0)
        c["clicked"] = next((len(e["ids"]) for e in events if e["_id"] in ("email.clicked", "clicked")), 0)
        c["bounced"] = next((len(e["ids"]) for e in events if e["_id"] in ("email.bounced", "bounced")), 0)
    return {"items": items}


@router.delete("/marketing/flyer-campaigns/{campaign_id}")
async def admin_cancel_flyer_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    """Cancel a *scheduled* campaign before it dispatches. No-op if the
    campaign already started sending.
    """
    _admin_only(user)
    res = await db.flyer_campaigns.update_one(
        {"campaign_id": campaign_id, "status": "scheduled"},
        {"$set": {"status": "cancelled", "cancelled_at": utc_now().isoformat()}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=400, detail="Campaign already dispatched or not found")
    return {"cancelled": campaign_id}


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



# ---------- Revenue dashboard (admin's own platform-fee P&L) ----------
@router.get("/revenue")
async def admin_revenue(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Per-booking revenue breakdown so admin can see their platform-fee
    cut without leaving Allsale.

    Stripe natively doesn't show our 1% + $0.50 platform fee as a line
    item (the architecture today is "platform-keeps-100%, organizer
    receives manual payouts"). This endpoint reconstructs the breakdown
    from `bookings.amount`, `bookings.face_value`, and the historical
    fee snapshot stored at checkout time.

    Returns:
        {
          items: [...per booking row with breakdown...],
          totals: {gross, stripe_fees, platform_fees, organizer_share, count},
          currency: "NZD",     # majority currency in the slice; mixed is flagged
        }
    """
    _admin_only(user)

    q: dict = {"status": "paid"}
    if start:
        q["paid_at"] = {"$gte": start}
    if end:
        q.setdefault("paid_at", {})["$lte"] = end

    rows: list = []
    totals = {
        "gross": 0.0, "stripe_fees": 0.0, "platform_fees": 0.0,
        "organizer_share": 0.0, "count": 0,
    }
    currencies: dict = {}

    # Pull bookings + event titles + organizer info in one pass.
    cursor = db.bookings.find(q, {"_id": 0}).sort("paid_at", -1).skip(int(offset)).limit(int(limit))
    async for b in cursor:
        gross = float(b.get("amount") or 0)
        face = float(b.get("face_value") or 0)
        # Reconstruct fees: prefer stored breakdown, fall back to a clean compute.
        platform_fee = b.get("platform_fee")
        stripe_fee = b.get("stripe_fee_estimated") or b.get("stripe_fee")

        event_doc = await db.events.find_one(
            {"event_id": b.get("event_id")},
            {"_id": 0, "title": 1, "organizer_name": 1, "organizer_id": 1, "absorb_fees": 1},
        ) or {}
        absorb_fees = bool(event_doc.get("absorb_fees"))

        if platform_fee is None or stripe_fee is None:
            # Lazy import so tests don't pay for it on cold start.
            from fees import compute_fees
            plat = await db.platform_settings.find_one({"key": "commission"}, {"_id": 0}) or {}
            # Legacy bookings don't store `face_value`. In the buyer-pays-fees
            # model the buyer paid `gross` and the organizer receives a smaller
            # face_value — so we need to invert the gross-up. Approximation:
            # compute_fees(face) gives buyer_total. We want buyer_total ≈ gross.
            # `face = gross / (1 + platform_pct + (stripe_pct + flat/face))`
            # is messy with the flat fee, so we just iterate 3x — converges fast.
            if not face:
                trial = gross
                for _ in range(4):
                    fb_trial = compute_fees(
                        trial, b.get("currency") or "NZD",
                        platform_pct=plat.get("commission_percent"),
                        platform_flat=plat.get("commission_flat_fee_per_ticket"),
                        absorb_fees=absorb_fees,
                    )
                    if fb_trial.buyer_total <= 0:
                        break
                    trial = trial * (gross / fb_trial.buyer_total)
                face = trial
            fb = compute_fees(
                face, b.get("currency") or "NZD",
                platform_pct=plat.get("commission_percent"),
                platform_flat=plat.get("commission_flat_fee_per_ticket"),
                absorb_fees=absorb_fees,
            )
            platform_fee = float(fb.platform_fee)
            stripe_fee = float(fb.stripe_fee)
            face = float(fb.face_value)
            # Final safety: force the row math to reconcile exactly with `gross`.
            # Tiny iteration error otherwise leaves a few cents un-attributed.
            remainder = gross - (platform_fee + stripe_fee + face)
            face += remainder

        # If face_value not stored on the booking, reverse-engineer it.
        if not face:
            face = max(0.0, gross - float(platform_fee or 0) - float(stripe_fee or 0))

        currency = (b.get("currency") or "NZD").upper()
        currencies[currency] = currencies.get(currency, 0) + 1

        # Use the event_doc fetched above (already loaded for absorb_fees).
        ev = event_doc

        rows.append({
            "booking_id": b.get("booking_id"),
            "paid_at": b.get("paid_at"),
            "event_id": b.get("event_id"),
            "event_title": ev.get("title") or "(deleted)",
            "organizer_name": ev.get("organizer_name") or "—",
            "absorb_fees": bool(ev.get("absorb_fees")),
            "buyer_email": b.get("user_email"),
            "quantity": int(b.get("quantity") or 1),
            "currency": currency,
            "gross": round(gross, 2),
            "stripe_fee": round(float(stripe_fee or 0), 2),
            "platform_fee": round(float(platform_fee or 0), 2),
            "organizer_share": round(face, 2),
            "stripe_session_id": b.get("stripe_session_id"),
        })
        totals["gross"] += gross
        totals["stripe_fees"] += float(stripe_fee or 0)
        totals["platform_fees"] += float(platform_fee or 0)
        totals["organizer_share"] += face
        totals["count"] += 1

    for k in ("gross", "stripe_fees", "platform_fees", "organizer_share"):
        totals[k] = round(totals[k], 2)

    # Majority currency for the headline cards. If a slice has mixed
    # currencies, the page will badge each row anyway — this is for the KPIs.
    headline_currency = max(currencies.items(), key=lambda kv: kv[1])[0] if currencies else "NZD"

    return {
        "items": rows,
        "totals": totals,
        "currency": headline_currency,
        "mixed_currencies": len(currencies) > 1,
        "range": {"start": start, "end": end},
    }


@router.get("/revenue/headline")
async def admin_revenue_headline(user: dict = Depends(get_current_user)):
    """Lightweight headline KPI: total platform fees collected THIS MONTH
    vs. previous month + delta. Powers the big "earned this month" hero
    card at the top of /admin/revenue so admin can see their cut at a
    glance without scrolling through the per-booking table.

    Returns:
        {
          current_month:  {label, start, end, gross, platform_fees, count, currency},
          previous_month: {label, start, end, gross, platform_fees, count, currency},
          delta_percent:  +12.3,   # platform_fees: current vs previous (null if prev=0)
          today_fees:     12.34,   # today's platform fees in headline_currency
        }
    """
    _admin_only(user)

    now = utc_now()
    cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Previous month start/end via calendar.
    if cur_start.month == 1:
        prev_start = cur_start.replace(year=cur_start.year - 1, month=12)
    else:
        prev_start = cur_start.replace(month=cur_start.month - 1)
    prev_end = cur_start  # exclusive
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def _bucket(start_dt: "datetime", end_dt: Optional["datetime"]) -> dict:
        """Aggregate paid bookings in [start, end) — uses prefix string compare
        on `paid_at` (ISO 8601), which is cheap and correctly ordered."""
        q: dict = {"status": "paid", "paid_at": {"$gte": start_dt.isoformat()}}
        if end_dt is not None:
            q["paid_at"]["$lt"] = end_dt.isoformat()
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": {"$ifNull": ["$currency", "NZD"]},
                "gross": {"$sum": {"$ifNull": ["$amount", 0]}},
                "platform_fees": {"$sum": {"$ifNull": ["$platform_fee", 0]}},
                "stripe_fees": {"$sum": {"$ifNull": ["$stripe_fee_estimated", 0]}},
                "count": {"$sum": 1},
            }},
        ]
        by_ccy: dict = {}
        async for row in db.bookings.aggregate(pipeline):
            by_ccy[(row["_id"] or "NZD").upper()] = row
        if not by_ccy:
            return {"gross": 0.0, "platform_fees": 0.0, "stripe_fees": 0.0, "count": 0, "currency": "NZD"}
        majority = max(by_ccy.items(), key=lambda kv: kv[1]["count"])
        return {
            "gross": round(float(majority[1]["gross"]), 2),
            "platform_fees": round(float(majority[1]["platform_fees"]), 2),
            "stripe_fees": round(float(majority[1]["stripe_fees"]), 2),
            "count": int(majority[1]["count"]),
            "currency": majority[0],
        }

    current = await _bucket(cur_start, None)
    previous = await _bucket(prev_start, prev_end)
    today = await _bucket(today_start, None)

    delta = None
    if previous["platform_fees"] > 0:
        delta = round(
            ((current["platform_fees"] - previous["platform_fees"]) / previous["platform_fees"]) * 100, 1
        )

    return {
        "current_month": {
            **current,
            "label": cur_start.strftime("%B %Y"),
            "start": cur_start.date().isoformat(),
            "end": now.date().isoformat(),
        },
        "previous_month": {
            **previous,
            "label": prev_start.strftime("%B %Y"),
            "start": prev_start.date().isoformat(),
            "end": (prev_end - timedelta(days=1)).date().isoformat(),
        },
        "delta_percent": delta,
        "today_fees": today["platform_fees"],
        "today_count": today["count"],
    }


# ---------- Stripe Connect Status Tracker (admin) ----------
# Lets the admin see which organizers haven't completed Stripe Connect
# onboarding yet so they can chase the high-revenue ones onto the new
# Phase B (destination charges) flow. Without this, organizers' charges
# keep landing on Allsale's master account and never appear in Stripe's
# native "Collected fees" tab.

@router.get("/stripe-connect-status")
async def admin_stripe_connect_status(user: dict = Depends(get_current_user)):
    """List every organizer who has ever created an event, with their
    Stripe Connect status and revenue stats.

    Status values:
      🔴 not_connected         — no stripe_account_id on the user
      🟡 onboarding_incomplete — has account but charges_enabled=false
      ✅ connected              — charges_enabled=true (Phase B will route)

    Sorted by lifetime_revenue DESC so admin can chase the biggest revenue
    organizers first.
    """
    _admin_only(user)

    # 1) Find every user who owns at least one event.
    organizer_ids = await db.events.distinct("organizer_id")
    if not organizer_ids:
        return {"items": [], "summary": {"total": 0, "connected": 0, "onboarding": 0, "not_connected": 0}}

    # 2) Pre-aggregate paid-booking totals per organizer in one pipeline.
    revenue_by_org: dict = {}
    pipeline = [
        {"$match": {"status": "paid"}},
        {"$lookup": {
            "from": "events", "localField": "event_id",
            "foreignField": "event_id", "as": "_event"
        }},
        {"$unwind": "$_event"},
        {"$group": {
            "_id": "$_event.organizer_id",
            "bookings_count": {"$sum": 1},
            "tickets_sold": {"$sum": {"$ifNull": ["$quantity", 1]}},
            "lifetime_revenue": {"$sum": {"$ifNull": ["$amount", 0]}},
            "platform_fees_collected": {"$sum": {"$ifNull": ["$platform_fee", 0]}},
            "last_paid_at": {"$max": "$paid_at"},
            "currencies": {"$addToSet": "$currency"},
        }},
    ]
    async for row in db.bookings.aggregate(pipeline):
        revenue_by_org[row["_id"]] = row

    # 3) Build the response row per organizer.
    rows: list = []
    summary = {"total": 0, "connected": 0, "onboarding": 0, "not_connected": 0}
    async for u in db.users.find(
        {"user_id": {"$in": list(organizer_ids)}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "phone": 1,
         "stripe_account_id": 1, "stripe_charges_enabled": 1,
         "stripe_payouts_enabled": 1, "stripe_details_submitted": 1,
         "stripe_nudge_sent_at": 1, "created_at": 1},
    ):
        acct = u.get("stripe_account_id") or None
        charges = bool(u.get("stripe_charges_enabled"))
        if charges:
            status = "connected"
        elif acct:
            status = "onboarding_incomplete"
        else:
            status = "not_connected"
        summary[status if status != "onboarding_incomplete" else "onboarding"] += 1
        summary["total"] += 1

        rev = revenue_by_org.get(u["user_id"]) or {}
        events_count = await db.events.count_documents({"organizer_id": u["user_id"]})
        rows.append({
            "user_id": u["user_id"],
            "email": u.get("email"),
            "name": u.get("name") or u.get("email"),
            "phone": u.get("phone"),
            "stripe_account_id": acct,
            "stripe_charges_enabled": charges,
            "stripe_payouts_enabled": bool(u.get("stripe_payouts_enabled")),
            "stripe_details_submitted": bool(u.get("stripe_details_submitted")),
            "status": status,
            "events_count": events_count,
            "bookings_count": int(rev.get("bookings_count") or 0),
            "tickets_sold": int(rev.get("tickets_sold") or 0),
            "lifetime_revenue": round(float(rev.get("lifetime_revenue") or 0), 2),
            "platform_fees_collected": round(float(rev.get("platform_fees_collected") or 0), 2),
            "currency": (rev.get("currencies") or ["NZD"])[0] if rev.get("currencies") else "NZD",
            "last_paid_at": rev.get("last_paid_at"),
            "last_reminder_sent_at": u.get("stripe_nudge_sent_at"),
        })

    # Sort biggest revenue first, then by status (not_connected first within ties).
    status_rank = {"not_connected": 0, "onboarding_incomplete": 1, "connected": 2}
    rows.sort(key=lambda r: (-r["lifetime_revenue"], status_rank.get(r["status"], 9)))

    return {"items": rows, "summary": summary}


class _RemindIn(BaseModel):
    user_ids: Optional[list[str]] = None  # None = remind all not_connected with revenue


@router.post("/stripe-connect-status/remind")
async def admin_send_stripe_reminders(payload: _RemindIn, user: dict = Depends(get_current_user)):
    """Send the `organizer_stripe_setup_nudge` email to a list of organizers
    (or to ALL not-connected organizers with revenue when `user_ids` is None).

    Rate-limited via the existing email_logs retry-on-429 logic in emails.py
    so a 200-recipient blast doesn't get truncated by Resend's 2 req/sec cap.
    """
    _admin_only(user)
    target_ids = payload.user_ids or []

    if not target_ids:
        # Default target: every organizer who has paid revenue + isn't connected.
        organizer_ids_with_revenue = []
        async for row in db.bookings.aggregate([
            {"$match": {"status": "paid"}},
            {"$lookup": {"from": "events", "localField": "event_id", "foreignField": "event_id", "as": "_e"}},
            {"$unwind": "$_e"},
            {"$group": {"_id": "$_e.organizer_id"}},
        ]):
            organizer_ids_with_revenue.append(row["_id"])
        async for u in db.users.find(
            {
                "user_id": {"$in": organizer_ids_with_revenue},
                "$or": [
                    {"stripe_charges_enabled": {"$ne": True}},
                    {"stripe_charges_enabled": {"$exists": False}},
                ],
            },
            {"_id": 0, "user_id": 1},
        ):
            target_ids.append(u["user_id"])

    if not target_ids:
        return {"sent": 0, "skipped": 0, "errors": []}

    sent = 0
    skipped = 0
    errors: list = []
    now_iso = utc_now().isoformat()
    async for u in db.users.find(
        {"user_id": {"$in": target_ids}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1,
         "stripe_charges_enabled": 1, "stripe_account_id": 1},
    ):
        if not u.get("email"):
            skipped += 1
            continue
        # Re-check status: if they completed onboarding since the admin opened
        # the tab, skip (idempotent — never spam someone who already finished).
        if u.get("stripe_charges_enabled"):
            skipped += 1
            continue
        try:
            # Surface the count of upcoming events on this organizer so the
            # email body reads honestly ("you have N events coming up...").
            from datetime import datetime as _dt
            now_iso_for_query = _dt.now(timezone.utc).isoformat()
            events_count = await db.events.count_documents({
                "organizer_id": u["user_id"],
                "date": {"$gte": now_iso_for_query[:10]},
            })
            next_event = await db.events.find_one(
                {"organizer_id": u["user_id"], "date": {"$gte": now_iso_for_query[:10]}},
                {"_id": 0, "title": 1, "date": 1},
                sort=[("date", 1)],
            )
            send_template_fireforget(
                "organizer_stripe_setup_nudge",
                u["email"],
                {
                    "organizer_name": u.get("name") or "Organizer",
                    "events_count": max(1, events_count),
                    "next_event_title": (next_event or {}).get("title") or "your next event",
                    "next_event_date": (next_event or {}).get("date") or "",
                    "dashboard_url": None,  # template falls back to /organizer
                },
                db,
            )
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"stripe_nudge_sent_at": now_iso, "stripe_nudge_sent_by": user["user_id"]}},
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 — log and keep blasting
            errors.append({"user_id": u["user_id"], "error": str(exc)[:120]})

    return {"sent": sent, "skipped": skipped, "errors": errors, "queued_at": now_iso}

