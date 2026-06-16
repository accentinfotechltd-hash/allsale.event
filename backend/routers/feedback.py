"""Post-event NPS feedback collection.

Visitors land on `/feedback/:booking_id` from the post-event email; they
submit a 1-5 star rating + optional comment which gets persisted to
`event_feedback`. Organizers can later display average star rating + a
few quoted comments on the event detail page as social proof.

No auth required — the booking_id is the secret (long random UUID).
Re-submitting overwrites so people can change their mind.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import db, utc_now

router = APIRouter(tags=["feedback"])


class FeedbackIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=600)
    display_name: Optional[str] = Field(default=None, max_length=80)


@router.get("/feedback/{booking_id}")
async def get_feedback_context(booking_id: str):
    """Return enough info for the feedback page header (event title, image, plus
    any existing rating the visitor already left)."""
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0, "event_id": 1, "user_email": 1})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    event = await db.events.find_one(
        {"event_id": booking["event_id"]},
        {"_id": 0, "title": 1, "image_url": 1, "venue": 1, "city": 1, "date": 1, "organizer_id": 1},
    ) or {}
    existing = await db.event_feedback.find_one({"booking_id": booking_id}, {"_id": 0})
    return {"event": event, "existing": existing}


@router.post("/feedback/{booking_id}")
async def submit_feedback(booking_id: str, payload: FeedbackIn):
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    doc = {
        "booking_id": booking_id,
        "event_id": booking["event_id"],
        "user_id": booking.get("user_id"),
        "stars": payload.stars,
        "comment": (payload.comment or "").strip() or None,
        "display_name": (payload.display_name or "").strip() or "Verified attendee",
        "submitted_at": utc_now().isoformat(),
    }
    await db.event_feedback.update_one(
        {"booking_id": booking_id},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True}


@router.get("/events/{event_id}/feedback")
async def public_event_feedback(event_id: str, limit: int = 20):
    """Public endpoint — organizers display average rating + a few comments
    on the event page so future visitors see social proof."""
    cursor = db.event_feedback.find(
        {"event_id": event_id, "stars": {"$gte": 4}},  # only show ≥4★ as social proof
        {"_id": 0, "stars": 1, "comment": 1, "display_name": 1, "submitted_at": 1},
    ).sort("submitted_at", -1).limit(max(1, min(limit, 50)))
    comments = []
    async for fb in cursor:
        if fb.get("comment"):
            comments.append(fb)

    # Aggregate average + count across ALL feedback (not just the high-star ones)
    agg = await db.event_feedback.aggregate([
        {"$match": {"event_id": event_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$stars"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    avg = round(agg[0]["avg"], 1) if agg else None
    count = agg[0]["count"] if agg else 0
    return {"avg_stars": avg, "count": count, "comments": comments}
