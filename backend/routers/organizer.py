"""Organizer dashboard: events, analytics, drill-down, attendees, CSV export."""
import csv
import io
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core import db, get_current_user, require_role, event_to_public

router = APIRouter(prefix="/organizer", tags=["organizer"])


@router.get("/events")
async def org_events(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    cursor = db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return [event_to_public(e) async for e in cursor]


@router.get("/analytics")
async def org_analytics(user: dict = Depends(get_current_user)):
    """Aggregate analytics across all of organizer's events."""
    await require_role(user, "organizer", "admin")
    events = await db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).to_list(500)
    event_ids = [e["event_id"] for e in events]
    bookings = []
    async for b in db.bookings.find({"event_id": {"$in": event_ids}, "status": "paid"}, {"_id": 0}):
        bookings.append(b)

    total_revenue = sum(b.get("amount", 0) for b in bookings)
    tickets_sold = sum(b.get("quantity", 0) for b in bookings)

    per_event = {}
    for b in bookings:
        eid = b["event_id"]
        if eid not in per_event:
            per_event[eid] = {"event_id": eid, "title": b["event_title"], "revenue": 0, "tickets": 0}
        per_event[eid]["revenue"] += b.get("amount", 0)
        per_event[eid]["tickets"] += b.get("quantity", 0)

    series = {}
    for b in bookings:
        d = (b.get("paid_at") or b.get("created_at", ""))[:10]
        series[d] = series.get(d, 0) + b.get("amount", 0)
    series_list = [{"date": k, "revenue": round(v, 2)} for k, v in sorted(series.items())][-14:]

    return {
        "total_revenue": round(total_revenue, 2),
        "tickets_sold": tickets_sold,
        "events_count": len(events),
        "per_event": list(per_event.values()),
        "series": series_list,
    }


@router.get("/events/{event_id}/analytics")
async def event_drilldown(event_id: str, user: dict = Depends(get_current_user)):
    """Per-event drilldown: revenue & tickets by tier, by day, by city.
    Returns also a breakdown of attendees by their booking time-of-day."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    bookings = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        bookings.append(b)

    # by tier
    by_tier = defaultdict(lambda: {"tickets": 0, "revenue": 0.0})
    for b in bookings:
        t = b.get("tier_name", "Seat Selection")
        by_tier[t]["tickets"] += b.get("quantity", 0)
        by_tier[t]["revenue"] += b.get("amount", 0)
    tiers = [{"tier": k, "tickets": v["tickets"], "revenue": round(v["revenue"], 2)} for k, v in by_tier.items()]

    # by day (last 30 entries)
    by_day = defaultdict(lambda: {"tickets": 0, "revenue": 0.0})
    for b in bookings:
        d = (b.get("paid_at") or b.get("created_at", ""))[:10]
        by_day[d]["tickets"] += b.get("quantity", 0)
        by_day[d]["revenue"] += b.get("amount", 0)
    days = [{"date": k, "tickets": v["tickets"], "revenue": round(v["revenue"], 2)} for k, v in sorted(by_day.items())]

    # by hour-of-day (when bookings were paid)
    by_hour = defaultdict(int)
    for b in bookings:
        ts = b.get("paid_at") or b.get("created_at", "")
        if "T" in ts:
            h = int(ts.split("T")[1][:2])
            by_hour[h] += b.get("quantity", 0)
    hours = [{"hour": h, "tickets": by_hour.get(h, 0)} for h in range(24)]

    # capacity / sell-through
    if event.get("has_seatmap"):
        total_capacity = max(0, event.get("seat_rows", 0) * event.get("seat_cols", 0) - len(event.get("aisles") or []))
    else:
        total_capacity = sum(t.get("capacity", 0) for t in event.get("tiers", []))
    tickets_sold = sum(b.get("quantity", 0) for b in bookings)
    sell_through = round((tickets_sold / total_capacity) * 100, 1) if total_capacity else 0.0

    return {
        "event": {
            "event_id": event["event_id"],
            "title": event["title"],
            "venue": event["venue"],
            "city": event["city"],
            "date": event["date"],
            "category": event["category"],
            "image_url": event.get("image_url"),
        },
        "totals": {
            "revenue": round(sum(b.get("amount", 0) for b in bookings), 2),
            "tickets_sold": tickets_sold,
            "capacity": total_capacity,
            "sell_through_pct": sell_through,
            "bookings_count": len(bookings),
            "unique_attendees": len({b["user_email"] for b in bookings}),
        },
        "tiers": tiers,
        "days": days,
        "hours": hours,
    }


@router.get("/events/{event_id}/attendees")
async def org_attendees(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        items.append(b)
    return items


@router.get("/events/{event_id}/attendees.csv")
async def org_attendees_csv(event_id: str, user: dict = Depends(get_current_user)):
    """Stream attendee list as CSV for the given event."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Booking ID", "Name", "Email", "Tier / Seats", "Qty", "Amount (USD)", "Paid At", "Booking Status"])
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}).sort("paid_at", 1):
        seats = ", ".join(b.get("seats") or []) if b.get("seats") else b.get("tier_name", "")
        writer.writerow([
            b.get("booking_id", ""),
            b.get("user_name", ""),
            b.get("user_email", ""),
            seats,
            b.get("quantity", 0),
            f"{b.get('amount', 0):.2f}",
            b.get("paid_at") or b.get("created_at", ""),
            b.get("status", ""),
        ])
    csv_bytes = buf.getvalue().encode("utf-8")
    safe_title = "".join(c if c.isalnum() else "_" for c in event.get("title", "event"))[:50]
    filename = f"attendees_{safe_title}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
