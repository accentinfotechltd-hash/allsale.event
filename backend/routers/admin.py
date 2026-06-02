"""Admin endpoints: events moderation + user management."""
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
