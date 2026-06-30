"""Organizer dashboard: events, analytics, drill-down, attendees, CSV export, check-in."""
import csv
import io
import secrets
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

from core import db, get_current_user, get_current_user_optional, require_role, event_to_public, utc_now
from routers.team import user_can_manage_event
from emails import send_template_fireforget
from datetime import datetime as _dt_for_fmt


def _fmt_when(iso: str) -> str:
    try:
        return _dt_for_fmt.fromisoformat((iso or "").replace("Z", "+00:00")).strftime("%a, %b %-d · %-I:%M %p")
    except Exception:
        return iso or ""


def _organizer_revenue(booking: dict) -> float:
    """Organizer's gross revenue from a booking — the *face value* of the
    ticket, NEVER the buyer-paid amount.

    `amount` on the booking is what the buyer was charged on Stripe, which
    bakes in platform commission + Stripe processing fees. Showing that to
    organizers is misleading (they don't get all of it) and leaks the
    platform's fee structure on every report row.

    Falls back to `amount` for legacy bookings that pre-date the fees.py
    refactor (face_value was added Feb 2026; older rows may not have it).
    """
    fv = booking.get("face_value")
    if fv is not None:
        return float(fv) or 0.0
    return float(booking.get("amount") or 0)

router = APIRouter(prefix="/organizer", tags=["organizer"])


class CheckinIn(BaseModel):
    event_id: str
    qr_payload: Optional[str] = None  # e.g. "AURA|bkg_xxxxxxx..."
    booking_id: Optional[str] = None  # manual entry fallback
    scanner_token: Optional[str] = None  # for volunteer/3rd-party scanners


@router.get("/events")
async def org_events(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    # Owned events
    owned_ids: set[str] = set()
    owned_events = []
    async for e in db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        owned_ids.add(e["event_id"])
        owned_events.append(event_to_public(e))

    # Events granted to this user via team membership (per-event OR via org-wide grant)
    org_owners: set[str] = set()
    team_event_ids: set[str] = set()
    async for tm in db.team_members.find(
        {"member_user_id": user["user_id"], "status": "active"}, {"_id": 0},
    ):
        if tm.get("scope") == "organization" and tm.get("owner_user_id"):
            org_owners.add(tm["owner_user_id"])
        elif tm.get("scope") == "event" and tm.get("event_id"):
            team_event_ids.add(tm["event_id"])

    extra_query: dict = {}
    if org_owners and team_event_ids:
        extra_query = {"$or": [
            {"organizer_id": {"$in": list(org_owners)}},
            {"event_id": {"$in": list(team_event_ids - owned_ids)}},
        ]}
    elif org_owners:
        extra_query = {"organizer_id": {"$in": list(org_owners)}}
    elif team_event_ids:
        extra_query = {"event_id": {"$in": list(team_event_ids - owned_ids)}}

    team_events = []
    if extra_query:
        async for e in db.events.find(extra_query, {"_id": 0}).sort("created_at", -1):
            if e["event_id"] in owned_ids:
                continue
            pub = event_to_public(e)
            pub["_team_role"] = "team"
            team_events.append(pub)

    return owned_events + team_events


@router.get("/analytics")
async def org_analytics(user: dict = Depends(get_current_user)):
    """Aggregate analytics across all of organizer's events."""
    await require_role(user, "organizer", "admin")
    events = await db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).to_list(500)
    event_ids = [e["event_id"] for e in events]
    bookings = []
    async for b in db.bookings.find({"event_id": {"$in": event_ids}, "status": "paid"}, {"_id": 0}):
        bookings.append(b)

    total_revenue = sum(_organizer_revenue(b) for b in bookings)
    tickets_sold = sum(b.get("quantity", 0) for b in bookings)

    per_event = {}
    for b in bookings:
        eid = b["event_id"]
        if eid not in per_event:
            per_event[eid] = {"event_id": eid, "title": b["event_title"], "revenue": 0, "tickets": 0}
        per_event[eid]["revenue"] += _organizer_revenue(b)
        per_event[eid]["tickets"] += b.get("quantity", 0)

    series = {}
    for b in bookings:
        d = (b.get("paid_at") or b.get("created_at", ""))[:10]
        series[d] = series.get(d, 0) + _organizer_revenue(b)
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
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    bookings = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        bookings.append(b)

    # by tier
    by_tier = defaultdict(lambda: {"tickets": 0, "revenue": 0.0})
    for b in bookings:
        t = b.get("tier_name", "Seat Selection")
        by_tier[t]["tickets"] += b.get("quantity", 0)
        by_tier[t]["revenue"] += _organizer_revenue(b)
    tiers = [{"tier": k, "tickets": v["tickets"], "revenue": round(v["revenue"], 2)} for k, v in by_tier.items()]

    # by day (last 30 entries)
    by_day = defaultdict(lambda: {"tickets": 0, "revenue": 0.0})
    for b in bookings:
        d = (b.get("paid_at") or b.get("created_at", ""))[:10]
        by_day[d]["tickets"] += b.get("quantity", 0)
        by_day[d]["revenue"] += _organizer_revenue(b)
    days = [{"date": k, "tickets": v["tickets"], "revenue": round(v["revenue"], 2)} for k, v in sorted(by_day.items())]

    # by hour-of-day (when bookings were paid)
    by_hour = defaultdict(int)
    for b in bookings:
        ts = b.get("paid_at") or b.get("created_at", "")
        if "T" in ts:
            h = int(ts.split("T")[1][:2])
            by_hour[h] += b.get("quantity", 0)
    hours = [{"hour": h, "tickets": by_hour.get(h, 0)} for h in range(24)]

    # by discount code (attribution) — "Direct" bucket for bookings without a code
    by_code = defaultdict(lambda: {"tickets": 0, "revenue": 0.0, "discount_given": 0.0})
    for b in bookings:
        key = b.get("discount_code") or "Direct"
        by_code[key]["tickets"] += b.get("quantity", 0)
        by_code[key]["revenue"] += _organizer_revenue(b)
        by_code[key]["discount_given"] += b.get("discount_amount", 0)
    codes = [
        {"code": k, "tickets": v["tickets"], "revenue": round(v["revenue"], 2), "discount_given": round(v["discount_given"], 2)}
        for k, v in sorted(by_code.items(), key=lambda kv: -kv[1]["revenue"])
    ]

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
            "has_seatmap": event.get("has_seatmap", False),
            "seat_rows": event.get("seat_rows"),
            "seat_cols": event.get("seat_cols"),
            "seat_price": event.get("seat_price"),
            "aisles": event.get("aisles") or [],
            "seatmap_sections": event.get("seatmap_sections") or [],
            "seatmap_curved": event.get("seatmap_curved", False),
            "currency": event.get("currency", "NZD"),
            "dynamic_pricing": event.get("dynamic_pricing") or {},
        },
        "totals": {
            "revenue": round(sum(_organizer_revenue(b) for b in bookings), 2),
            "tickets_sold": tickets_sold,
            "capacity": total_capacity,
            "sell_through_pct": sell_through,
            "bookings_count": len(bookings),
            "unique_attendees": len({b["user_email"] for b in bookings}),
        },
        "tiers": tiers,
        "days": days,
        "hours": hours,
        "codes": codes,
    }


@router.get("/events/{event_id}/attendees")
async def org_attendees(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        # Replace `amount` (buyer-paid total incl. platform + Stripe fees)
        # with the organizer's own revenue (face_value, with legacy fallback)
        # so the organizer never sees what the buyer was charged.
        b.pop("amount", None)
        b.pop("platform_fee", None)
        b.pop("stripe_fee_estimated", None)
        b.pop("service_fee", None)
        b["amount"] = round(_organizer_revenue(b), 2)
        items.append(b)
    return items


async def _organizer_visible_event_ids(user: dict) -> tuple[set[str], dict[str, dict]]:
    """Return (event_ids, events_by_id) the user can manage as organizer/team.

    Mirrors `org_events` visibility: owned + team-granted (per-event or
    org-wide). Admins see every event so they can audit any organizer.
    """
    query: dict
    if user.get("role") == "admin":
        query = {}
    else:
        owned_ids: set[str] = set()
        async for e in db.events.find({"organizer_id": user["user_id"]}, {"event_id": 1, "_id": 0}):
            owned_ids.add(e["event_id"])

        org_owners: set[str] = set()
        team_event_ids: set[str] = set()
        async for tm in db.team_members.find(
            {"member_user_id": user["user_id"], "status": "active"}, {"_id": 0},
        ):
            if tm.get("scope") == "organization" and tm.get("owner_user_id"):
                org_owners.add(tm["owner_user_id"])
            elif tm.get("scope") == "event" and tm.get("event_id"):
                team_event_ids.add(tm["event_id"])

        or_clauses: list[dict] = [{"organizer_id": user["user_id"]}]
        if org_owners:
            or_clauses.append({"organizer_id": {"$in": list(org_owners)}})
        if team_event_ids:
            or_clauses.append({"event_id": {"$in": list(team_event_ids - owned_ids)}})
        query = {"$or": or_clauses}

    events_by_id: dict[str, dict] = {}
    async for e in db.events.find(query, {"_id": 0}):
        events_by_id[e["event_id"]] = e

    return set(events_by_id.keys()), events_by_id


@router.get("/buyers")
async def org_buyers(
    user: dict = Depends(get_current_user),
    event_id: Optional[str] = None,
    status: Optional[str] = "paid",
    q: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    """Unified buyers report across ALL events the user can manage.

    Returns paid bookings (or any status when `status='all'`) flattened
    with the event title/date so the UI can render a single table. Filterable
    by event, free-text (name/email/booking id), date range, and status.
    """
    await require_role(user, "organizer", "admin")

    visible_ids, events_by_id = await _organizer_visible_event_ids(user)
    if not visible_ids:
        return {"items": [], "total": 0, "events": [], "limit": limit, "offset": offset}

    target_ids = visible_ids
    if event_id:
        if event_id not in visible_ids:
            raise HTTPException(status_code=403, detail="Not allowed for this event")
        target_ids = {event_id}

    query: dict = {"event_id": {"$in": list(target_ids)}}
    if status and status != "all":
        query["status"] = status
    if q:
        ql = q.strip()
        if ql:
            import re
            esc = re.escape(ql)
            query["$or"] = [
                {"user_name": {"$regex": esc, "$options": "i"}},
                {"user_email": {"$regex": esc, "$options": "i"}},
                {"booking_id": {"$regex": esc, "$options": "i"}},
            ]
    # Date range filter applied to paid_at (fallback to created_at).
    if from_date:
        query.setdefault("$and", []).append({"$or": [
            {"paid_at": {"$gte": from_date}},
            {"$and": [{"paid_at": {"$in": [None, ""]}}, {"created_at": {"$gte": from_date}}]},
        ]})
    if to_date:
        # inclusive upper bound: append a 'z' so any time on that ISO date matches
        upper = to_date + "z"
        query.setdefault("$and", []).append({"$or": [
            {"paid_at": {"$lte": upper}},
            {"$and": [{"paid_at": {"$in": [None, ""]}}, {"created_at": {"$lte": upper}}]},
        ]})

    total = await db.bookings.count_documents(query)
    safe_limit = max(1, min(int(limit or 200), 500))
    safe_offset = max(0, int(offset or 0))

    items = []
    cursor = (
        db.bookings.find(query, {"_id": 0})
        .sort([("paid_at", -1), ("created_at", -1)])
        .skip(safe_offset)
        .limit(safe_limit)
    )
    async for b in cursor:
        ev = events_by_id.get(b["event_id"]) or {}
        items.append({
            "booking_id": b.get("booking_id"),
            "event_id": b.get("event_id"),
            "event_title": b.get("event_title") or ev.get("title"),
            "event_date": b.get("event_date") or ev.get("date"),
            "event_venue": b.get("event_venue") or ev.get("venue"),
            "user_name": b.get("user_name"),
            "user_email": b.get("user_email"),
            "tier_name": b.get("tier_name"),
            "seats": b.get("seats") or [],
            "quantity": b.get("quantity", 0),
            # NOTE: `amount` here is the ORGANIZER's revenue (face value),
            # NOT what the buyer paid. We never expose buyer-paid totals,
            # platform fees, or Stripe fees to organizers.
            "amount": round(_organizer_revenue(b), 2),
            "currency": (b.get("currency") or ev.get("currency") or "NZD").upper(),
            "status": b.get("status"),
            "paid_at": b.get("paid_at"),
            "created_at": b.get("created_at"),
            "checked_in": bool(b.get("checked_in")),
            "checked_in_at": b.get("checked_in_at"),
            "discount_code": b.get("discount_code"),
            "discount_amount": round(b.get("discount_amount", 0) or 0, 2),
            "transferred_at": b.get("transferred_at"),
        })

    events_list = sorted(
        [
            {"event_id": e["event_id"], "title": e.get("title"), "date": e.get("date")}
            for e in events_by_id.values()
        ],
        key=lambda e: e.get("date") or "",
        reverse=True,
    )

    return {
        "items": items,
        "total": total,
        "events": events_list,
        "limit": safe_limit,
        "offset": safe_offset,
    }


@router.get("/buyers.csv")
async def org_buyers_csv(
    user: dict = Depends(get_current_user),
    event_id: Optional[str] = None,
    status: Optional[str] = "paid",
    q: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """Stream the unified buyers report (paid bookings across all visible
    events) as CSV. Filters mirror `/organizer/buyers`."""
    await require_role(user, "organizer", "admin")

    visible_ids, events_by_id = await _organizer_visible_event_ids(user)
    if not visible_ids:
        return Response(
            content=b"Booking ID,Event,Event date,Buyer,Email,Tier / Seats,Qty,Amount,Currency,Status,Booked at,Checked in\n",
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="buyers.csv"'},
        )

    target_ids = visible_ids
    if event_id:
        if event_id not in visible_ids:
            raise HTTPException(status_code=403, detail="Not allowed for this event")
        target_ids = {event_id}

    query: dict = {"event_id": {"$in": list(target_ids)}}
    if status and status != "all":
        query["status"] = status
    if q:
        ql = q.strip()
        if ql:
            import re
            esc = re.escape(ql)
            query["$or"] = [
                {"user_name": {"$regex": esc, "$options": "i"}},
                {"user_email": {"$regex": esc, "$options": "i"}},
                {"booking_id": {"$regex": esc, "$options": "i"}},
            ]
    if from_date:
        query.setdefault("$and", []).append({"$or": [
            {"paid_at": {"$gte": from_date}},
            {"$and": [{"paid_at": {"$in": [None, ""]}}, {"created_at": {"$gte": from_date}}]},
        ]})
    if to_date:
        upper = to_date + "z"
        query.setdefault("$and", []).append({"$or": [
            {"paid_at": {"$lte": upper}},
            {"$and": [{"paid_at": {"$in": [None, ""]}}, {"created_at": {"$lte": upper}}]},
        ]})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Booking ID", "Event", "Event date", "Buyer", "Email",
        "Tier / Seats", "Qty", "Revenue", "Currency", "Status",
        "Booked at", "Checked in",
    ])
    async for b in db.bookings.find(query, {"_id": 0}).sort([("paid_at", -1), ("created_at", -1)]):
        seats = ", ".join(b.get("seats") or []) if b.get("seats") else (b.get("tier_name") or "")
        ev = events_by_id.get(b["event_id"]) or {}
        writer.writerow([
            b.get("booking_id", ""),
            b.get("event_title") or ev.get("title", ""),
            (b.get("event_date") or ev.get("date") or "")[:10],
            b.get("user_name", ""),
            b.get("user_email", ""),
            seats,
            b.get("quantity", 0),
            f"{_organizer_revenue(b):.2f}",
            (b.get("currency") or ev.get("currency") or "NZD").upper(),
            b.get("status", ""),
            b.get("paid_at") or b.get("created_at", ""),
            "Yes" if b.get("checked_in") else "No",
        ])
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="buyers.csv"'},
    )


class TransferIn(BaseModel):
    """Body for re-assigning a paid booking to a different attendee."""
    email: EmailStr
    name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/bookings/{booking_id}/transfer")
async def transfer_booking(booking_id: str, payload: TransferIn, user: dict = Depends(get_current_user)):
    """Re-assign a paid booking to another attendee (alternative to refund).

    Seats stay the same — only the `user_*` fields and the QR-bearing record
    are updated. A new QR ticket email is sent to the recipient, and the
    previous holder gets a notice that their booking has been moved.

    If the target email already belongs to a registered user, the booking is
    linked to that account (it appears in their My Tickets). Otherwise we
    keep the email on the booking and they receive the ticket by email.
    """
    await require_role(user, "organizer", "admin")
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") != "paid":
        raise HTTPException(status_code=400, detail="Only paid bookings can be transferred")
    if booking.get("checked_in"):
        raise HTTPException(status_code=400, detail="Cannot transfer a booking that has already been checked in")

    event = await db.events.find_one({"event_id": booking["event_id"]}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event missing")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    new_email = str(payload.email).lower().strip()
    if new_email == booking.get("user_email", "").lower():
        raise HTTPException(status_code=400, detail="Booking is already under this email")

    target_user = await db.users.find_one({"email": new_email}, {"_id": 0, "password_hash": 0})
    new_name = (payload.name or "").strip() or (target_user.get("name") if target_user else new_email.split("@")[0])
    old_email = booking.get("user_email")
    old_name = booking.get("user_name")

    update = {
        "user_email": new_email,
        "user_name": new_name,
        "user_id": target_user["user_id"] if target_user else booking.get("user_id"),
        "transferred_at": utc_now().isoformat(),
        "transferred_by": user["user_id"],
        "transferred_from_email": old_email,
        "transferred_reason": payload.reason or None,
    }
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": update})

    # Refresh and re-send the confirmation/ticket email to the new holder.
    refreshed = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    try:
        send_template_fireforget(
            "booking_confirmation",
            new_email,
            {
                "user_name": new_name,
                "event_title": refreshed.get("event_title", event.get("title")),
                "event_when": _fmt_when(refreshed.get("event_date") or event.get("date") or ""),
                "event_venue": refreshed.get("event_venue") or event.get("venue"),
                "seats": refreshed.get("seats") or [],
                "tier_name": refreshed.get("tier_name"),
                "quantity": refreshed.get("quantity"),
                "amount": refreshed.get("amount"),
                "currency": refreshed.get("currency", "NZD"),
                "qr_payload": refreshed.get("qr_payload"),
                "booking_id": booking_id,
            },
            db,
        )
    except Exception:
        pass

    # Notify the previous holder so they're not surprised.
    if old_email and old_email.lower() != new_email:
        try:
            send_template_fireforget(
                "admin_blast",
                old_email,
                {
                    "user_name": old_name or "there",
                    "subject": f"Your booking for {event.get('title')} has been transferred",
                    "body": (
                        f"Hi {old_name or 'there'},\n\n"
                        f"Your booking for \"{event.get('title')}\" has been re-assigned by the organizer to {new_email}. "
                        f"You no longer hold this ticket. "
                        + (f"\n\nReason: {payload.reason}" if payload.reason else "")
                        + "\n\nIf this was unexpected, please reply to the organizer directly."
                    ),
                    "event_id": event.get("event_id"),
                    "event_title": event.get("title"),
                    "event_when": _fmt_when(event.get("date") or ""),
                },
                db,
            )
        except Exception:
            pass

    return {"transferred": True, "booking_id": booking_id, "new_email": new_email, "new_user_id": update["user_id"]}



class SwapSeatsIn(BaseModel):
    new_seats: list[str]
    reason: Optional[str] = None


@router.post("/bookings/{booking_id}/swap-seats")
async def swap_booking_seats(
    booking_id: str,
    payload: SwapSeatsIn,
    user: dict = Depends(get_current_user),
):
    """Move a paid booking to a different set of seats *within the same event*.

    Use case: customer was assigned A-1 but wanted B-5, or organizer needs to
    move a VIP guest to a better seat. Validates:
      - Booking is paid and not yet checked in
      - New seats exist in the seatmap
      - Same seat count as the existing booking
      - All new seats are currently free (not booked or held by anyone else)
      - Same tier (price-wise) — preventing accidental free upgrades / downgrades
    Also re-issues a fresh QR ticket email to the holder so they have the
    updated seat assignment, and releases the old seats back to the public.
    """
    await require_role(user, "organizer", "admin")
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("status") != "paid":
        raise HTTPException(status_code=400, detail="Only paid bookings can have seats swapped")
    if booking.get("checked_in"):
        raise HTTPException(status_code=400, detail="Cannot swap seats after check-in")

    old_seats = booking.get("seats") or []
    if not old_seats:
        raise HTTPException(status_code=400, detail="This booking doesn't use the seatmap — swap not applicable")

    new_seats = [s.strip() for s in (payload.new_seats or []) if s and s.strip()]
    if not new_seats:
        raise HTTPException(status_code=400, detail="At least one new seat is required")
    if len(new_seats) != len(old_seats):
        raise HTTPException(
            status_code=400,
            detail=f"Must select exactly {len(old_seats)} seat{'s' if len(old_seats) != 1 else ''} (same count as the original booking)",
        )
    if len(set(new_seats)) != len(new_seats):
        raise HTTPException(status_code=400, detail="Duplicate seats in selection")

    event = await db.events.find_one({"event_id": booking["event_id"]}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event missing")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Validate every requested seat exists in the seatmap and grab its tier.
    seatmap = event.get("seatmap") or {}
    all_seats_by_id = {s.get("id"): s for s in (seatmap.get("seats") or []) if s.get("id")}
    unknown = [s for s in new_seats if s not in all_seats_by_id]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown seat(s): {', '.join(unknown)}")

    # Confirm tier parity so we don't accidentally swap a Standard seat for a
    # VIP one without payment reconciliation. Same tier id required.
    old_tiers = {all_seats_by_id.get(s, {}).get("tier") for s in old_seats if s in all_seats_by_id}
    new_tiers = {all_seats_by_id[s].get("tier") for s in new_seats}
    if old_tiers != new_tiers or len(new_tiers) > 1:
        raise HTTPException(
            status_code=400,
            detail="New seats must be in the same tier as the original booking (to keep pricing fair).",
        )

    # Confirm no one else holds or has booked the requested seats. Same-booking
    # seats are exempt — swapping A-1 → A-1 is a no-op but we allow A-1+A-2 → A-2+A-1.
    other_reservations = await db.seat_reservations.find(
        {
            "event_id": booking["event_id"],
            "seat_id": {"$in": new_seats},
            "status": {"$in": ["held", "booked"]},
            "booking_id": {"$ne": booking_id},
        },
        {"_id": 0, "seat_id": 1, "status": 1},
    ).to_list(50)
    if other_reservations:
        taken = sorted({r["seat_id"] for r in other_reservations})
        raise HTTPException(
            status_code=409,
            detail=f"Seat(s) already taken: {', '.join(taken)}",
        )

    now = utc_now().isoformat()

    # Atomic-ish: free old reservations, write new ones, update the booking.
    await db.seat_reservations.delete_many({"booking_id": booking_id})
    new_reservation_docs = [
        {
            "event_id": booking["event_id"],
            "seat_id": s,
            "booking_id": booking_id,
            "user_id": booking.get("user_id"),
            "status": "booked",
            "created_at": now,
            "expires_at": None,
        }
        for s in new_seats
    ]
    if new_reservation_docs:
        await db.seat_reservations.insert_many(new_reservation_docs)

    await db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "seats": new_seats,
            "seats_swapped_at": now,
            "seats_swapped_by": user["user_id"],
            "seats_swapped_from": old_seats,
            "seats_swapped_reason": payload.reason or None,
        }},
    )

    # Broadcast the change so live event detail pages refresh.
    try:
        from realtime import notify_seats
        seat_events = (
            [{"seat_id": s, "status": "free"} for s in old_seats if s not in new_seats]
            + [{"seat_id": s, "status": "booked"} for s in new_seats if s not in old_seats]
        )
        if seat_events:
            await notify_seats(booking["event_id"], seat_events)
    except Exception:
        pass

    # Re-send the confirmation with the new seat assignment.
    refreshed = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    holder_email = refreshed.get("user_email")
    if holder_email:
        try:
            send_template_fireforget(
                "booking_confirmation",
                holder_email,
                {
                    "user_name": refreshed.get("user_name") or holder_email.split("@")[0],
                    "event_title": refreshed.get("event_title", event.get("title")),
                    "event_when": _fmt_when(refreshed.get("event_date") or event.get("date") or ""),
                    "event_venue": refreshed.get("event_venue") or event.get("venue"),
                    "seats": new_seats,
                    "tier_name": refreshed.get("tier_name"),
                    "quantity": refreshed.get("quantity"),
                    "amount": refreshed.get("amount"),
                    "currency": refreshed.get("currency", "NZD"),
                    "qr_payload": refreshed.get("qr_payload"),
                    "booking_id": booking_id,
                    "seat_swap_note": (
                        "Your seats have been updated by the organizer. "
                        f"Old seats: {', '.join(old_seats)} → New seats: {', '.join(new_seats)}."
                        + (f" Reason: {payload.reason}" if payload.reason else "")
                    ),
                },
                db,
            )
        except Exception:
            pass

    return {
        "ok": True,
        "booking_id": booking_id,
        "old_seats": old_seats,
        "new_seats": new_seats,
    }


@router.get("/events/{event_id}/attendees.csv")
async def org_attendees_csv(event_id: str, user: dict = Depends(get_current_user)):
    """Stream attendee list as CSV for the given event."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Booking ID", "Name", "Email", "Tier / Seats", "Qty", "Revenue", "Paid At", "Booking Status", "Checked In", "Checked In At"])
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}).sort("paid_at", 1):
        seats = ", ".join(b.get("seats") or []) if b.get("seats") else b.get("tier_name", "")
        writer.writerow([
            b.get("booking_id", ""),
            b.get("user_name", ""),
            b.get("user_email", ""),
            seats,
            b.get("quantity", 0),
            f"{_organizer_revenue(b):.2f}",
            b.get("paid_at") or b.get("created_at", ""),
            b.get("status", ""),
            "Yes" if b.get("checked_in") else "No",
            b.get("checked_in_at", ""),
        ])
    csv_bytes = buf.getvalue().encode("utf-8")
    safe_title = "".join(c if c.isalnum() else "_" for c in event.get("title", "event"))[:50]
    filename = f"attendees_{safe_title}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------------
# Check-in: scan QR / manual entry, attendance report
# ----------------------------------------------------------------------------
def _parse_qr(qr: str) -> Optional[str]:
    """QR payload format: 'AURA|<booking_id>' (with optional extra fields)."""
    if not qr:
        return None
    parts = qr.strip().split("|")
    if len(parts) >= 2 and parts[0] == "AURA":
        return parts[1].strip()
    return None


@router.post("/checkin")
async def checkin(payload: CheckinIn, user: Optional[dict] = Depends(get_current_user_optional)):
    """Scan a QR code and mark the booking as checked in.
    Idempotent: scanning a checked-in ticket returns the existing record (no error).

    Two ways to authorize:
      • Logged-in organizer/admin owning the event (Bearer token)
      • A valid `scanner_token` issued by the organizer for this event
        (lets door staff / volunteers scan without an account).
    """
    event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    actor_id = "scanner-token"
    if payload.scanner_token:
        tok = await db.scanner_tokens.find_one({
            "event_id": payload.event_id, "token": payload.scanner_token, "revoked": {"$ne": True},
        }, {"_id": 0})
        if not tok:
            raise HTTPException(status_code=403, detail="Invalid or revoked scanner token")
        actor_id = f"token:{tok.get('label') or tok['token'][:8]}"
    else:
        if not user:
            raise HTTPException(status_code=401, detail="Sign in or provide a scanner token")
        await require_role(user, "organizer", "admin")
        if not await user_can_manage_event(user, event, required="door_staff"):
            raise HTTPException(status_code=403, detail="Not your event")
        actor_id = user["user_id"]

    booking_id = payload.booking_id or _parse_qr(payload.qr_payload or "")
    if not booking_id:
        raise HTTPException(status_code=400, detail="Invalid QR code")

    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if booking["event_id"] != payload.event_id:
        raise HTTPException(status_code=400, detail="This ticket is for a different event")
    if booking.get("status") != "paid":
        raise HTTPException(status_code=400, detail=f"Ticket is {booking.get('status')}, not paid")

    already = bool(booking.get("checked_in"))
    if not already:
        now_iso = utc_now().isoformat()
        await db.bookings.update_one(
            {"booking_id": booking_id},
            {"$set": {
                "checked_in": True,
                "checked_in_at": now_iso,
                "checked_in_by": actor_id,
            }},
        )
        booking["checked_in"] = True
        booking["checked_in_at"] = now_iso

    return {
        "ok": True,
        "already_checked_in": already,
        "booking": {
            "booking_id": booking["booking_id"],
            "user_name": booking["user_name"],
            "user_email": booking["user_email"],
            "tier_name": booking.get("tier_name"),
            "seats": booking.get("seats") or [],
            "quantity": booking.get("quantity"),
            "checked_in_at": booking["checked_in_at"],
        },
    }


# ---------- Scanner tokens (volunteer / 3rd-party door staff) ----------

class ScannerTokenIn(BaseModel):
    label: Optional[str] = None  # e.g. "Door 1", "Front gate", "Volunteer Sam"


@router.post("/events/{event_id}/scanner-tokens")
async def create_scanner_token(event_id: str, payload: ScannerTokenIn, user: dict = Depends(get_current_user)):
    """Mint a single-event scanner token. Returns a URL the organizer can share
    with door staff — they open it on any phone, no login required."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")

    token = secrets.token_urlsafe(24)
    doc = {
        "token_id": secrets.token_hex(8),
        "event_id": event_id,
        "token": token,
        "label": (payload.label or "Door scanner").strip()[:80],
        "created_by": user["user_id"],
        "created_at": utc_now().isoformat(),
        "revoked": False,
    }
    await db.scanner_tokens.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/events/{event_id}/scanner-tokens")
async def list_scanner_tokens(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")
    return [
        t async for t in db.scanner_tokens.find({"event_id": event_id}, {"_id": 0}).sort("created_at", -1)
    ]


@router.delete("/events/{event_id}/scanner-tokens/{token_id}")
async def revoke_scanner_token(event_id: str, token_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")
    await db.scanner_tokens.update_one({"event_id": event_id, "token_id": token_id}, {"$set": {"revoked": True}})
    return {"ok": True}


@router.get("/scanner-context")
async def scanner_context(event_id: str, token: str):
    """Resolve a scanner token → event meta + live stats. No login required.
    Used by the public /scan/{eventId}?t=... page so door staff see what they're scanning for."""
    tok = await db.scanner_tokens.find_one({
        "event_id": event_id, "token": token, "revoked": {"$ne": True},
    }, {"_id": 0})
    if not tok:
        raise HTTPException(status_code=403, detail="Invalid or revoked scanner token")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    total = await db.bookings.count_documents({"event_id": event_id, "status": "paid"})
    checked = await db.bookings.count_documents({"event_id": event_id, "status": "paid", "checked_in": True})

    # Recent check-ins (last 20). Door volunteers benefit from seeing this too.
    recent = []
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid", "checked_in": True}, {"_id": 0}
    ).sort("checked_in_at", -1).limit(20):
        recent.append({
            "booking_id": b["booking_id"],
            "user_name": b["user_name"],
            "user_email": b["user_email"],
            "seats": b.get("seats") or [],
            "tier_name": b.get("tier_name"),
            "quantity": b.get("quantity"),
            "checked_in_at": b.get("checked_in_at"),
        })

    return {
        "event": {
            "event_id": event["event_id"],
            "title": event["title"],
            "venue": event.get("venue"),
            "date": event.get("date"),
            "image_url": event.get("image_url"),
        },
        "label": tok.get("label"),
        "stats": {"total": total, "checked_in": checked, "remaining": max(0, total - checked), "recent": recent},
    }


@router.get("/events/{event_id}/checkin-stats")
async def checkin_stats(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="door_staff"):
        raise HTTPException(status_code=403, detail="Forbidden")

    total_bookings = await db.bookings.count_documents({"event_id": event_id, "status": "paid"})
    checked_in_count = await db.bookings.count_documents({"event_id": event_id, "status": "paid", "checked_in": True})

    # Total tickets (sum of quantity)
    total_tickets = 0
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0, "quantity": 1}):
        total_tickets += b.get("quantity", 0)

    # Recent check-ins (last 20 paid bookings only)
    recent = []
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid", "checked_in": True}, {"_id": 0}
    ).sort("checked_in_at", -1).limit(20):
        recent.append({
            "booking_id": b["booking_id"],
            "user_name": b["user_name"],
            "user_email": b["user_email"],
            "seats": b.get("seats") or [],
            "tier_name": b.get("tier_name"),
            "quantity": b.get("quantity"),
            "checked_in_at": b.get("checked_in_at"),
        })

    no_shows_count = total_bookings - checked_in_count
    percent = round((checked_in_count / total_bookings) * 100, 1) if total_bookings else 0.0

    return {
        "total_bookings": total_bookings,
        "checked_in_count": checked_in_count,
        "no_shows_count": no_shows_count,
        "total_tickets": total_tickets,
        "percent": percent,
        "recent": recent,
    }


@router.post("/events/{event_id}/checkin/{booking_id}/undo")
async def undo_checkin(event_id: str, booking_id: str, user: dict = Depends(get_current_user)):
    """Undo a check-in (organizer mistake fix)."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.bookings.update_one(
        {"booking_id": booking_id, "event_id": event_id},
        {"$set": {"checked_in": False}, "$unset": {"checked_in_at": "", "checked_in_by": ""}},
    )
    return {"ok": True}


@router.get("/events/{event_id}/attendance-report.csv")
async def attendance_report_csv(event_id: str, user: dict = Depends(get_current_user)):
    """Full attendance report: every paid booking with checked-in status, sorted by status then name."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    bookings = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        bookings.append(b)
    # Sort: checked-in first, then not-checked-in; alphabetical within group
    bookings.sort(key=lambda b: (0 if b.get("checked_in") else 1, b.get("user_name", "")))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Status", "Name", "Email", "Booking ID", "Tier / Seats", "Quantity", "Revenue", "Checked In At", "Discount Code"])
    for b in bookings:
        seats = ", ".join(b.get("seats") or []) if b.get("seats") else b.get("tier_name", "")
        writer.writerow([
            "ATTENDED" if b.get("checked_in") else "NO-SHOW",
            b.get("user_name", ""),
            b.get("user_email", ""),
            b.get("booking_id", ""),
            seats,
            b.get("quantity", 0),
            f"{_organizer_revenue(b):.2f}",
            b.get("checked_in_at", ""),
            b.get("discount_code") or "",
        ])
    safe_title = "".join(c if c.isalnum() else "_" for c in event.get("title", "event"))[:50]
    filename = f"attendance_{safe_title}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------------------------------------------------------
# SEAT BLOCKS — organizer holds seats for sponsors / VIPs / gifts.
# Implemented as `seat_reservations` documents with status="blocked", so the
# existing public availability query and unique compound index automatically
# prevent any double-claim, with zero changes to the booking flow.
# -----------------------------------------------------------------------------
from pymongo.errors import DuplicateKeyError


class SeatBlockIn(BaseModel):
    seats: list[str]
    reason: Optional[str] = "VIP"  # VIP / Sponsor / Gift / Comp / Staff / Other
    note: Optional[str] = None


async def _assert_event_owner(event_id: str, user: dict) -> dict:
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return event


@router.get("/events/{event_id}/seat-blocks")
async def list_seat_blocks(event_id: str, user: dict = Depends(get_current_user)):
    """Return all seats the organizer has blocked for this event."""
    await require_role(user, "organizer", "admin")
    await _assert_event_owner(event_id, user)
    items = []
    async for r in db.seat_reservations.find(
        {"event_id": event_id, "status": "blocked"}, {"_id": 0}
    ).sort("created_at", -1):
        items.append({
            "seat_id": r["seat_id"],
            "reason": r.get("reason") or "VIP",
            "note": r.get("note") or "",
            "created_at": r.get("created_at"),
            "blocked_by": r.get("blocked_by"),
        })
    return {"event_id": event_id, "blocks": items, "count": len(items)}


@router.post("/events/{event_id}/seat-blocks")
async def create_seat_blocks(event_id: str, payload: SeatBlockIn, user: dict = Depends(get_current_user)):
    """Block seats so the public can't buy them. Useful for sponsors, VIPs, gifts.

    Rejects seats that are aisles, already booked, currently on hold by another
    buyer, or already blocked. Returns a summary so the UI can toast clearly.
    """
    await require_role(user, "organizer", "admin")
    event = await _assert_event_owner(event_id, user)

    if not event.get("has_seatmap"):
        raise HTTPException(status_code=400, detail="Seat blocking is only available for seatmap events")
    seats = [s for s in (payload.seats or []) if s]
    if not seats:
        raise HTTPException(status_code=400, detail="No seats provided")

    aisles = set(event.get("aisles") or [])
    bad_aisles = [s for s in seats if s in aisles]
    if bad_aisles:
        raise HTTPException(status_code=400, detail=f"Cannot block aisle markers: {', '.join(bad_aisles)}")

    now_iso = utc_now().isoformat()
    blocked = []
    rejected = []
    for sid in seats:
        try:
            await db.seat_reservations.insert_one({
                "event_id": event_id,
                "seat_id": sid,
                "status": "blocked",
                "reason": payload.reason or "VIP",
                "note": payload.note or "",
                "blocked_by": user["user_id"],
                "blocked_by_name": user.get("name") or user.get("email"),
                "created_at": now_iso,
                # blocks never expire — must be explicitly released
                "expires_at": "9999-12-31T23:59:59+00:00",
            })
            blocked.append(sid)
        except DuplicateKeyError:
            rejected.append(sid)

    # Tell anyone watching the seatmap so blocked seats grey-out instantly.
    try:
        from routers.ws_seats import notify_seats  # local import to avoid cycle on cold start
        if blocked:
            await notify_seats(event_id, [{"seat_id": s, "status": "booked"} for s in blocked])
    except Exception:
        pass

    return {"blocked": blocked, "rejected": rejected, "count": len(blocked)}


@router.delete("/events/{event_id}/seat-blocks/{seat_id}")
async def release_seat_block(event_id: str, seat_id: str, user: dict = Depends(get_current_user)):
    """Release a single previously-blocked seat back into public inventory."""
    await require_role(user, "organizer", "admin")
    await _assert_event_owner(event_id, user)
    res = await db.seat_reservations.delete_one({
        "event_id": event_id, "seat_id": seat_id, "status": "blocked",
    })
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Block not found")

    try:
        from routers.ws_seats import notify_seats
        await notify_seats(event_id, [{"seat_id": seat_id, "status": "available"}])
    except Exception:
        pass

    return {"released": seat_id}


@router.delete("/events/{event_id}/seat-blocks")
async def release_all_seat_blocks(event_id: str, user: dict = Depends(get_current_user)):
    """Release every blocked seat for an event (bulk action)."""
    await require_role(user, "organizer", "admin")
    await _assert_event_owner(event_id, user)
    seat_ids = []
    async for r in db.seat_reservations.find(
        {"event_id": event_id, "status": "blocked"}, {"_id": 0, "seat_id": 1}
    ):
        seat_ids.append(r["seat_id"])
    res = await db.seat_reservations.delete_many({"event_id": event_id, "status": "blocked"})

    try:
        from routers.ws_seats import notify_seats
        if seat_ids:
            await notify_seats(event_id, [{"seat_id": s, "status": "available"} for s in seat_ids])
    except Exception:
        pass

    return {"released_count": res.deleted_count, "seats": seat_ids}



# -----------------------------------------------------------------------------
# Announce event — organizer emails all marketing-opted-in users about this event.
# -----------------------------------------------------------------------------


@router.post("/events/{event_id}/announce")
async def announce_event(event_id: str, user: dict = Depends(get_current_user)):
    """Email opted-in users a 'new event' announcement.

    Targets users who have `notification_prefs.email_marketing` enabled AND
    have NOT already booked this event. Returns the recipient count so the
    UI can show a clean toast.
    """
    await require_role(user, "organizer", "admin")
    event = await _assert_event_owner(event_id, user)

    excluded_user_ids: set[str] = set()
    async for b in db.bookings.find(
        {"event_id": event_id, "status": "paid"}, {"_id": 0, "user_id": 1},
    ):
        if b.get("user_id"):
            excluded_user_ids.add(b["user_id"])

    sent = 0
    payload_base = {
        "event_id": event_id,
        "event_title": event.get("title", ""),
        "event_when": _fmt_when(event.get("date") or ""),
        "event_venue": event.get("venue", ""),
        "organizer_name": event.get("organizer_name") or user.get("name") or "Allsale Events",
    }

    async for u in db.users.find(
        {"user_id": {"$nin": list(excluded_user_ids)}}, {"_id": 0, "password_hash": 0},
    ):
        prefs = u.get("notification_prefs") or {}
        if not prefs.get("email_marketing", False):
            continue
        if not u.get("email"):
            continue
        try:
            send_template_fireforget(
                "new_event_announcement",
                u["email"],
                {**payload_base, "user_name": u.get("name") or u["email"].split("@")[0]},
                db,
            )
            sent += 1
        except Exception:
            pass

    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {"last_announced_at": utc_now().isoformat(), "last_announced_by": user["user_id"]}},
    )
    return {"sent": sent, "event_id": event_id}
