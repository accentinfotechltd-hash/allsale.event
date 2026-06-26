"""Admin- and organizer-managed creator promo codes.

Admins or the event's organizer attach a discount code to a specific
creator/influencer for a given event. Buyers get the discount, and (if a
`commission_percent` is set on the code) the creator earns a commission
credited to their `creator_earnings` ledger on every paid booking that used
the code.

How this fits with existing systems:
  • Codes live in the SAME `discount_codes` collection used by the organizer
    self-serve flow, but with two extra fields: `creator_id` and
    `commission_percent`. The booking validation / apply path is unchanged
    (organizers already validate against any discount_codes row for their
    event).
  • To keep the `_find_active_code()` lookup working we store
    `created_by = event.organizer_id` — i.e. the code "belongs" to the
    organizer for discount-lookup purposes, but the `creator_id` field
    records who gets credited.
  • Commission credit fires from `routers/payments.py` on the standard
    `booking_paid` hook, alongside the existing marketing-partner credit.
    Idempotent via a unique `(creator_id, booking_id)` compound index.

Endpoints (admin OR the event's organizer):
  POST   /api/admin/events/{event_id}/creator-codes        admin: create
  POST   /api/organizer/events/{event_id}/creator-codes    organizer: create
  GET    /api/admin/events/{event_id}/creator-codes        admin: list
  GET    /api/organizer/events/{event_id}/creator-codes    organizer: list
  PATCH  /api/admin/events/{event_id}/creator-codes/{id}   admin: edit
  PATCH  /api/organizer/events/{event_id}/creator-codes/{id}  organizer: edit
  DELETE /api/admin/events/{event_id}/creator-codes/{id}   admin: deactivate
  DELETE /api/organizer/events/{event_id}/creator-codes/{id}  organizer: deactivate
  GET    /api/admin/creator-codes/users-search?q=          autocomplete users
  GET    /api/organizer/creator-codes/users-search?q=      autocomplete users
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

logger = logging.getLogger("aura.creator_codes")
router = APIRouter(prefix="/admin", tags=["admin-creator-codes"])
# Organizer-facing mirror: same handlers, different auth (must own the event).
organizer_router = APIRouter(prefix="/organizer", tags=["organizer-creator-codes"])

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


def _admin_only(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


async def _ensure_can_manage_event(user: dict, event_id: str) -> dict:
    """Authorize the caller for creator-code operations on `event_id`.

    Allowed:
      • admin (any event)
      • the event's organizer (their own events)
    Returns the event document so callers don't re-fetch.
    """
    ev = await db.events.find_one(
        {"event_id": event_id},
        {"_id": 0, "organizer_id": 1, "title": 1, "currency": 1, "event_id": 1},
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if user.get("role") == "admin":
        return ev
    if user.get("user_id") == ev.get("organizer_id"):
        return ev
    raise HTTPException(status_code=403, detail="You don't own this event")


class CreatorCodeIn(BaseModel):
    code: str  # case-insensitive; we uppercase + strip
    creator_email: str  # who gets credit + earnings (we'll resolve to user_id)
    kind: str = "percent"  # "percent" or "flat"
    # Discount is OPTIONAL. Leave blank/None/0 to create a pure-commission /
    # attribution code where the buyer pays full price but the creator still
    # earns their commission on each redemption.
    value: Optional[float] = Field(None, ge=0)
    commission_percent: Optional[float] = Field(
        None, ge=0, le=100,
        description="If set, creator earns this % on each paid booking using the code.",
    )
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[str] = None  # ISO datetime
    restricted_tiers: List[str] = Field(default_factory=list)


@router.post("/events/{event_id}/creator-codes")
async def admin_create_creator_code(
    event_id: str,
    payload: CreatorCodeIn,
    user: dict = Depends(get_current_user),
):
    """Admin attaches a promo code to a creator for a specific event."""
    _admin_only(user)
    return await _create_creator_code(event_id, payload, user)


@organizer_router.post("/events/{event_id}/creator-codes")
async def organizer_create_creator_code(
    event_id: str,
    payload: CreatorCodeIn,
    user: dict = Depends(get_current_user),
):
    """Event organizer attaches a promo code to a creator for their own event."""
    await _ensure_can_manage_event(user, event_id)
    return await _create_creator_code(event_id, payload, user)


async def _create_creator_code(event_id: str, payload: CreatorCodeIn, user: dict) -> dict:
    code = (payload.code or "").strip().upper()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Code must be 2-24 chars A-Z, 0-9, _ or -")
    if payload.kind not in ("percent", "flat"):
        raise HTTPException(status_code=400, detail="Kind must be 'percent' or 'flat'")
    discount_value = float(payload.value) if payload.value is not None else 0.0
    if payload.kind == "percent" and discount_value > 100:
        raise HTTPException(status_code=400, detail="Percent cannot exceed 100")
    # Either give the buyer a discount, OR the creator a commission — a code
    # with neither does nothing.
    commission_pct = float(payload.commission_percent) if payload.commission_percent else 0.0
    if discount_value <= 0 and commission_pct <= 0:
        raise HTTPException(
            status_code=400,
            detail="Set a discount value, a creator commission %, or both — a code with neither has no effect.",
        )

    ev = await db.events.find_one({"event_id": event_id}, {"_id": 0, "organizer_id": 1, "title": 1, "currency": 1})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    creator_email = (payload.creator_email or "").strip().lower()
    creator = await db.users.find_one(
        {"email": creator_email},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "is_influencer": 1},
    )
    if not creator:
        raise HTTPException(status_code=404, detail=f"No user found with email {creator_email}")
    if not creator.get("is_influencer"):
        raise HTTPException(
            status_code=400,
            detail=f"{creator_email} hasn't enrolled as a creator yet. Ask them to enable creator mode first.",
        )

    # Codes are unique per organizer (existing constraint) — block duplicates.
    if await db.discount_codes.find_one({"code": code, "created_by": ev["organizer_id"]}):
        raise HTTPException(status_code=409, detail=f"A code '{code}' already exists on this organizer's account")

    doc = {
        "code_id": f"dc_{uuid.uuid4().hex[:12]}",
        "code": code,
        "kind": payload.kind,
        "value": discount_value,
        "event_id": event_id,
        "max_uses": payload.max_uses,
        "uses_count": 0,
        "expires_at": payload.expires_at,
        "restricted_tiers": payload.restricted_tiers,
        "active": True,
        # `created_by` = organizer so the existing _find_active_code lookup still finds it.
        "created_by": ev["organizer_id"],
        "creator_id": creator["user_id"],
        "creator_email": creator["email"],
        "creator_name": creator.get("name"),
        "commission_percent": (commission_pct if commission_pct > 0 else None),
        "admin_created_by": user["user_id"],
        "auto_generated": False,
        "kind_tag": "creator_promo",
        "created_at": utc_now().isoformat(),
    }
    await db.discount_codes.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        "[creator-code] %s %s created %s for creator %s on event %s",
        user.get("role", "?"), user["user_id"], code, creator["user_id"], event_id,
    )
    return doc


@router.get("/events/{event_id}/creator-codes")
async def admin_list_creator_codes(event_id: str, user: dict = Depends(get_current_user)):
    """List creator promo codes attached to this event with usage + commission stats."""
    _admin_only(user)
    return await _list_creator_codes(event_id)


@organizer_router.get("/events/{event_id}/creator-codes")
async def organizer_list_creator_codes(event_id: str, user: dict = Depends(get_current_user)):
    """Same listing, but scoped to the calling organizer's own event."""
    await _ensure_can_manage_event(user, event_id)
    return await _list_creator_codes(event_id)


@router.get("/events/{event_id}/influencer-summary")
async def admin_influencer_summary(event_id: str, user: dict = Depends(get_current_user)):
    """Per-influencer aggregate: who sold how many tickets and earned how much."""
    _admin_only(user)
    return await _influencer_summary(event_id)


@organizer_router.get("/events/{event_id}/influencer-summary")
async def organizer_influencer_summary(event_id: str, user: dict = Depends(get_current_user)):
    """Same summary, scoped to the calling organizer's own event."""
    await _ensure_can_manage_event(user, event_id)
    return await _influencer_summary(event_id)


async def _influencer_summary(event_id: str) -> dict:
    """One row per influencer driving sales on this event.

    Aggregates across ALL of a creator's codes for the event (they may have
    multiple — e.g. a 10% discount + a 20% special). Lets the organizer see
    which influencers actually move tickets vs. just hold a code.
    """
    by_creator: dict[str, dict] = {}

    # Walk every creator code on this event and bucket by creator_id.
    async for code in db.discount_codes.find(
        {"event_id": event_id, "creator_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ):
        cid = code["creator_id"]
        bk_agg = await db.bookings.aggregate([
            {"$match": {
                "discount_code": code["code"],
                "event_id": event_id,
                "status": {"$in": ["paid", "confirmed"]},
            }},
            {"$group": {"_id": None,
                        "bookings": {"$sum": 1},
                        "tickets": {"$sum": "$quantity"},
                        "revenue": {"$sum": "$amount"}}},
        ]).to_list(1)
        bk = bk_agg[0] if bk_agg else {}
        earn_agg = await db.creator_earnings.aggregate([
            {"$match": {"code_id": code["code_id"]}},
            {"$group": {"_id": "$status", "amount": {"$sum": "$earning_amount"}}},
        ]).to_list(5)
        slot = by_creator.setdefault(cid, {
            "creator_id": cid,
            "creator_name": code.get("creator_name"),
            "creator_email": code.get("creator_email"),
            "codes_count": 0,
            "active_codes": 0,
            "tickets_sold": 0,
            "bookings": 0,
            "revenue": 0.0,
            "commission_credited": 0.0,
            "commission_unpaid": 0.0,
        })
        slot["codes_count"] += 1
        if code.get("active"):
            slot["active_codes"] += 1
        slot["tickets_sold"] += int(bk.get("tickets") or 0)
        slot["bookings"] += int(bk.get("bookings") or 0)
        slot["revenue"] += float(bk.get("revenue") or 0)
        slot["commission_credited"] += sum(e["amount"] for e in earn_agg)
        slot["commission_unpaid"] += sum(e["amount"] for e in earn_agg if e["_id"] == "unpaid")

    # Enrich with avatar + display_name from `influencers` collection so the
    # organizer can recognise the human behind the email.
    creator_ids = list(by_creator.keys())
    if creator_ids:
        async for prof in db.influencers.find(
            {"user_id": {"$in": creator_ids}},
            {"_id": 0, "user_id": 1, "display_name": 1, "avatar_url": 1, "follower_count_total": 1},
        ):
            uid = prof["user_id"]
            if uid in by_creator:
                by_creator[uid]["display_name"] = prof.get("display_name") or by_creator[uid].get("creator_name")
                by_creator[uid]["avatar_url"] = prof.get("avatar_url")
                by_creator[uid]["follower_count"] = prof.get("follower_count_total") or 0

    # Rank by tickets sold (then revenue) so the leaderboard puts active
    # sellers on top and dormant code-holders at the bottom.
    items = sorted(
        by_creator.values(),
        key=lambda r: (r["tickets_sold"], r["revenue"]),
        reverse=True,
    )
    # Round monetary fields to cents for clean display.
    for r in items:
        for k in ("revenue", "commission_credited", "commission_unpaid"):
            r[k] = round(r[k], 2)
    return {
        "items": items,
        "totals": {
            "creators_with_codes": len(items),
            "active_sellers": sum(1 for r in items if r["tickets_sold"] > 0),
            "tickets_via_creators": sum(r["tickets_sold"] for r in items),
            "revenue_via_creators": round(sum(r["revenue"] for r in items), 2),
            "commission_owed_to_creators": round(sum(r["commission_unpaid"] for r in items), 2),
        },
    }


async def _list_creator_codes(event_id: str) -> dict:
    cur = db.discount_codes.find(
        {"event_id": event_id, "creator_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    ).sort("created_at", -1)
    items = [doc async for doc in cur]

    # Aggregate per-code: bookings paid + revenue + commission credited.
    for c in items:
        bookings_agg = await db.bookings.aggregate([
            {"$match": {"discount_code": c["code"], "event_id": event_id, "status": {"$in": ["paid", "confirmed"]}}},
            {"$group": {"_id": None, "count": {"$sum": 1}, "revenue": {"$sum": "$amount"}}},
        ]).to_list(1)
        c["paid_bookings"] = bookings_agg[0]["count"] if bookings_agg else 0
        c["revenue"] = round(bookings_agg[0]["revenue"], 2) if bookings_agg else 0
        earn_agg = await db.creator_earnings.aggregate([
            {"$match": {"code_id": c["code_id"]}},
            {"$group": {"_id": "$status", "amount": {"$sum": "$earning_amount"}}},
        ]).to_list(5)
        c["commission_credited"] = round(sum(e["amount"] for e in earn_agg), 2)
        c["commission_unpaid"] = round(sum(e["amount"] for e in earn_agg if e["_id"] == "unpaid"), 2)
    return {"items": items}


@router.delete("/events/{event_id}/creator-codes/{code_id}")
async def admin_deactivate_creator_code(
    event_id: str,
    code_id: str,
    user: dict = Depends(get_current_user),
):
    """Soft-delete: mark the code inactive. Existing earning rows stay."""
    _admin_only(user)
    return await _deactivate_creator_code(event_id, code_id)


@organizer_router.delete("/events/{event_id}/creator-codes/{code_id}")
async def organizer_deactivate_creator_code(
    event_id: str,
    code_id: str,
    user: dict = Depends(get_current_user),
):
    await _ensure_can_manage_event(user, event_id)
    return await _deactivate_creator_code(event_id, code_id)


async def _deactivate_creator_code(event_id: str, code_id: str) -> dict:
    res = await db.discount_codes.update_one(
        {"code_id": code_id, "event_id": event_id, "creator_id": {"$exists": True}},
        {"$set": {"active": False, "deactivated_at": utc_now().isoformat()}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Creator code not found")
    return {"deactivated": code_id}


class CreatorCodeEdit(BaseModel):
    # All optional — only the fields admin actually changed are sent.
    # value=0 / None means "no buyer discount" (pure-commission code).
    value: Optional[float] = Field(None, ge=0)
    kind: Optional[str] = None
    commission_percent: Optional[float] = Field(None, ge=0, le=100)
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[str] = None
    restricted_tiers: Optional[List[str]] = None
    active: Optional[bool] = None  # reactivate or deactivate via PATCH


@router.patch("/events/{event_id}/creator-codes/{code_id}")
async def admin_edit_creator_code(
    event_id: str,
    code_id: str,
    payload: CreatorCodeEdit,
    user: dict = Depends(get_current_user),
):
    """Edit an existing creator promo code. Code string and creator are
    immutable (changing either should be done via a new code so historical
    attribution stays clean). Everything else is editable.
    """
    _admin_only(user)
    return await _edit_creator_code(event_id, code_id, payload, user)


@organizer_router.patch("/events/{event_id}/creator-codes/{code_id}")
async def organizer_edit_creator_code(
    event_id: str,
    code_id: str,
    payload: CreatorCodeEdit,
    user: dict = Depends(get_current_user),
):
    """Same edit, but scoped to the calling organizer's own event."""
    await _ensure_can_manage_event(user, event_id)
    return await _edit_creator_code(event_id, code_id, payload, user)


async def _edit_creator_code(event_id: str, code_id: str, payload: CreatorCodeEdit, user: dict) -> dict:
    set_ops: dict = {}
    if payload.kind is not None:
        if payload.kind not in ("percent", "flat"):
            raise HTTPException(status_code=400, detail="Kind must be 'percent' or 'flat'")
        set_ops["kind"] = payload.kind
    if payload.value is not None:
        # If kind is being set in the same call use the new kind, else look up the existing one.
        kind_for_check = payload.kind or (await db.discount_codes.find_one({"code_id": code_id}, {"_id": 0, "kind": 1}) or {}).get("kind")
        if kind_for_check == "percent" and payload.value > 100:
            raise HTTPException(status_code=400, detail="Percent cannot exceed 100")
        set_ops["value"] = float(payload.value)
    if payload.commission_percent is not None:
        # Treat 0 as "discount-only" (no commission) for clarity in DB.
        set_ops["commission_percent"] = float(payload.commission_percent) if payload.commission_percent > 0 else None
    if payload.max_uses is not None:
        set_ops["max_uses"] = int(payload.max_uses)
    if payload.expires_at is not None:
        set_ops["expires_at"] = payload.expires_at or None
    if payload.restricted_tiers is not None:
        set_ops["restricted_tiers"] = payload.restricted_tiers
    if payload.active is not None:
        set_ops["active"] = bool(payload.active)
        if payload.active:
            set_ops["deactivated_at"] = None

    if not set_ops:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    set_ops["updated_at"] = utc_now().isoformat()
    set_ops["updated_by"] = user["user_id"]

    res = await db.discount_codes.update_one(
        {"code_id": code_id, "event_id": event_id, "creator_id": {"$exists": True}},
        {"$set": set_ops},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Creator code not found")
    updated = await db.discount_codes.find_one({"code_id": code_id}, {"_id": 0})
    return updated


@router.get("/creator-codes/users-search")
async def admin_search_users(q: str = Query(..., min_length=2), user: dict = Depends(get_current_user)):
    """Autocomplete for the 'Pick a creator' modal.

    Only surfaces users who have ALREADY enrolled in the creator/influencer
    program (`users.is_influencer = true`, set via `POST /api/influencer/enable`).
    This prevents admins from accidentally attaching a code to a random
    attendee — codes only make sense for users who've actively opted in,
    completed their public creator profile, and connected Stripe for payout.
    """
    _admin_only(user)
    return await _search_enrolled_creators(q)


@organizer_router.get("/creator-codes/users-search")
async def organizer_search_users(q: str = Query(..., min_length=2), user: dict = Depends(get_current_user)):
    """Same creator autocomplete, exposed to logged-in organizers."""
    if user.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Organizer or admin only")
    return await _search_enrolled_creators(q)


async def _search_enrolled_creators(q: str) -> dict:
    needle = q.strip()
    if not needle:
        return {"items": []}
    pattern = re.escape(needle)
    cur = db.users.find(
        {
            "is_influencer": True,
            "$or": [
                {"email": {"$regex": pattern, "$options": "i"}},
                {"name": {"$regex": pattern, "$options": "i"}},
            ],
        },
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role": 1},
    ).limit(10)
    users = [u async for u in cur]

    # Enrich with the influencer's chosen display name + follower count so
    # the caller sees who they're actually picking.
    if users:
        user_ids = [u["user_id"] for u in users]
        infl_map: dict = {}
        async for prof in db.influencers.find(
            {"user_id": {"$in": user_ids}, "is_active": True},
            {"_id": 0, "user_id": 1, "display_name": 1, "follower_count_total": 1, "categories": 1},
        ):
            infl_map[prof["user_id"]] = prof
        for u in users:
            prof = infl_map.get(u["user_id"]) or {}
            u["display_name"] = prof.get("display_name") or u.get("name")
            u["follower_count"] = prof.get("follower_count_total") or 0
            u["categories"] = prof.get("categories") or []
    return {"items": users}


# -----------------------------------------------------------------------------
# Commission credit hook — called from routers/payments.py on `booking_paid`.
# -----------------------------------------------------------------------------
async def record_creator_earning_for_booking(booking: dict) -> Optional[str]:
    """If a paid booking used a creator-tagged code with `commission_percent`,
    credit the creator's earnings ledger. Idempotent on (creator_id, booking_id).
    """
    code_str = booking.get("discount_code")
    if not code_str:
        return None
    booking_id = booking.get("booking_id")
    if not booking_id:
        return None
    code_doc = await db.discount_codes.find_one(
        {"code": code_str, "event_id": booking.get("event_id"), "creator_id": {"$exists": True, "$ne": None}},
        {"_id": 0},
    )
    if not code_doc:
        return None
    pct = code_doc.get("commission_percent")
    if pct is None or pct <= 0:
        return None  # creator wants credit but no payout — that's fine

    amount = float(booking.get("amount") or 0)
    if amount <= 0:
        return None
    earning_amt = round(amount * (pct / 100.0), 2)
    earning_id = f"cren_{uuid.uuid4().hex[:12]}"
    try:
        await db.creator_earnings.insert_one({
            "earning_id": earning_id,
            "creator_id": code_doc["creator_id"],
            "creator_email": code_doc.get("creator_email"),
            "creator_name": code_doc.get("creator_name"),
            "code_id": code_doc["code_id"],
            "code": code_str,
            "booking_id": booking_id,
            "event_id": booking.get("event_id"),
            "booking_amount": amount,
            "commission_percent": pct,
            "earning_amount": earning_amt,
            "currency": booking.get("currency") or "NZD",
            "status": "unpaid",
            "created_at": utc_now(),
        })
    except Exception as exc:  # noqa: BLE001
        from pymongo.errors import DuplicateKeyError
        if isinstance(exc, DuplicateKeyError):
            return None  # webhook replay
        raise
    logger.info(
        "[creator-earning] credited %s to creator %s for booking %s",
        earning_amt, code_doc["creator_id"], booking_id,
    )
    return earning_id
