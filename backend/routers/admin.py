"""Admin endpoints: events moderation + user management."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, event_to_public, utc_now

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
    await db.events.update_one({"event_id": event_id}, {"$set": {"status": "approved"}})
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
