"""Per-event affiliate / referral codes.

Lets organizers create affiliate codes (separate from discount codes) that
track clicks + conversions. Each code is associated with a partner /
ambassador / promoter; when an attendee visits an event page with the
affiliate code as a query param (or has clicked an affiliate share link
recently), we drop a 30-day cookie and attribute the resulting booking.

Endpoints (organizer-side):
  POST   /api/organizer/affiliates                       — create
  GET    /api/organizer/affiliates                       — list w/ stats
  PATCH  /api/organizer/affiliates/{code_id}             — edit / deactivate
  DELETE /api/organizer/affiliates/{code_id}             — soft-delete

Endpoints (public):
  GET    /api/affiliate/track?code=XXX&event_id=YYY      — record a click;
                                                          sets cookie + 302s
                                                          to the event page.
  GET    /api/affiliate/{code}                           — resolve code → {organizer, commission_pct}

Attribution:
  Bookings include `affiliate_code` and `affiliate_id` when created within
  the cookie window. The booking router uses
  `affiliate_code_from_cookie(request)` to pull the value.
"""
from __future__ import annotations

import re
import uuid
import logging
from datetime import timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["affiliates"])

AFFILIATE_COOKIE = "aff_code"
AFFILIATE_COOKIE_DAYS = 30
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


class AffiliateIn(BaseModel):
    code: str
    partner_name: str
    partner_email: Optional[str] = None
    commission_pct: float = Field(0, ge=0, le=100)
    # Optional restriction. None = all of organizer's events.
    event_id: Optional[str] = None
    notes: Optional[str] = None


def _normalize_code(s: str) -> str:
    return (s or "").strip().upper()


@router.post("/organizer/affiliates")
async def create_affiliate(payload: AffiliateIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    code = _normalize_code(payload.code)
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Code must be 2-24 chars A-Z, 0-9, _ or -")

    if payload.event_id:
        ev = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0, "organizer_id": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        if ev["organizer_id"] != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your event")

    if await db.affiliates.find_one({"code": code, "created_by": user["user_id"]}):
        raise HTTPException(status_code=409, detail=f"You already have an affiliate code '{code}'")

    doc = {
        "affiliate_id": f"aff_{uuid.uuid4().hex[:12]}",
        "code": code,
        "partner_name": payload.partner_name.strip()[:120],
        "partner_email": (payload.partner_email or "").strip().lower() or None,
        "commission_pct": float(payload.commission_pct),
        "event_id": payload.event_id,
        "notes": (payload.notes or "").strip()[:500] or None,
        "active": True,
        "clicks": 0,
        "conversions": 0,
        "revenue_attributed": 0.0,
        "created_by": user["user_id"],
        "created_at": utc_now().isoformat(),
    }
    await db.affiliates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/organizer/affiliates")
async def list_affiliates(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    items: List[dict] = []
    async for a in db.affiliates.find({"created_by": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        # Compute conversion stats from bookings table — counts paid only.
        agg = await db.bookings.aggregate([
            {"$match": {"affiliate_code": a["code"], "status": "paid", "event_id": a.get("event_id") or {"$exists": True}}},
            {"$group": {"_id": None, "n": {"$sum": 1}, "rev": {"$sum": "$amount"}, "tickets": {"$sum": "$quantity"}}},
        ]).to_list(1)
        a["conversions"] = agg[0]["n"] if agg else 0
        a["revenue_attributed"] = round(agg[0]["rev"], 2) if agg else 0.0
        a["tickets_sold"] = agg[0]["tickets"] if agg else 0
        a["commission_owed"] = round(a["revenue_attributed"] * a["commission_pct"] / 100, 2)
        items.append(a)
    return items


@router.patch("/organizer/affiliates/{affiliate_id}")
async def edit_affiliate(affiliate_id: str, payload: dict, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    a = await db.affiliates.find_one({"affiliate_id": affiliate_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Affiliate not found")
    if a["created_by"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your affiliate")

    EDITABLE = {"partner_name", "partner_email", "commission_pct", "notes", "active"}
    update = {k: v for k, v in (payload or {}).items() if k in EDITABLE}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields")
    if "commission_pct" in update:
        update["commission_pct"] = max(0.0, min(100.0, float(update["commission_pct"])))
    if "partner_email" in update and update["partner_email"]:
        update["partner_email"] = update["partner_email"].strip().lower()
    update["updated_at"] = utc_now().isoformat()
    await db.affiliates.update_one({"affiliate_id": affiliate_id}, {"$set": update})
    return {"ok": True}


@router.delete("/organizer/affiliates/{affiliate_id}")
async def deactivate_affiliate(affiliate_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    a = await db.affiliates.find_one({"affiliate_id": affiliate_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Affiliate not found")
    if a["created_by"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your affiliate")
    await db.affiliates.update_one({"affiliate_id": affiliate_id}, {"$set": {"active": False}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public — click tracking + cookie drop
# ---------------------------------------------------------------------------

@router.get("/affiliate/track")
async def track_affiliate_click(request: Request, code: str, event_id: Optional[str] = None):
    """Drop the affiliate cookie, log the click, then 302 to the event page.

    Frontend shareable URL pattern:
        https://www.allsale.events/api/affiliate/track?code=PROMO50&event_id=evt_xxx
    Resulting cookie persists for `AFFILIATE_COOKIE_DAYS` days across the
    apex domain.
    """
    code_norm = _normalize_code(code)
    if not code_norm:
        raise HTTPException(status_code=400, detail="Code required")
    aff = await db.affiliates.find_one(
        {"code": code_norm, "active": True},
        {"_id": 0, "affiliate_id": 1, "event_id": 1, "created_by": 1},
    )
    target_event = event_id or (aff or {}).get("event_id")
    # Even if affiliate code doesn't exist, redirect gracefully — don't 404
    # on the public surface.
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    if target_event:
        # Verify the event exists before redirecting.
        ev = await db.events.find_one({"event_id": target_event}, {"_id": 0, "event_id": 1})
        if ev:
            redirect_url = f"{origin}/events/{target_event}"
        else:
            redirect_url = f"{origin}/events"
    else:
        redirect_url = f"{origin}/events"

    if aff:
        await db.affiliates.update_one(
            {"affiliate_id": aff["affiliate_id"]},
            {"$inc": {"clicks": 1}, "$set": {"last_click_at": utc_now().isoformat()}},
        )
        await db.affiliate_clicks.insert_one({
            "click_id": f"clk_{uuid.uuid4().hex[:12]}",
            "affiliate_id": aff["affiliate_id"],
            "code": code_norm,
            "event_id": target_event,
            "referrer": request.headers.get("referer"),
            "user_agent": (request.headers.get("user-agent") or "")[:200],
            "ip": request.client.host if request.client else None,
            "at": utc_now().isoformat(),
        })

    resp = RedirectResponse(url=redirect_url, status_code=302)
    if aff:
        # Cookie is host-only so it works in preview + production without
        # `Domain=` (preview is a different domain than apex).
        resp.set_cookie(
            key=AFFILIATE_COOKIE,
            value=code_norm,
            max_age=AFFILIATE_COOKIE_DAYS * 86400,
            httponly=False,  # need readable from JS for share buttons
            samesite="lax",
            secure=False,  # allow http for preview; prod is HTTPS-only anyway
            path="/",
        )
    return resp


@router.get("/affiliate/{code}")
async def resolve_affiliate(code: str):
    """Public lookup. Useful for the booking flow to display 'Referred by X.'"""
    code_norm = _normalize_code(code)
    aff = await db.affiliates.find_one(
        {"code": code_norm, "active": True},
        {"_id": 0, "affiliate_id": 1, "code": 1, "partner_name": 1, "event_id": 1, "commission_pct": 1},
    )
    if not aff:
        raise HTTPException(status_code=404, detail="Affiliate code not found")
    return aff


# ---------------------------------------------------------------------------
# Booking integration helper
# ---------------------------------------------------------------------------

def affiliate_code_from_cookie(request: Request) -> Optional[str]:
    """Pull the affiliate cookie from a request — used by `bookings.hold` to
    attribute a new booking to an affiliate."""
    val = request.cookies.get(AFFILIATE_COOKIE)
    if not val:
        return None
    val = _normalize_code(val)
    if not CODE_RE.match(val):
        return None
    return val


async def attribute_booking(booking_doc: dict, code: Optional[str]) -> dict:
    """Mutate `booking_doc` in place to record affiliate attribution. Called
    from the booking hold endpoint when a code is present (via cookie or
    URL param)."""
    if not code:
        return booking_doc
    code_norm = _normalize_code(code)
    aff = await db.affiliates.find_one(
        {"code": code_norm, "active": True},
        {"_id": 0, "affiliate_id": 1, "event_id": 1, "commission_pct": 1, "created_by": 1},
    )
    if not aff:
        return booking_doc
    # Event-scoped affiliates only attribute to their own event.
    if aff.get("event_id") and aff["event_id"] != booking_doc.get("event_id"):
        return booking_doc
    booking_doc["affiliate_code"] = code_norm
    booking_doc["affiliate_id"] = aff["affiliate_id"]
    booking_doc["affiliate_commission_pct"] = aff["commission_pct"]
    return booking_doc
