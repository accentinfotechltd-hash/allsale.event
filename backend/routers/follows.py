"""Follow-organizer feature.

Attendees can follow organizers to:
  - See follower count on event detail pages (social proof)
  - Receive a weekly Sunday email digest of new events from organizers
    they follow
  - Get notified the moment a new event from a followed organizer is
    approved (in-app + email — opt-out per organizer)

Endpoints:
  POST   /api/organizers/{organizer_id}/follow      (auth required)
  DELETE /api/organizers/{organizer_id}/follow      (auth required)
  GET    /api/organizers/{organizer_id}/follow      (auth required, optional)
       Returns {following: bool, follower_count: int}
  GET    /api/me/following                          (auth required)
       Returns the list of organizers I follow + their upcoming-event counts.
  GET    /api/organizers/{organizer_id}/public
       Public bio + follower_count + upcoming events. Used by attendees
       browsing an organizer page.

Storage:
  - `follows` collection: {user_id, organizer_id, created_at}
                          (compound unique index on user_id+organizer_id)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, utc_now, event_to_public

logger = logging.getLogger(__name__)
router = APIRouter(tags=["follows"])


# ---------------------------------------------------------------------------
# Follow / unfollow
# ---------------------------------------------------------------------------

async def _follower_count(organizer_id: str) -> int:
    return await db.follows.count_documents({"organizer_id": organizer_id})


@router.post("/organizers/{organizer_id}/follow")
async def follow_organizer(organizer_id: str, user: dict = Depends(get_current_user)):
    if organizer_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="You can't follow yourself.")
    org = await db.users.find_one(
        {"user_id": organizer_id},
        {"_id": 0, "user_id": 1, "role": 1, "name": 1},
    )
    if not org:
        raise HTTPException(status_code=404, detail="Organizer not found")
    if org.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=400, detail="That account isn't an organizer.")

    # Upsert so repeated POSTs are idempotent.
    await db.follows.update_one(
        {"user_id": user["user_id"], "organizer_id": organizer_id},
        {"$setOnInsert": {
            "user_id": user["user_id"],
            "organizer_id": organizer_id,
            "created_at": utc_now().isoformat(),
        }},
        upsert=True,
    )
    return {
        "following": True,
        "organizer_id": organizer_id,
        "organizer_name": org.get("name"),
        "follower_count": await _follower_count(organizer_id),
    }


@router.delete("/organizers/{organizer_id}/follow")
async def unfollow_organizer(organizer_id: str, user: dict = Depends(get_current_user)):
    await db.follows.delete_one({"user_id": user["user_id"], "organizer_id": organizer_id})
    return {
        "following": False,
        "organizer_id": organizer_id,
        "follower_count": await _follower_count(organizer_id),
    }


@router.get("/organizers/{organizer_id}/follow")
async def get_follow_state(organizer_id: str, user: dict = Depends(get_current_user)):
    is_following = bool(await db.follows.find_one(
        {"user_id": user["user_id"], "organizer_id": organizer_id},
        {"_id": 1},
    ))
    return {
        "following": is_following,
        "organizer_id": organizer_id,
        "follower_count": await _follower_count(organizer_id),
    }


@router.get("/me/following")
async def my_following(user: dict = Depends(get_current_user)):
    """List the organizers I follow, with their name + upcoming-event count."""
    items = []
    async for f in db.follows.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        org = await db.users.find_one(
            {"user_id": f["organizer_id"]},
            {"_id": 0, "user_id": 1, "name": 1, "picture": 1},
        )
        if not org:
            continue
        upcoming = await db.events.count_documents({
            "organizer_id": f["organizer_id"],
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": utc_now().isoformat()},
        })
        items.append({
            "organizer_id": org["user_id"],
            "organizer_name": org.get("name"),
            "organizer_picture": org.get("picture"),
            "upcoming_count": upcoming,
            "followed_at": f.get("created_at"),
        })
    return {"items": items, "total": len(items)}


@router.get("/organizers/{organizer_id}/public")
async def organizer_public_page(organizer_id: str):
    """Public organizer profile — bio + follower count + upcoming events.

    No auth required so it's shareable.
    """
    org = await db.users.find_one(
        {"user_id": organizer_id},
        {"_id": 0, "user_id": 1, "name": 1, "role": 1, "picture": 1, "bio": 1, "created_at": 1},
    )
    if not org or org.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=404, detail="Organizer not found")

    upcoming = []
    async for e in db.events.find(
        {
            "organizer_id": organizer_id,
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": utc_now().isoformat()},
        },
        {"_id": 0},
    ).sort("date", 1).limit(50):
        upcoming.append(event_to_public(e))

    return {
        "organizer": {
            "user_id": org["user_id"],
            "name": org.get("name"),
            "picture": org.get("picture"),
            "bio": org.get("bio"),
            "joined_at": org.get("created_at"),
        },
        "follower_count": await _follower_count(organizer_id),
        "upcoming_count": len(upcoming),
        "upcoming_events": upcoming,
    }
