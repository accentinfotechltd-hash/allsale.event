"""Organizer referral program (d2).

Mechanics:
  • Every existing organizer has a deterministic referral code (ref_xxxx)
    derived from their user_id. Share the link `?ref=<code>` anywhere.
  • New users that sign up via that link get `referred_by_code` stamped on
    their user doc.
  • The FIRST time the referred user's event is approved, the REFERRER
    gets a $50 NZD platform credit. The new organizer doesn't receive a
    welcome bonus — keeps the program lean and prevents self-referral
    abuse via burner accounts. This is captured as an `organizer_credits`
    ledger row — admins apply it manually against the next payout.
  • Credits don't auto-deduct from organizer revenue. Surface them in the
    referral dashboard + nudge the organizer to mention them on payout day.

Flat amount ($50) is simple, predictable, and low-fraud — aligns with the
user-stated "$50 referrer-only credit on first event" plan.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now, logger

router = APIRouter(tags=["organizer_referrals"])

REFERRAL_CREDIT_NZD = float(os.environ.get("REFERRAL_CREDIT_NZD", "50"))


def _ref_code_for(user_id: str) -> str:
    """Deterministic short code. Stable for a given user_id so existing links
    keep working even if we add a `code` column later."""
    return "ref_" + user_id[-8:].lower()


async def _grant_credit(user_id: str, amount: float, reason: str, related_event: Optional[str] = None) -> str:
    credit_id = f"crd_{uuid.uuid4().hex[:12]}"
    await db.organizer_credits.insert_one({
        "credit_id": credit_id,
        "user_id": user_id,
        "amount": round(float(amount), 2),
        "currency": "NZD",
        "reason": reason,
        "related_event_id": related_event,
        "status": "available",  # available | applied | void
        "created_at": utc_now().isoformat(),
    })
    return credit_id


async def maybe_grant_referral_on_first_approval(event: dict) -> bool:
    """Called after an event flips to `approved`. If the organizer was
    referred and this is their FIRST approved event, grant credit to both
    parties. Idempotent — checks for a prior referral_credit on this user
    before granting."""
    organizer_id = event.get("organizer_id")
    if not organizer_id:
        return False
    organizer = await db.users.find_one({"user_id": organizer_id}, {"_id": 0})
    if not organizer:
        return False
    ref_code = (organizer.get("referred_by_code") or "").strip().lower()
    if not ref_code or not ref_code.startswith("ref_"):
        return False
    # Already credited? bail. We stamp the organizer doc once the credit is
    # granted (rather than checking the credits ledger), so removing the
    # referee-side bonus doesn't break idempotency.
    if organizer.get("referral_credited_at"):
        return False
    # Count this organizer's approved events (>= 1 means this is the moment).
    approved_count = await db.events.count_documents(
        {"organizer_id": organizer_id, "status": "approved"}
    )
    if approved_count < 1:
        return False
    # Resolve the referrer
    referrer = None
    async for u in db.users.find({"role": {"$in": ["organizer", "admin"]}}, {"_id": 0}):
        if _ref_code_for(u["user_id"]) == ref_code:
            referrer = u
            break
    if not referrer:
        logger.info(f"[referral] code {ref_code} did not match any organizer — skipping")
        return False
    # Don't credit if user referred themselves (paranoia)
    if referrer["user_id"] == organizer_id:
        return False
    # Grant credit ONLY to the referrer. The newly-onboarded organizer
    # no longer gets a welcome bonus — keeps the program tight against
    # burner-account self-referral abuse.
    await _grant_credit(
        referrer["user_id"], REFERRAL_CREDIT_NZD,
        reason="referral_payout", related_event=event["event_id"],
    )
    # Stamp the referred organizer so a subsequent re-approval of the same
    # event (or another early event) doesn't credit the referrer twice.
    await db.users.update_one(
        {"user_id": organizer_id},
        {"$set": {"referral_credited_at": utc_now().isoformat()}},
    )
    logger.info(
        f"[referral] credited ${REFERRAL_CREDIT_NZD} NZD to "
        f"referrer={referrer['user_id']} (no bonus for referred={organizer_id})"
    )
    # Best-effort email to the referrer only
    try:
        from emails import send_template_fireforget
        if referrer.get("email"):
            send_template_fireforget(
                "organizer_payout_issued",
                referrer["email"],
                {
                    "organizer_name": referrer.get("name", "organizer"),
                    "amount": REFERRAL_CREDIT_NZD,
                    "event_title": f"Referral reward — {organizer.get('name','your friend')} just launched!",
                },
                db,
            )
    except Exception:  # noqa: BLE001
        logger.exception("[referral] notification email failed")
    return True


# -------- API --------

@router.get("/organizer/referral")
async def my_referral_stats(user: dict = Depends(get_current_user)):
    """Returns my referral code + stats: signups, qualified events, credits."""
    await require_role(user, "organizer", "admin")
    code = _ref_code_for(user["user_id"])
    # How many users joined with my code?
    signups = await db.users.count_documents({"referred_by_code": code})
    qualified = await db.organizer_credits.count_documents(
        {"user_id": user["user_id"], "reason": "referral_payout"}
    )
    credits_total = 0.0
    async for c in db.organizer_credits.find(
        {"user_id": user["user_id"], "status": "available"}, {"_id": 0, "amount": 1}
    ):
        credits_total += float(c.get("amount") or 0)
    public_origin = (os.environ.get("APP_PUBLIC_URL") or "https://allsale.events").rstrip("/")
    return {
        "code": code,
        "share_url": f"{public_origin}/signup?ref={code}",
        "signups": signups,
        "qualified": qualified,
        "available_credit_nzd": round(credits_total, 2),
        "credit_per_referral_nzd": REFERRAL_CREDIT_NZD,
    }


@router.get("/organizer/credits")
async def my_credits(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    out = []
    async for c in db.organizer_credits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        out.append(c)
    return out


class StampReferralIn(BaseModel):
    ref_code: str = Field(min_length=4, max_length=32)


@router.post("/auth/register/stamp-referral")
async def stamp_referral(payload: StampReferralIn, user: dict = Depends(get_current_user)):
    """Optional post-signup step: stamp the user's row with the referral code
    they used. Frontend calls this right after register. We avoid embedding
    this into /auth/register to keep that endpoint pristine."""
    code = payload.ref_code.strip().lower()
    if not code.startswith("ref_"):
        raise HTTPException(status_code=400, detail="Invalid referral code")
    # Don't allow self-referral
    if code == _ref_code_for(user["user_id"]):
        raise HTTPException(status_code=400, detail="Cannot refer yourself")
    # Only allow stamping if not already stamped
    existing = await db.users.find_one(
        {"user_id": user["user_id"]}, {"_id": 0, "referred_by_code": 1}
    )
    if existing and existing.get("referred_by_code"):
        return {"ok": False, "reason": "already_stamped"}
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"referred_by_code": code, "referred_at": utc_now().isoformat()}},
    )
    return {"ok": True}
