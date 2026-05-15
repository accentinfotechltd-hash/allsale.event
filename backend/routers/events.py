"""Event endpoints: list, featured, categories, detail, create."""
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from core import db, get_current_user, require_role, utc_now, event_to_public
from models import EventIn

router = APIRouter(tags=["events"])


@router.get("/events")
async def list_events(
    q: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 50,
):
    query: Dict[str, Any] = {"status": {"$in": ["approved", "published"]}}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"venue": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    cursor = db.events.find(query, {"_id": 0}).sort("date", 1).limit(limit)
    return [event_to_public(e) async for e in cursor]


@router.get("/events/featured")
async def featured_events():
    cursor = db.events.find(
        {"status": {"$in": ["approved", "published"]}, "featured": True}, {"_id": 0},
    ).limit(6)
    items = [event_to_public(e) async for e in cursor]
    if not items:
        cursor = db.events.find({"status": {"$in": ["approved", "published"]}}, {"_id": 0}).limit(6)
        items = [event_to_public(e) async for e in cursor]
    return items


@router.get("/events/categories")
async def event_categories():
    return [
        {"id": "music", "name": "Music", "image": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800"},
        {"id": "comedy", "name": "Comedy", "image": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=800"},
        {"id": "sports", "name": "Sports", "image": "https://images.unsplash.com/photo-1471295253337-3ceaaedca402?w=800"},
        {"id": "theater", "name": "Theater", "image": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=800"},
        {"id": "tech", "name": "Tech & Conferences", "image": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800"},
        {"id": "workshops", "name": "Workshops", "image": "https://images.unsplash.com/photo-1552581234-26160f608093?w=800"},
        {"id": "festivals", "name": "Festivals", "image": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800"},
        {"id": "arts", "name": "Arts & Culture", "image": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=800"},
    ]


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    if e.get("has_seatmap"):
        now_iso = utc_now().isoformat()
        booked_seats = []
        held_seats = []
        async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "booked"}, {"_id": 0, "seat_id": 1},
        ):
            booked_seats.append(r["seat_id"])
        async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "held", "expires_at": {"$gte": now_iso}},
            {"_id": 0, "seat_id": 1},
        ):
            held_seats.append(r["seat_id"])
        e["booked_seats"] = booked_seats
        e["held_seats"] = held_seats
    return event_to_public(e)


@router.post("/events")
async def create_event(payload: EventIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    doc = {
        "event_id": event_id,
        "organizer_id": user["user_id"],
        "organizer_name": user["name"],
        "title": payload.title,
        "description": payload.description,
        "category": payload.category,
        "venue": payload.venue,
        "city": payload.city,
        "date": payload.date,
        "image_url": payload.image_url,
        "banner_url": payload.banner_url or payload.image_url,
        "tiers": payload.tiers,
        "has_seatmap": payload.has_seatmap,
        "seat_rows": payload.seat_rows,
        "seat_cols": payload.seat_cols,
        "seat_price": payload.seat_price,
        "aisles": payload.aisles,
        "seat_map_image_url": payload.seat_map_image_url,
        "status": "approved" if user.get("role") == "admin" else "pending",
        "featured": False,
        "created_at": utc_now().isoformat(),
    }
    await db.events.insert_one(doc)
    return event_to_public(doc)
