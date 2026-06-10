"""Event endpoints: list, featured, categories, detail, create."""
import os
import uuid
from datetime import timedelta
from typing import Optional, Dict, Any
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now, event_to_public, compute_tier_effective_price
from models import EventIn

router = APIRouter(tags=["events"])

# An event is considered "finished" and archived from public listings this many
# hours after its start `date`. We use a buffer (rather than `date < now`) so
# same-day events don't vanish the moment they start. 24h covers most multi-day
# festivals; tweak via env if you ever want shorter/longer.
EVENT_FINISHED_GRACE_HOURS = int(os.environ.get("EVENT_FINISHED_GRACE_HOURS", "24"))


def _event_finished_cutoff_iso() -> str:
    """Events with `date` older than this ISO string are considered finished."""
    return (utc_now() - timedelta(hours=EVENT_FINISHED_GRACE_HOURS)).isoformat()


def _is_event_past(event_date: Optional[str]) -> bool:
    if not event_date:
        return False
    return event_date < _event_finished_cutoff_iso()


@router.get("/events")
async def list_events(
    q: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    past: bool = False,
    limit: int = 50,
):
    query: Dict[str, Any] = {"status": {"$in": ["approved", "published"]}}
    cutoff_iso = _event_finished_cutoff_iso()
    if past:
        # Finished events only — newest first so the most recent show up top.
        query["date"] = {"$lt": cutoff_iso}
        sort_spec = [("date", -1)]
    else:
        # Upcoming + still-running events (within the grace window).
        query["date"] = {"$gte": cutoff_iso}
        sort_spec = [("date", 1)]
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
    cursor = db.events.find(query, {"_id": 0}).sort(sort_spec).limit(limit)
    items = [event_to_public(e) async for e in cursor]
    # Annotate events with waitlist_count (cheap aggregate) — only meaningful
    # for upcoming events; skip for past listings.
    if not past:
        for e in items:
            wcount = await db.waitlist_entries.count_documents(
                {"event_id": e["event_id"], "status": "waiting"}
            )
            if wcount > 0:
                e["waitlist_count"] = wcount
    else:
        for e in items:
            e["is_past"] = True
    return items


@router.get("/events/featured")
async def featured_events():
    cutoff_iso = _event_finished_cutoff_iso()
    base_q = {
        "status": {"$in": ["approved", "published"]},
        "date": {"$gte": cutoff_iso},
    }
    cursor = db.events.find({**base_q, "featured": True}, {"_id": 0}).limit(6)
    items = [event_to_public(e) async for e in cursor]
    if not items:
        cursor = db.events.find(base_q, {"_id": 0}).sort("date", 1).limit(6)
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


@router.get("/events/stats/public")
async def public_event_stats():
    """Cheap public counter used by the landing-page hero chip
    ("Live · N events on sale"). Counts only approved + future events so the
    number always represents tickets a visitor can actually buy right now.
    """
    now_iso = utc_now().isoformat()
    live_count = await db.events.count_documents({
        "status": {"$in": ["approved", "published"]},
        "date": {"$gte": now_iso},
    })
    return {"live_events": live_count}


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
            {"event_id": event_id, "status": {"$in": ["booked", "blocked"]}}, {"_id": 0, "seat_id": 1},
        ):
            booked_seats.append(r["seat_id"])
        async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "held", "expires_at": {"$gte": now_iso}},
            {"_id": 0, "seat_id": 1},
        ):
            held_seats.append(r["seat_id"])
        e["booked_seats"] = booked_seats
        e["held_seats"] = held_seats
        # Sold-out = every non-aisle seat is locked
        rows = e.get("seat_rows", 0)
        cols = e.get("seat_cols", 0)
        aisles = set(e.get("aisles") or [])
        total_non_aisle = max(0, rows * cols - len(aisles))
        locked = len({*booked_seats, *held_seats})
        e["sold_out"] = total_non_aisle > 0 and locked >= total_non_aisle
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
    e["is_past"] = _is_event_past(e.get("date"))
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
        "seatmap_curved": payload.seatmap_curved,
        "seatmap_numbering_rtl": payload.seatmap_numbering_rtl,
        "seatmap_sections": payload.seatmap_sections,
        "seatmap_backdrop_opacity": payload.seatmap_backdrop_opacity,
        "seatmap_backdrop_offset_y": payload.seatmap_backdrop_offset_y,
        "seatmap_backdrop_offset_x": payload.seatmap_backdrop_offset_x,
        "seatmap_backdrop_scale": payload.seatmap_backdrop_scale,
        "status": "approved" if user.get("role") == "admin" else "pending",
        "featured": False,
        "created_at": utc_now().isoformat(),
    }
    await db.events.insert_one(doc)
    # Notify all admins when a new event lands in the moderation queue.
    if doc["status"] == "pending":
        try:
            from emails import send_template_fireforget
            cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
            origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
            admin_url = f"{origin}/admin"
            async for admin in db.users.find(
                {"role": "admin"}, {"_id": 0, "email": 1, "name": 1}
            ):
                send_template_fireforget(
                    "admin_new_event_submitted",
                    admin.get("email"),
                    {
                        "admin_name": admin.get("name") or "Admin",
                        "event_title": doc["title"],
                        "organizer_name": doc.get("organizer_name") or "Organizer",
                        "venue": f"{doc.get('venue','')}, {doc.get('city','')}",
                        "event_date_iso": doc["date"],
                        "admin_url": admin_url,
                    },
                    db,
                )
        except Exception as exc:  # pragma: no cover
            from core import logger as _log
            _log.warning(f"[events] admin notify failed: {exc}")
    return event_to_public(doc)


@router.patch("/events/{event_id}")
async def update_event(event_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Edit an event. Owner, admin or team members with manager+ rights can edit.

    Body is a partial dict of EventIn-compatible fields. Unknown keys are
    silently dropped to keep this forgiving for the frontend.
    """
    from routers.team import user_can_manage_event
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")

    EDITABLE = {
        "title", "description", "category", "venue", "city", "date",
        "image_url", "banner_url", "tiers",
        "has_seatmap", "seat_rows", "seat_cols", "seat_price",
        "aisles", "seat_map_image_url",
        "seatmap_curved", "seatmap_numbering_rtl", "seatmap_sections",
        "seatmap_backdrop_opacity", "seatmap_backdrop_offset_y",
        "seatmap_backdrop_offset_x", "seatmap_backdrop_scale",
        "currency",
    }
    update = {k: v for k, v in (payload or {}).items() if k in EDITABLE}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided")
    update["updated_at"] = utc_now().isoformat()
    update["updated_by"] = user["user_id"]

    await db.events.update_one({"event_id": event_id}, {"$set": update})
    refreshed = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    return event_to_public(refreshed)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, user: dict = Depends(get_current_user)):
    """Delete an event AND all of its bookings, holds, seat-blocks, scanner tokens,
    team grants. Only the owner or an admin can delete.

    NOTE: We refuse to delete events that already have paid bookings unless the
    caller is an admin — the organizer must refund first, or escalate to admin.
    """
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    is_owner = event.get("organizer_id") == user["user_id"]
    is_admin = user.get("role") == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Only the event owner or an admin can delete")

    paid_count = await db.bookings.count_documents({"event_id": event_id, "status": "paid"})
    if paid_count > 0 and not is_admin:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete — {paid_count} paid booking(s) exist. Refund first or ask an admin.",
        )

    # Cascade-clean any artefacts so the DB doesn't hoard orphans
    cascade = {
        "bookings": await db.bookings.delete_many({"event_id": event_id}),
        "seat_reservations": await db.seat_reservations.delete_many({"event_id": event_id}),
        "seat_holds": await db.seat_holds.delete_many({"event_id": event_id}),
        "scanner_tokens": await db.scanner_tokens.delete_many({"event_id": event_id}),
        "team_members_event": await db.team_members.delete_many({"event_id": event_id, "scope": "event"}),
        "waitlist": await db.waitlist.delete_many({"event_id": event_id}),
        "discount_codes": await db.discount_codes.delete_many({"event_id": event_id}),
    }
    await db.events.delete_one({"event_id": event_id})

    return {
        "deleted": event_id,
        "title": event.get("title"),
        "cascade": {k: r.deleted_count for k, r in cascade.items()},
    }



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


@router.get("/sitemap.xml")
async def sitemap():
    """Public sitemap for SEO — lists Browse + every approved event."""
    base = os.environ.get("APP_PUBLIC_URL", "https://allsale.events").rstrip("/")
    urls = [f"{base}/", f"{base}/events"]
    async for e in db.events.find(
        {"status": "approved"}, {"_id": 0, "event_id": 1, "date": 1},
    ).limit(5000):
        urls.append(f"{base}/events/{e['event_id']}")
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append(f"  <url><loc>{xml_escape(u)}</loc></url>")
    body.append("</urlset>")
    return Response(content="\n".join(body), media_type="application/xml")
