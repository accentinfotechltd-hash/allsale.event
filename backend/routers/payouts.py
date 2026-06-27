"""Commission & payouts: organizer balance, request payout, admin settle.

Schema:
- `platform_settings` (singleton doc, key="commission"): commission_percent, commission_flat_fee_per_ticket
- `payouts`: payout_id, organizer_id, gross, commission, flat_fees, net_amount,
  bookings_count, tickets_count, booking_ids[], period_start, period_end,
  status (requested|paid|rejected), requested_at, paid_at, paid_by, notes
- `bookings` gets an optional `payout_id` field once included in a payout.

Statuses flow: requested -> paid | rejected.
On reject we clear payout_id on bookings so they roll back into balance.
On paid we trigger the `organizer_payout_issued` email.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now
from emails import send_template_fireforget

router = APIRouter(tags=["payouts"])


DEFAULT_COMMISSION_PERCENT = 8.0
DEFAULT_FLAT_FEE_PER_TICKET = 0.50


# ---------------------------------------------------------------------------
# Settings (admin-configurable)
# ---------------------------------------------------------------------------
async def get_commission_settings() -> dict:
    doc = await db.platform_settings.find_one({"key": "commission"}, {"_id": 0})
    if not doc:
        doc = {
            "key": "commission",
            "commission_percent": DEFAULT_COMMISSION_PERCENT,
            "commission_flat_fee_per_ticket": DEFAULT_FLAT_FEE_PER_TICKET,
            "currency": "usd",
        }
        await db.platform_settings.update_one(
            {"key": "commission"}, {"$setOnInsert": doc}, upsert=True,
        )
    return {
        "commission_percent": doc.get("commission_percent", DEFAULT_COMMISSION_PERCENT),
        "commission_flat_fee_per_ticket": doc.get("commission_flat_fee_per_ticket", DEFAULT_FLAT_FEE_PER_TICKET),
        "currency": doc.get("currency", "usd"),
        "marketing_partners_auto_payout": bool(doc.get("marketing_partners_auto_payout", False)),
    }


class CommissionSettingsIn(BaseModel):
    commission_percent: float = Field(ge=0, le=50)
    commission_flat_fee_per_ticket: float = Field(ge=0, le=20)
    marketing_partners_auto_payout: Optional[bool] = None


@router.get("/admin/platform-settings")
async def admin_get_settings(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return await get_commission_settings()


@router.put("/admin/platform-settings")
async def admin_update_settings(payload: CommissionSettingsIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    updates = {
        "commission_percent": payload.commission_percent,
        "commission_flat_fee_per_ticket": payload.commission_flat_fee_per_ticket,
        "updated_at": utc_now().isoformat(),
        "updated_by": user["user_id"],
    }
    if payload.marketing_partners_auto_payout is not None:
        updates["marketing_partners_auto_payout"] = bool(payload.marketing_partners_auto_payout)
    await db.platform_settings.update_one(
        {"key": "commission"}, {"$set": updates}, upsert=True
    )
    return await get_commission_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_commission(gross: float, tickets: int, percent: float, flat_per_ticket: float) -> tuple[float, float, float]:
    commission = round(gross * (percent / 100.0), 2)
    flat_fees = round(tickets * flat_per_ticket, 2)
    net = round(max(0.0, gross - commission - flat_fees), 2)
    return commission, flat_fees, net


async def _get_organizer_event_ids(organizer_id: str) -> list[str]:
    ids = []
    async for e in db.events.find({"organizer_id": organizer_id}, {"_id": 0, "event_id": 1}):
        ids.append(e["event_id"])
    return ids


async def _eligible_bookings_for_payout(organizer_id: str) -> list[dict]:
    """Paid bookings, not yet attached to any payout, for this organizer's events."""
    event_ids = await _get_organizer_event_ids(organizer_id)
    if not event_ids:
        return []
    items = []
    async for b in db.bookings.find(
        {"event_id": {"$in": event_ids}, "status": "paid", "payout_id": {"$in": [None]}},
        {"_id": 0},
    ).sort("paid_at", 1):
        items.append(b)
    # Mongo `{"$in": [None]}` also matches "missing" field in motor, but to be safe also include docs without the field
    if not items:
        async for b in db.bookings.find(
            {"event_id": {"$in": event_ids}, "status": "paid", "payout_id": {"$exists": False}},
            {"_id": 0},
        ).sort("paid_at", 1):
            items.append(b)
    return items


# ---------------------------------------------------------------------------
# Organizer endpoints
# ---------------------------------------------------------------------------
@router.get("/organizer/payouts/balance")
async def organizer_balance(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    settings = await get_commission_settings()
    bookings = await _eligible_bookings_for_payout(user["user_id"])
    # SINGLE SOURCE OF TRUTH: `b.face_value` is what the organizer earns on
    # each booking (set by `compute_fees()` in routers/bookings.py). In
    # exclusive mode it equals the ticket price; in absorb mode it equals
    # ticket_price minus platform + Stripe fees. NO second commission
    # deduction at payout time — the platform fee was already routed to
    # Allsale via compute_fees at checkout. Fixes the double-counting bug
    # where the org was getting MORE than their face value.
    gross = round(sum(b.get("face_value", b.get("amount", 0)) for b in bookings), 2)
    tickets = sum(b.get("quantity", 0) for b in bookings)
    # Kept the variables for backwards-compatibility with the frontend payload
    # but they're now informational (always 0 — surfacing them lets the UI
    # render a clean "no further deductions" hint).
    commission = 0.0
    flat_fees = 0.0
    net = gross

    # Lifetime totals across all of this organizer's payouts (paid + requested + rejected)
    pipeline_paid = {"organizer_id": user["user_id"], "status": "paid"}
    lifetime_paid = 0.0
    paid_count = 0
    async for p in db.payouts.find(pipeline_paid, {"_id": 0, "net_amount": 1}):
        lifetime_paid += p.get("net_amount", 0)
        paid_count += 1

    pending = 0.0
    async for p in db.payouts.find(
        {"organizer_id": user["user_id"], "status": "requested"}, {"_id": 0, "net_amount": 1},
    ):
        pending += p.get("net_amount", 0)

    return {
        "available": {
            "gross": gross,
            "commission": commission,
            "flat_fees": flat_fees,
            "net": net,
            "tickets": tickets,
            "bookings": len(bookings),
        },
        "lifetime_paid": round(lifetime_paid, 2),
        "lifetime_paid_count": paid_count,
        "pending": round(pending, 2),
        "settings": settings,
    }


class PayoutRequestIn(BaseModel):
    notes: Optional[str] = None


@router.post("/organizer/payouts/request")
async def organizer_request_payout(payload: PayoutRequestIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")

    bookings = await _eligible_bookings_for_payout(user["user_id"])
    if not bookings:
        raise HTTPException(status_code=400, detail="No eligible earnings to request")

    settings = await get_commission_settings()
    # SINGLE SOURCE OF TRUTH (see comment in /balance above).
    gross = round(sum(b.get("face_value", b.get("amount", 0)) for b in bookings), 2)
    tickets = sum(b.get("quantity", 0) for b in bookings)
    commission = 0.0
    flat_fees = 0.0
    net = gross

    payout_id = "pyt_" + uuid4().hex[:12]
    booking_ids = [b["booking_id"] for b in bookings]
    paid_ats = [b.get("paid_at") for b in bookings if b.get("paid_at")]

    # Auto-apply available referral / organizer credits — capped at the
    # current net payout so we don't go negative. Each applied credit gets
    # flipped to status=applied and stamped with this payout_id; if admin
    # later rejects the payout, the credits are released back automatically
    # in admin_reject_payout.
    credit_total = 0.0
    applied_credit_ids = []
    async for c in db.organizer_credits.find(
        {"user_id": user["user_id"], "status": "available"},
        {"_id": 0, "credit_id": 1, "amount": 1},
    ).sort("created_at", 1):
        if credit_total >= net:
            break
        remaining = net - credit_total
        take = min(float(c.get("amount") or 0), remaining)
        if take <= 0:
            continue
        credit_total = round(credit_total + take, 2)
        applied_credit_ids.append({"credit_id": c["credit_id"], "amount": take})
    if applied_credit_ids:
        await db.organizer_credits.update_many(
            {"credit_id": {"$in": [a["credit_id"] for a in applied_credit_ids]}},
            {"$set": {"status": "applied", "applied_to_payout_id": payout_id, "applied_at": utc_now().isoformat()}},
        )

    payout_doc = {
        "payout_id": payout_id,
        "organizer_id": user["user_id"],
        "organizer_name": user.get("name"),
        "organizer_email": user.get("email"),
        "gross": gross,
        "commission": commission,
        "flat_fees": flat_fees,
        "net_amount": net,
        "credit_applied": round(credit_total, 2),
        "credit_ids_applied": [a["credit_id"] for a in applied_credit_ids],
        "bookings_count": len(bookings),
        "tickets_count": tickets,
        "booking_ids": booking_ids,
        "period_start": min(paid_ats) if paid_ats else None,
        "period_end": max(paid_ats) if paid_ats else None,
        "status": "requested",
        "requested_at": utc_now().isoformat(),
        "notes": payload.notes,
        "currency": settings.get("currency", "usd"),
        "commission_settings_snapshot": {
            "commission_percent": settings["commission_percent"],
            "commission_flat_fee_per_ticket": settings["commission_flat_fee_per_ticket"],
        },
    }
    await db.payouts.insert_one(payout_doc)
    # Mark bookings as included in this payout (locks them out of future requests)
    await db.bookings.update_many(
        {"booking_id": {"$in": booking_ids}, "payout_id": {"$exists": False}},
        {"$set": {"payout_id": payout_id}},
    )
    payout_doc.pop("_id", None)
    return payout_doc


@router.get("/organizer/payouts")
async def organizer_list_payouts(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    items = []
    async for p in db.payouts.find({"organizer_id": user["user_id"]}, {"_id": 0}).sort("requested_at", -1):
        items.append(p)
    return items


# ---------------------------------------------------------------------------
# Admin endpoints (settle / reject)
# ---------------------------------------------------------------------------
class MarkPaidIn(BaseModel):
    reference: Optional[str] = None  # bank ref / transfer ID
    notes: Optional[str] = None


class RejectIn(BaseModel):
    reason: str


@router.get("/admin/payouts")
async def admin_list_payouts(
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    query: dict = {}
    if status in ("requested", "paid", "rejected"):
        query["status"] = status
    items = []
    async for p in db.payouts.find(query, {"_id": 0}).sort("requested_at", -1).limit(500):
        items.append(p)

    # Totals
    totals = {"requested": 0.0, "paid": 0.0, "rejected": 0.0, "count": {"requested": 0, "paid": 0, "rejected": 0}}
    async for p in db.payouts.find({}, {"_id": 0, "status": 1, "net_amount": 1}):
        s = p.get("status")
        if s in totals:
            totals[s] += p.get("net_amount", 0)
            totals["count"][s] += 1
    totals["requested"] = round(totals["requested"], 2)
    totals["paid"] = round(totals["paid"], 2)
    totals["rejected"] = round(totals["rejected"], 2)
    return {"items": items, "totals": totals}


@router.post("/admin/payouts/{payout_id}/mark-paid")
async def admin_mark_paid(payout_id: str, payload: MarkPaidIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    payout = await db.payouts.find_one({"payout_id": payout_id}, {"_id": 0})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout["status"] != "requested":
        raise HTTPException(status_code=400, detail=f"Cannot mark {payout['status']} payout as paid")

    now_iso = utc_now().isoformat()
    await db.payouts.update_one(
        {"payout_id": payout_id},
        {"$set": {
            "status": "paid",
            "paid_at": now_iso,
            "paid_by": user["user_id"],
            "transfer_reference": payload.reference,
            "admin_notes": payload.notes,
        }},
    )

    # Email organizer
    if payout.get("organizer_email"):
        period = ""
        if payout.get("period_start") and payout.get("period_end"):
            try:
                ps = payout["period_start"][:10]
                pe = payout["period_end"][:10]
                period = f"{ps} → {pe}"
            except Exception:
                period = ""
        send_template_fireforget("organizer_payout_issued", payout["organizer_email"], {
            "organizer_name": payout.get("organizer_name") or "organizer",
            "payout_id": payout_id,
            "amount": payout.get("net_amount", 0),
            "currency": payout.get("currency") or "NZD",
            "bookings_count": payout.get("bookings_count", 0),
            "period": period,
        }, db)

    return {"ok": True, "payout_id": payout_id, "status": "paid"}


@router.post("/admin/payouts/{payout_id}/reject")
async def admin_reject_payout(payout_id: str, payload: RejectIn, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    payout = await db.payouts.find_one({"payout_id": payout_id}, {"_id": 0})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout["status"] != "requested":
        raise HTTPException(status_code=400, detail=f"Cannot reject {payout['status']} payout")

    # Roll bookings back: they become eligible for a future payout request
    await db.bookings.update_many(
        {"booking_id": {"$in": payout.get("booking_ids", [])}, "payout_id": payout_id},
        {"$unset": {"payout_id": ""}},
    )
    # Release any credits that were auto-applied to this payout — they go
    # back to `available` so the organizer can use them on the next request.
    credit_ids = payout.get("credit_ids_applied") or []
    if credit_ids:
        await db.organizer_credits.update_many(
            {"credit_id": {"$in": credit_ids}, "status": "applied", "applied_to_payout_id": payout_id},
            {"$set": {"status": "available"}, "$unset": {"applied_to_payout_id": "", "applied_at": ""}},
        )
    await db.payouts.update_one(
        {"payout_id": payout_id},
        {"$set": {
            "status": "rejected",
            "rejected_at": utc_now().isoformat(),
            "rejected_by": user["user_id"],
            "rejection_reason": payload.reason,
        }},
    )
    return {"ok": True, "payout_id": payout_id, "status": "rejected"}
