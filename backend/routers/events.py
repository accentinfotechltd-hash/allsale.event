"""Event endpoints: list, featured, categories, detail, create."""
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now, event_to_public, compute_tier_effective_price
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
    items = [event_to_public(e) async for e in cursor]
    # Annotate sold-out events with waitlist_count (cheap aggregate)
    for e in items:
        if not e.get("has_seatmap") and e.get("tiers"):
            wcount = await db.waitlist_entries.count_documents(
                {"event_id": e["event_id"], "status": "waiting"}
            )
            if wcount > 0:
                e["waitlist_count"] = wcount
    return items


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
        {"id": "movies", "name": "Movies", "image": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800"},
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
        e["sold_out"] = False  # Seatmap events don't surface aggregate sold-out
    else:
        # For tier-based events, compute sold/remaining per tier and aggregate sold_out flag
        now_iso = utc_now().isoformat()
        tier_status = []
        any_remaining = False
        any_surging = False
        for t in e.get("tiers", []):
            sold = 0
            async for b in db.bookings.find(
                {"event_id": event_id, "tier_name": t["name"], "status": {"$in": ["paid", "confirmed", "pending"]}},
                {"_id": 0, "quantity": 1, "hold_expires_at": 1, "status": 1},
            ):
                if b.get("status") == "pending" and (b.get("hold_expires_at") or "") < now_iso:
                    continue
                sold += b.get("quantity", 0)
            remaining = max(0, t.get("capacity", 0) - sold)
            if remaining > 0:
                any_remaining = True
            eff_price, surging = compute_tier_effective_price(e, t, sold)
            if surging:
                any_surging = True
                t["effective_price"] = eff_price
                t["surging"] = True
            tier_status.append({"name": t["name"], "sold": sold, "remaining": remaining, "effective_price": eff_price, "surging": surging})
        e["tier_status"] = tier_status
        e["sold_out"] = (not any_remaining) and bool(e.get("tiers"))
        e["surging"] = any_surging
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


class DynamicPricingIn(BaseModel):
    enabled: bool
    surge_threshold_pct: float = Field(default=30.0, ge=5, le=90)
    surge_multiplier: float = Field(default=1.2, ge=1.01, le=3.0)


@router.patch("/organizer/events/{event_id}/dynamic-pricing")
async def set_dynamic_pricing(event_id: str, payload: DynamicPricingIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {"dynamic_pricing": {
            "enabled": payload.enabled,
            "surge_threshold_pct": payload.surge_threshold_pct,
            "surge_multiplier": payload.surge_multiplier,
        }}},
    )
    return {"ok": True, "dynamic_pricing": payload.model_dump()}
