"""Event analytics: views tracking, demand sparkline, sales velocity.

Lightweight aggregations so EventDetail can show a 7-day demand sparkline and
the organizer drill-down can show "12 tickets/hour, sellout in 4d" forecasts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core import db, get_current_user, get_current_user_optional, utc_now

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# View tracking — POST /events/{id}/view (debounced on the frontend)
# ---------------------------------------------------------------------------
@router.post("/events/{event_id}/view")
async def record_view(event_id: str, request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    """Record an event-detail view. Cheap insert; bucketed analytics happen at read time.

    Auth is optional — anonymous viewers count too (use IP-derived fingerprint).
    Frontend should debounce so a single SPA mount yields at most one POST per minute.
    """
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0, "event_id": 1})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    fingerprint = (user or {}).get("user_id") if user else (request.client.host if request.client else "anon")
    await db.event_views.insert_one({
        "event_id": event_id,
        "user_id": (user or {}).get("user_id"),
        "fingerprint": fingerprint,
        "at": utc_now().isoformat(),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Demand sparkline — last 7 days of views + bookings (public)
# ---------------------------------------------------------------------------
@router.get("/events/{event_id}/demand")
async def event_demand(event_id: str):
    """Returns 7 daily buckets: views + paid_bookings, oldest → newest."""
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0, "event_id": 1})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now = utc_now()
    start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    days = [(start + timedelta(days=i)) for i in range(7)]
    buckets = {d.strftime("%Y-%m-%d"): {"date": d.strftime("%Y-%m-%d"), "views": 0, "bookings": 0} for d in days}

    async for v in db.event_views.find(
        {"event_id": event_id, "at": {"$gte": start.isoformat()}},
        {"_id": 0, "at": 1},
    ):
        try:
            key = v["at"][:10]
            if key in buckets:
                buckets[key]["views"] += 1
        except Exception:
            continue

    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid", "paid_at": {"$gte": start.isoformat()}},
        {"_id": 0, "paid_at": 1, "quantity": 1},
    ):
        try:
            key = (b.get("paid_at") or "")[:10]
            if key in buckets:
                buckets[key]["bookings"] += b.get("quantity", 1)
        except Exception:
            continue

    return {"items": [buckets[d.strftime("%Y-%m-%d")] for d in days]}


# ---------------------------------------------------------------------------
# Sales velocity — organizer-only forecast
# ---------------------------------------------------------------------------
@router.get("/organizer/events/{event_id}/velocity")
async def sales_velocity(event_id: str, user: dict = Depends(get_current_user)):
    """Returns recent sales velocity + a naive linear sellout forecast."""
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")

    now = utc_now()

    # Compute capacity + sold count
    if event.get("has_seatmap"):
        rows = event.get("seat_rows", 0)
        cols = event.get("seat_cols", 0)
        aisles = set(event.get("aisles") or [])
        capacity = max(0, rows * cols - len(aisles))
        sold = await db.seat_reservations.count_documents({"event_id": event_id, "status": "booked"})
    else:
        capacity = sum(t.get("capacity", 0) for t in event.get("tiers", []))
        sold = 0
        async for b in db.bookings.find(
            {"event_id": event_id, "status": "paid"}, {"_id": 0, "quantity": 1},
        ):
            sold += b.get("quantity", 0)

    remaining = max(0, capacity - sold)

    # Recent 24h velocity (paid bookings)
    last_24h = now - timedelta(hours=24)
    sold_24h = 0
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid", "paid_at": {"$gte": last_24h.isoformat()}},
        {"_id": 0, "quantity": 1},
    ):
        sold_24h += b.get("quantity", 1)

    last_7d = now - timedelta(days=7)
    sold_7d = 0
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid", "paid_at": {"$gte": last_7d.isoformat()}},
        {"_id": 0, "quantity": 1},
    ):
        sold_7d += b.get("quantity", 1)

    per_hour_24 = round(sold_24h / 24.0, 2)
    per_day_7 = round(sold_7d / 7.0, 2)
    rate_per_day = per_day_7 if sold_7d > 0 else (sold_24h * 1.0)

    # Linear sellout forecast (None if we'd need >365 days or rate is zero)
    forecast_days: Optional[float] = None
    forecast_label = "Not enough data"
    if rate_per_day > 0 and remaining > 0:
        days = remaining / rate_per_day
        if days <= 365:
            forecast_days = round(days, 1)
            if days < 1:
                forecast_label = "Sellout today"
            elif days < 2:
                forecast_label = "Sellout tomorrow"
            else:
                forecast_label = f"Expected sellout in {forecast_days:.0f}d"
        else:
            forecast_label = "Slow demand"
    elif remaining == 0:
        forecast_label = "Sold out"
    elif rate_per_day == 0:
        forecast_label = "No sales yet"

    return {
        "capacity": capacity,
        "sold": sold,
        "remaining": remaining,
        "sold_24h": sold_24h,
        "sold_7d": sold_7d,
        "per_hour_24h": per_hour_24,
        "per_day_7d": per_day_7,
        "forecast_days": forecast_days,
        "forecast_label": forecast_label,
    }
