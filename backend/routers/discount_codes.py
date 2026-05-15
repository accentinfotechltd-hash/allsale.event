"""Discount codes: organizer CRUD + public validate + apply-at-hold."""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now

router = APIRouter(tags=["discount-codes"])


class DiscountCodeIn(BaseModel):
    code: str  # case-insensitive; we uppercase + strip
    kind: str  # "percent" or "flat"
    value: float  # 10 = 10% or $10
    event_id: Optional[str] = None  # None = applies to all this organizer's events
    max_uses: Optional[int] = None  # None = unlimited
    expires_at: Optional[str] = None  # ISO datetime; None = no expiry
    restricted_tiers: List[str] = Field(default_factory=list)  # empty = all tiers


class ValidateIn(BaseModel):
    code: str
    event_id: str
    tier_name: Optional[str] = None
    quantity: int = 1
    seat_count: int = 0  # for seatmap events: number of seats selected
    subtotal: float  # pre-discount amount


CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


def _normalize_code(s: str) -> str:
    return (s or "").strip().upper()


def _apply_discount(kind: str, value: float, subtotal: float) -> float:
    """Return discount amount (positive number), capped at subtotal."""
    if kind == "percent":
        d = subtotal * (value / 100.0)
    else:
        d = value
    return round(min(d, subtotal), 2)


async def _find_active_code(code: str, event_id: str, organizer_id: Optional[str] = None) -> Optional[dict]:
    """Find a code that's either event-scoped to this event OR all-events for the event's organizer."""
    if organizer_id is None:
        ev = await db.events.find_one({"event_id": event_id}, {"_id": 0, "organizer_id": 1})
        if not ev:
            return None
        organizer_id = ev["organizer_id"]
    return await db.discount_codes.find_one(
        {
            "code": code,
            "active": True,
            "created_by": organizer_id,
            "$or": [{"event_id": event_id}, {"event_id": None}],
        },
        {"_id": 0},
    )


def _check_code_usable(c: dict, tier_name: Optional[str], quantity: int) -> Optional[str]:
    """Return None if usable, or an error string."""
    if c.get("expires_at"):
        exp = c["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < utc_now():
            return "Code has expired"
    if c.get("max_uses") is not None:
        remaining = c["max_uses"] - c.get("uses_count", 0)
        if remaining < quantity:
            return "Code usage limit reached"
    restricted = c.get("restricted_tiers") or []
    if restricted and tier_name and tier_name not in restricted:
        return f"Code only applies to: {', '.join(restricted)}"
    return None


@router.post("/organizer/discount-codes")
async def create_code(payload: DiscountCodeIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    code = _normalize_code(payload.code)
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Code must be 2-24 chars A-Z, 0-9, _ or -")
    if payload.kind not in ("percent", "flat"):
        raise HTTPException(status_code=400, detail="Kind must be 'percent' or 'flat'")
    if payload.value <= 0:
        raise HTTPException(status_code=400, detail="Value must be positive")
    if payload.kind == "percent" and payload.value > 100:
        raise HTTPException(status_code=400, detail="Percent cannot exceed 100")

    # If event-scoped, must belong to this organizer
    if payload.event_id:
        ev = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        if ev["organizer_id"] != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your event")

    # Codes are unique per organizer (so two organizers can both use "EARLY10")
    if await db.discount_codes.find_one({"code": code, "created_by": user["user_id"]}):
        raise HTTPException(status_code=409, detail=f"You already have a code '{code}'")

    doc = {
        "code_id": f"dc_{uuid.uuid4().hex[:12]}",
        "code": code,
        "kind": payload.kind,
        "value": float(payload.value),
        "event_id": payload.event_id,
        "max_uses": payload.max_uses,
        "uses_count": 0,
        "expires_at": payload.expires_at,
        "restricted_tiers": payload.restricted_tiers,
        "active": True,
        "created_by": user["user_id"],
        "created_at": utc_now().isoformat(),
    }
    await db.discount_codes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/organizer/discount-codes")
async def list_codes(user: dict = Depends(get_current_user)):
    """List all of this organizer's codes with usage stats."""
    await require_role(user, "organizer", "admin")
    items = []
    async for c in db.discount_codes.find({"created_by": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        # Compute revenue attributed
        agg = await db.bookings.aggregate([
            {"$match": {"discount_code": c["code"], "status": "paid"}},
            {"$group": {"_id": None, "revenue": {"$sum": "$amount"}, "tickets": {"$sum": "$quantity"}, "discount": {"$sum": "$discount_amount"}}},
        ]).to_list(1)
        c["attributed_revenue"] = round(agg[0]["revenue"], 2) if agg else 0
        c["attributed_tickets"] = agg[0]["tickets"] if agg else 0
        c["total_discount_given"] = round(agg[0]["discount"], 2) if agg else 0
        items.append(c)
    return items


@router.delete("/organizer/discount-codes/{code_id}")
async def deactivate_code(code_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    c = await db.discount_codes.find_one({"code_id": code_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Code not found")
    if c["created_by"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your code")
    await db.discount_codes.update_one({"code_id": code_id}, {"$set": {"active": False}})
    return {"ok": True}


@router.post("/discount-codes/validate")
async def validate_code(payload: ValidateIn):
    """Public-ish: anyone who has a booking flow open can validate a code.
    Does NOT consume the code — just checks + computes discount."""
    code = _normalize_code(payload.code)
    c = await _find_active_code(code, payload.event_id)
    if not c:
        raise HTTPException(status_code=404, detail="Code not found or inactive")
    qty = payload.seat_count if payload.seat_count > 0 else payload.quantity
    err = _check_code_usable(c, payload.tier_name, qty)
    if err:
        raise HTTPException(status_code=400, detail=err)
    discount = _apply_discount(c["kind"], c["value"], payload.subtotal)
    return {
        "code": code,
        "kind": c["kind"],
        "value": c["value"],
        "discount_amount": discount,
        "final_amount": round(max(0, payload.subtotal - discount), 2),
    }
