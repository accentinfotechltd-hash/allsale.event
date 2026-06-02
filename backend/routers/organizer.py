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

    # by discount code (attribution) — "Direct" bucket for bookings without a code
    by_code = defaultdict(lambda: {"tickets": 0, "revenue": 0.0, "discount_given": 0.0})
    for b in bookings:
        key = b.get("discount_code") or "Direct"
        by_code[key]["tickets"] += b.get("quantity", 0)
        by_code[key]["revenue"] += b.get("amount", 0)
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
        items.append(b)
    return items


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
    writer.writerow(["Booking ID", "Name", "Email", "Tier / Seats", "Qty", "Amount (USD)", "Paid At", "Booking Status", "Checked In", "Checked In At"])
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
    writer.writerow(["Status", "Name", "Email", "Booking ID", "Tier / Seats", "Quantity", "Amount Paid", "Checked In At", "Discount Code"])
    for b in bookings:
        seats = ", ".join(b.get("seats") or []) if b.get("seats") else b.get("tier_name", "")
        writer.writerow([
            "ATTENDED" if b.get("checked_in") else "NO-SHOW",
            b.get("user_name", ""),
            b.get("user_email", ""),
            b.get("booking_id", ""),
            seats,
            b.get("quantity", 0),
            f"{b.get('amount', 0):.2f}",
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
