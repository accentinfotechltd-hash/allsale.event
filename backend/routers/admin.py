"""Admin endpoints: list, approve, reject, feature events."""
from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, event_to_public

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_only(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


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
