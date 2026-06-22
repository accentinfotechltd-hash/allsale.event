"""Marketing lead partner program (admin-controlled).

A "marketing partner" is anyone who brings organizers to Allsale (a freelance
sales agent, a referral agency, an industry contact). Admin configures the
partner once with a commission % and links one-or-more organizers to them.

Earnings model — **per-paid-booking recurring**:
  • Every time a referred organizer's booking is finalized (status flips to
    "paid"), the platform-commission slice we just took becomes the
    earnings base.
  • Partner earns `partner_commission = platform_fee × partner.commission_pct%`.
  • An immutable row is written to `marketing_partner_earnings` so the math
    is auditable and a payout batch can be cut later.
  • Recurring forever — no time cap. (We can layer one on later if abuse
    becomes a concern; for now the user explicitly chose recurring.)

We deliberately link the partner at the **organizer level** (the
`marketing_partner_id` field on the user doc) — not per event — so a new
event the organizer adds 2 years later still attributes correctly.

Endpoints (all admin-only):
  POST   /api/admin/marketing-partners                          create
  GET    /api/admin/marketing-partners                          list w/ stats
  GET    /api/admin/marketing-partners/{partner_id}             detail + organizers
  PATCH  /api/admin/marketing-partners/{partner_id}             edit
  DELETE /api/admin/marketing-partners/{partner_id}             deactivate
  POST   /api/admin/marketing-partners/{partner_id}/organizers  attach an organizer
  DELETE /api/admin/marketing-partners/{partner_id}/organizers/{user_id}  detach
  GET    /api/admin/marketing-partners/{partner_id}/earnings    earnings ledger
  POST   /api/admin/marketing-partners/{partner_id}/earnings/mark-paid  mark unpaid → paid

  GET    /api/admin/users/lookup-organizers?q=<search>          helper for "assign"
"""
from __future__ import annotations

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now, logger

router = APIRouter(tags=["marketing-partners"])


def _admin_only(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


def _strip(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ---------- schemas ----------

class PartnerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = None
    contact: Optional[str] = None  # phone / whatsapp / whatever
    commission_pct: float = Field(..., ge=0, le=100)
    notes: Optional[str] = ""


class PartnerPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None
    commission_pct: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class AttachIn(BaseModel):
    user_id: str


# ---------- helpers used by the booking hook ----------

async def record_partner_earning_for_booking(booking: dict) -> Optional[str]:
    """Called from `_finalize_paid_booking` once a booking goes paid.

    Returns the new earning_id if a partner earning row was written, else
    None. Idempotent — guarded by `(partner_id, booking_id)` uniqueness so
    a webhook replay never double-credits.
    """
    organizer_id = None
    event_id = booking.get("event_id")
    if not event_id:
        return None
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0, "organizer_id": 1, "title": 1})
    if not event:
        return None
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return None
    organizer = await db.users.find_one(
        {"user_id": organizer_id},
        {"_id": 0, "marketing_partner_id": 1},
    )
    if not organizer or not organizer.get("marketing_partner_id"):
        return None
    partner_id = organizer["marketing_partner_id"]
    partner = await db.marketing_partners.find_one(
        {"partner_id": partner_id, "status": "active"},
        {"_id": 0, "partner_id": 1, "commission_pct": 1, "name": 1},
    )
    if not partner:
        # Partner deleted or deactivated — silently skip; admin can re-link.
        return None
    # Already credited? (idempotency)
    if await db.marketing_partner_earnings.find_one(
        {"partner_id": partner_id, "booking_id": booking["booking_id"]},
        {"_id": 1},
    ):
        return None

    platform_fee = float(booking.get("platform_fee") or 0)
    if platform_fee <= 0:
        return None
    pct = float(partner.get("commission_pct") or 0)
    earning_amt = round(platform_fee * (pct / 100.0), 2)
    if earning_amt <= 0:
        return None

    earning_id = f"erng_{uuid.uuid4().hex[:12]}"
    await db.marketing_partner_earnings.insert_one(
        {
            "earning_id": earning_id,
            "partner_id": partner_id,
            "partner_name": partner.get("name"),
            "organizer_id": organizer_id,
            "booking_id": booking["booking_id"],
            "event_id": event_id,
            "event_title": event.get("title"),
            "booking_amount": float(booking.get("amount") or 0),
            "platform_fee": platform_fee,
            "commission_pct": pct,
            "earning_amount": earning_amt,
            "currency": booking.get("currency") or "NZD",
            "status": "unpaid",
            "created_at": utc_now(),
        }
    )
    logger.info(
        f"[marketing-partner] credited {earning_amt} to {partner_id} for booking {booking['booking_id']}"
    )
    return earning_id


async def _aggregate(partner_id: str) -> dict:
    """Total earnings + unpaid balance + organizer count for a partner."""
    org_count = await db.users.count_documents({"marketing_partner_id": partner_id})
    pipeline_lifetime = [
        {"$match": {"partner_id": partner_id}},
        {"$group": {"_id": None, "total": {"$sum": "$earning_amount"}}},
    ]
    pipeline_unpaid = [
        {"$match": {"partner_id": partner_id, "status": "unpaid"}},
        {"$group": {"_id": None, "total": {"$sum": "$earning_amount"}}},
    ]
    lifetime_doc = await db.marketing_partner_earnings.aggregate(pipeline_lifetime).to_list(1)
    unpaid_doc = await db.marketing_partner_earnings.aggregate(pipeline_unpaid).to_list(1)
    lifetime = round(lifetime_doc[0]["total"], 2) if lifetime_doc else 0.0
    unpaid = round(unpaid_doc[0]["total"], 2) if unpaid_doc else 0.0
    return {"organizer_count": org_count, "lifetime_earnings": lifetime, "unpaid_balance": unpaid}


# ---------- partner CRUD ----------

@router.post("/admin/marketing-partners")
async def create_partner(payload: PartnerIn, user: dict = Depends(get_current_user)):
    _admin_only(user)
    partner_id = f"mpt_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    doc = {
        "partner_id": partner_id,
        "name": payload.name.strip(),
        "email": (payload.email or "").strip().lower() or None,
        "contact": (payload.contact or "").strip() or None,
        "commission_pct": float(payload.commission_pct),
        "notes": payload.notes or "",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    await db.marketing_partners.insert_one(doc)
    return _strip(doc)


@router.get("/admin/marketing-partners")
async def list_partners(user: dict = Depends(get_current_user)):
    _admin_only(user)
    cur = db.marketing_partners.find({}, {"_id": 0}).sort("created_at", -1)
    items: List[dict] = []
    async for p in cur:
        items.append({**p, **(await _aggregate(p["partner_id"]))})
    return items


@router.get("/admin/marketing-partners/{partner_id}")
async def partner_detail(partner_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    partner = await db.marketing_partners.find_one({"partner_id": partner_id}, {"_id": 0})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    organizers = []
    cur = db.users.find(
        {"marketing_partner_id": partner_id},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "created_at": 1},
    )
    async for u in cur:
        organizers.append(u)
    stats = await _aggregate(partner_id)
    return {**partner, **stats, "organizers": organizers}


@router.patch("/admin/marketing-partners/{partner_id}")
async def update_partner(
    partner_id: str, payload: PartnerPatch, user: dict = Depends(get_current_user)
):
    _admin_only(user)
    existing = await db.marketing_partners.find_one({"partner_id": partner_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Partner not found")
    updates: dict = {"updated_at": utc_now()}
    fields = payload.model_dump(exclude_unset=True)
    for k, v in fields.items():
        if v is not None:
            updates[k] = v
    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].strip().lower()
    await db.marketing_partners.update_one({"partner_id": partner_id}, {"$set": updates})
    return _strip(await db.marketing_partners.find_one({"partner_id": partner_id}))


@router.delete("/admin/marketing-partners/{partner_id}")
async def delete_partner(partner_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    # Detach all organizers first so they don't have a dangling FK.
    await db.users.update_many(
        {"marketing_partner_id": partner_id},
        {"$unset": {"marketing_partner_id": ""}},
    )
    res = await db.marketing_partners.delete_one({"partner_id": partner_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Partner not found")
    return {"deleted": partner_id}


# ---------- organizer attachment ----------

@router.post("/admin/marketing-partners/{partner_id}/organizers")
async def attach_organizer(
    partner_id: str, payload: AttachIn, user: dict = Depends(get_current_user)
):
    _admin_only(user)
    partner = await db.marketing_partners.find_one({"partner_id": partner_id}, {"_id": 0, "partner_id": 1})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    org = await db.users.find_one({"user_id": payload.user_id}, {"_id": 0, "role": 1})
    if not org:
        raise HTTPException(status_code=404, detail="User not found")
    if org.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=400, detail="User is not an organizer")
    await db.users.update_one(
        {"user_id": payload.user_id},
        {"$set": {"marketing_partner_id": partner_id, "marketing_partner_attached_at": utc_now()}},
    )
    return {"ok": True}


@router.delete("/admin/marketing-partners/{partner_id}/organizers/{user_id}")
async def detach_organizer(
    partner_id: str, user_id: str, user: dict = Depends(get_current_user)
):
    _admin_only(user)
    res = await db.users.update_one(
        {"user_id": user_id, "marketing_partner_id": partner_id},
        {"$unset": {"marketing_partner_id": "", "marketing_partner_attached_at": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not attached")
    return {"ok": True}


# ---------- earnings ledger ----------

@router.get("/admin/marketing-partners/{partner_id}/earnings")
async def list_earnings(
    partner_id: str,
    user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    _admin_only(user)
    q: dict = {"partner_id": partner_id}
    if status:
        q["status"] = status
    cur = db.marketing_partner_earnings.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [doc async for doc in cur]


class MarkPaidIn(BaseModel):
    earning_ids: Optional[List[str]] = None  # if None → all unpaid for partner
    payout_reference: Optional[str] = None   # e.g. bank txn ID, manual note


@router.post("/admin/marketing-partners/{partner_id}/earnings/mark-paid")
async def mark_paid(
    partner_id: str,
    payload: MarkPaidIn,
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    batch_id = f"pbat_{uuid.uuid4().hex[:10]}"
    q: dict = {"partner_id": partner_id, "status": "unpaid"}
    if payload.earning_ids:
        q["earning_id"] = {"$in": payload.earning_ids}
    res = await db.marketing_partner_earnings.update_many(
        q,
        {
            "$set": {
                "status": "paid",
                "paid_at": utc_now(),
                "paid_by": user.get("user_id"),
                "payout_batch_id": batch_id,
                "payout_reference": payload.payout_reference or "",
            }
        },
    )
    return {"marked_paid": res.modified_count, "batch_id": batch_id}


# ---------- helper for the "assign organizer" autocomplete ----------

@router.get("/admin/marketing-partners-organizer-search")
async def search_organizers(
    q: str = Query("", min_length=0, max_length=80),
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    filter_q: dict = {"role": "organizer"}
    if q:
        filter_q["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    cur = db.users.find(
        filter_q,
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "marketing_partner_id": 1},
    ).limit(25)
    return [doc async for doc in cur]
