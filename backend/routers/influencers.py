"""Influencer / Creator marketplace.

Turns the existing per-event affiliate system into a full two-sided
marketplace where:

  • Any signed-in attendee or organizer can flip on "Influencer Mode" and
    fill out a public creator profile (handles, follower count, categories).
  • Organizers can mark each event as `affiliate_program_open=True` with a
    default commission %; influencers can then *self-join* the campaign
    with one click, which auto-creates a personalised affiliate code.
  • Influencers see a dashboard of all their campaigns with live
    clicks/conversions/earnings, plus a payouts tab backed by Stripe
    Connect Express (reusing the organizer payout plumbing — one
    Stripe account per user, used for both organizer payouts and
    influencer commissions).
  • A public marketplace at `/influencers` lets organizers browse and
    invite creators.
  • A UTM link generator lets organizers build trackable paid-ads URLs
    bound to an affiliate code (for Facebook / Google Ads attribution).

All collections this router touches:
  - users (flag `is_influencer`, `stripe_account_id` reused)
  - influencers   (creator profile)
  - affiliates    (extended with `influencer_id`)
  - events        (extended with `affiliate_program_open`,
                   `affiliate_default_commission_pct`)
  - influencer_payouts
"""
from __future__ import annotations

import os
import uuid
import logging
import asyncio
from typing import Optional, List
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["influencers"])

DEFAULT_COMMISSION_PCT = 5.0
PAYOUT_MIN_USD = 50.0


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SocialHandles(BaseModel):
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    twitter: Optional[str] = None
    youtube: Optional[str] = None
    facebook: Optional[str] = None


class InfluencerProfileIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    bio: Optional[str] = Field(default=None, max_length=600)
    social_handles: Optional[SocialHandles] = None
    follower_count_total: Optional[int] = Field(default=None, ge=0)
    categories: Optional[List[str]] = None
    city: Optional[str] = None
    avatar_url: Optional[str] = None


class JoinCampaignIn(BaseModel):
    event_id: str
    custom_code: Optional[str] = None


class UtmLinkIn(BaseModel):
    base_url: str
    source: str = Field(min_length=1, max_length=40)
    medium: str = Field(default="paid", max_length=40)
    campaign: str = Field(min_length=1, max_length=80)
    content: Optional[str] = Field(default=None, max_length=80)
    affiliate_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_stripe():
    api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured on the server")
    import stripe as _stripe
    _stripe.api_key = api_key
    return _stripe


def _slugify_code(name: str, suffix: str) -> str:
    base = "".join(ch for ch in (name or "").upper() if ch.isalnum())[:8] or "INF"
    return f"{base}-{suffix}".upper()


async def _public_origin() -> str:
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    return (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")


def _strip_user(doc: dict) -> dict:
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


# ---------------------------------------------------------------------------
# Profile management (private)
# ---------------------------------------------------------------------------

@router.post("/influencer/enable")
async def enable_influencer_mode(payload: InfluencerProfileIn, user: dict = Depends(get_current_user)):
    """Flip the user into influencer mode and (re)write their public creator profile.

    Idempotent — calling repeatedly updates the existing profile. Does NOT
    change the user's role (organizers stay organizers; attendees stay
    attendees), it just sets `is_influencer=true`.
    """
    handles = payload.social_handles.dict() if payload.social_handles else {}
    handles = {k: (v or "").strip().lstrip("@") or None for k, v in handles.items()}
    cats = [c.strip().lower() for c in (payload.categories or []) if c and c.strip()][:8]

    profile = {
        "user_id": user["user_id"],
        "display_name": payload.display_name.strip(),
        "bio": (payload.bio or "").strip() or None,
        "social_handles": handles,
        "follower_count_total": int(payload.follower_count_total or 0),
        "categories": cats,
        "city": (payload.city or "").strip() or None,
        "avatar_url": (payload.avatar_url or user.get("picture") or None),
        "is_active": True,
        "updated_at": utc_now().isoformat(),
    }
    existing = await db.influencers.find_one({"user_id": user["user_id"]})
    if existing:
        await db.influencers.update_one({"user_id": user["user_id"]}, {"$set": profile})
    else:
        profile["created_at"] = utc_now().isoformat()
        profile["payout_threshold"] = PAYOUT_MIN_USD
        await db.influencers.insert_one(profile)

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"is_influencer": True, "influencer_enabled_at": utc_now().isoformat()}},
    )
    profile.pop("_id", None)
    return {"ok": True, **profile}


@router.get("/influencer/me")
async def my_influencer_profile(user: dict = Depends(get_current_user)):
    prof = await db.influencers.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not prof:
        return {"enabled": False}
    # Tack on Stripe Connect status so the dashboard can show payout readiness
    stripe_ready = bool(user.get("stripe_payouts_enabled") and user.get("stripe_charges_enabled"))
    return {
        "enabled": True,
        "stripe_payouts_ready": stripe_ready,
        **prof,
    }


@router.post("/influencer/disable")
async def disable_influencer_mode(user: dict = Depends(get_current_user)):
    """Soft-disable — hides profile from marketplace but keeps history."""
    await db.influencers.update_one({"user_id": user["user_id"]}, {"$set": {"is_active": False}})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"is_influencer": False}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard — stats rollup
# ---------------------------------------------------------------------------

@router.get("/influencer/dashboard")
async def influencer_dashboard(user: dict = Depends(get_current_user)):
    prof = await db.influencers.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not prof:
        raise HTTPException(status_code=404, detail="Influencer profile not set up yet")

    # All affiliate codes owned by this influencer
    aff_cursor = db.affiliates.find(
        {"influencer_id": user["user_id"]},
        {"_id": 0},
    ).sort("created_at", -1)
    affiliates: List[dict] = []
    total_clicks = 0
    total_conversions = 0
    total_revenue = 0.0
    total_commission = 0.0
    async for a in aff_cursor:
        agg = await db.bookings.aggregate([
            {"$match": {"affiliate_code": a["code"], "status": "paid"}},
            {"$group": {"_id": None, "n": {"$sum": 1}, "rev": {"$sum": "$amount"}, "tickets": {"$sum": "$quantity"}}},
        ]).to_list(1)
        conv = agg[0]["n"] if agg else 0
        rev = round(agg[0]["rev"], 2) if agg else 0.0
        tickets = agg[0]["tickets"] if agg else 0
        commission = round(rev * float(a.get("commission_pct", 0)) / 100, 2)
        # Hydrate event name for display
        ev = await db.events.find_one({"event_id": a.get("event_id")}, {"_id": 0, "title": 1, "event_id": 1, "cover_image_url": 1, "starts_at": 1})
        affiliates.append({
            **a,
            "conversions": conv,
            "revenue_attributed": rev,
            "tickets_sold": tickets,
            "commission_owed": commission,
            "event": ev,
        })
        total_clicks += int(a.get("clicks", 0))
        total_conversions += conv
        total_revenue += rev
        total_commission += commission

    # Paid-out vs pending
    paid_agg = await db.influencer_payouts.aggregate([
        {"$match": {"influencer_id": user["user_id"], "status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    paid_total = round(paid_agg[0]["total"], 2) if paid_agg else 0.0
    pending_total = round(total_commission - paid_total, 2)

    return {
        "profile": prof,
        "summary": {
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "conversion_rate_pct": round((total_conversions / total_clicks * 100) if total_clicks else 0, 2),
            "total_revenue_attributed": round(total_revenue, 2),
            "total_commission_earned": round(total_commission, 2),
            "paid_out_total": paid_total,
            "pending_payout": max(0.0, pending_total),
        },
        "campaigns": affiliates,
    }


# ---------------------------------------------------------------------------
# Campaign browsing & self-join (the open marketplace flow)
# ---------------------------------------------------------------------------

@router.get("/influencer/campaigns/available")
async def available_campaigns(user: dict = Depends(get_current_user)):
    """Events with `affiliate_program_open=True` the influencer hasn't joined yet."""
    prof = await db.influencers.find_one({"user_id": user["user_id"]}, {"_id": 0, "categories": 1})
    if not prof:
        raise HTTPException(status_code=404, detail="Enable influencer mode first")
    already_joined = set()
    async for a in db.affiliates.find({"influencer_id": user["user_id"]}, {"_id": 0, "event_id": 1}):
        if a.get("event_id"):
            already_joined.add(a["event_id"])

    out = []
    async for ev in db.events.find(
        {"affiliate_program_open": True, "status": "approved"},
        {"_id": 0, "event_id": 1, "title": 1, "cover_image_url": 1,
         "starts_at": 1, "city": 1, "category": 1, "organizer_id": 1,
         "affiliate_default_commission_pct": 1},
    ).sort("starts_at", 1):
        if ev["event_id"] in already_joined:
            continue
        out.append({
            **ev,
            "default_commission_pct": float(ev.get("affiliate_default_commission_pct") or DEFAULT_COMMISSION_PCT),
        })
    return out


@router.post("/influencer/campaigns/join")
async def join_campaign(payload: JoinCampaignIn, user: dict = Depends(get_current_user)):
    """Self-join an event whose affiliate program is open. Creates an
    affiliate code owned by both the organizer and this influencer."""
    prof = await db.influencers.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not prof:
        raise HTTPException(status_code=404, detail="Enable influencer mode first")

    ev = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if not ev.get("affiliate_program_open"):
        raise HTTPException(status_code=403, detail="This event isn't accepting influencers yet")

    # Already joined? Return existing.
    existing = await db.affiliates.find_one(
        {"influencer_id": user["user_id"], "event_id": payload.event_id},
        {"_id": 0},
    )
    if existing:
        return {"already_joined": True, **existing}

    suffix = payload.event_id.split("_")[-1][:6].upper() if payload.event_id else uuid.uuid4().hex[:6].upper()
    candidate = (payload.custom_code or _slugify_code(prof["display_name"], suffix)).upper()[:24]
    # If the candidate clashes, append a random tail.
    if await db.affiliates.find_one({"code": candidate}):
        candidate = f"{candidate[:18]}-{uuid.uuid4().hex[:4].upper()}"

    commission_pct = float(ev.get("affiliate_default_commission_pct") or DEFAULT_COMMISSION_PCT)

    doc = {
        "affiliate_id": f"aff_{uuid.uuid4().hex[:12]}",
        "code": candidate,
        "partner_name": prof["display_name"],
        "partner_email": None,
        "commission_pct": commission_pct,
        "event_id": payload.event_id,
        "notes": "Self-joined via influencer marketplace",
        "active": True,
        "clicks": 0,
        "conversions": 0,
        "revenue_attributed": 0.0,
        "created_by": ev["organizer_id"],
        "influencer_id": user["user_id"],
        "created_at": utc_now().isoformat(),
    }
    await db.affiliates.insert_one(doc)
    doc.pop("_id", None)
    return {"joined": True, **doc}


# ---------------------------------------------------------------------------
# Creator promo codes assigned by admin (read-only, surfaces in /influencer hub)
# ---------------------------------------------------------------------------

@router.get("/influencer/my-codes")
async def my_creator_codes(user: dict = Depends(get_current_user)):
    """All admin-assigned creator promo codes for the signed-in creator.

    Lists every `discount_codes` row where `creator_id == me`, with the
    related event's title + cover, the code's discount/commission terms,
    usage stats, and the creator's running earnings (paid + unpaid).
    """
    items: list[dict] = []
    total_paid = 0.0
    total_unpaid = 0.0
    cur = db.discount_codes.find(
        {"creator_id": user["user_id"]},
        {"_id": 0},
    ).sort("created_at", -1)
    async for code in cur:
        ev = await db.events.find_one(
            {"event_id": code.get("event_id")},
            {"_id": 0, "event_id": 1, "title": 1, "cover_image_url": 1, "starts_at": 1, "city": 1, "venue": 1},
        )
        bookings_agg = await db.bookings.aggregate([
            {"$match": {
                "discount_code": code["code"],
                "event_id": code.get("event_id"),
                "status": {"$in": ["paid", "confirmed"]},
            }},
            {"$group": {"_id": None, "count": {"$sum": 1}, "tickets": {"$sum": "$quantity"}, "revenue": {"$sum": "$amount"}}},
        ]).to_list(1)
        bk = bookings_agg[0] if bookings_agg else {}
        earn_agg = await db.creator_earnings.aggregate([
            {"$match": {"code_id": code["code_id"], "creator_id": user["user_id"]}},
            {"$group": {"_id": "$status", "amount": {"$sum": "$earning_amount"}}},
        ]).to_list(5)
        paid_amt = round(sum(e["amount"] for e in earn_agg if e["_id"] == "paid"), 2)
        unpaid_amt = round(sum(e["amount"] for e in earn_agg if e["_id"] == "unpaid"), 2)
        total_paid += paid_amt
        total_unpaid += unpaid_amt
        items.append({
            "code_id": code["code_id"],
            "code": code["code"],
            "kind": code.get("kind", "percent"),
            "value": code.get("value"),
            "commission_percent": code.get("commission_percent"),
            "active": bool(code.get("active", True)),
            "max_uses": code.get("max_uses"),
            "uses_count": int(code.get("uses_count") or 0),
            "expires_at": code.get("expires_at"),
            "created_at": code.get("created_at"),
            "event": ev,
            "paid_bookings": int(bk.get("count") or 0),
            "tickets_sold": int(bk.get("tickets") or 0),
            "revenue": round(float(bk.get("revenue") or 0), 2),
            "earnings_paid": paid_amt,
            "earnings_unpaid": unpaid_amt,
        })
    return {
        "items": items,
        "summary": {
            "codes_total": len(items),
            "earnings_paid_total": round(total_paid, 2),
            "earnings_unpaid_total": round(total_unpaid, 2),
        },
    }


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

@router.get("/influencer/payouts")
async def list_payouts(user: dict = Depends(get_current_user)):
    items = []
    async for p in db.influencer_payouts.find({"influencer_id": user["user_id"]}, {"_id": 0}).sort("requested_at", -1):
        items.append(p)
    return items


@router.post("/influencer/payouts/request")
async def request_payout(user: dict = Depends(get_current_user)):
    """Compute current pending balance (campaign affiliates + creator codes)
    and create a payout request row when over the per-creator minimum threshold.

    Earnings come from TWO independent ledgers and the request must drain
    both — otherwise creators with only admin-assigned codes (no
    self-joined campaigns) would never see their money.
       1. `affiliates` → bookings.affiliate_code → rev × commission_pct
       2. `creator_earnings` (status='unpaid') → already-credited rows from
          /payments.py when a paid booking used an admin/organizer-assigned
          creator code.
    """
    prof = await db.influencers.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not prof:
        raise HTTPException(status_code=404, detail="Enable influencer mode first")
    if not user.get("stripe_payouts_enabled"):
        raise HTTPException(status_code=400, detail="Connect your Stripe account first to receive payouts")

    # 1) Legacy: self-joined affiliate campaigns.
    total_commission = 0.0
    async for a in db.affiliates.find({"influencer_id": user["user_id"]}, {"_id": 0, "code": 1, "commission_pct": 1}):
        agg = await db.bookings.aggregate([
            {"$match": {"affiliate_code": a["code"], "status": "paid"}},
            {"$group": {"_id": None, "rev": {"$sum": "$amount"}}},
        ]).to_list(1)
        if agg:
            total_commission += agg[0]["rev"] * float(a.get("commission_pct", 0)) / 100

    # 2) Creator codes: admin/organizer assigned codes credit a row in
    #    `creator_earnings` on every paid booking. Sum the unpaid rows.
    code_agg = await db.creator_earnings.aggregate([
        {"$match": {"creator_id": user["user_id"], "status": "unpaid"}},
        {"$group": {"_id": None, "total": {"$sum": "$earning_amount"}}},
    ]).to_list(1)
    code_earnings = round(code_agg[0]["total"], 2) if code_agg else 0

    paid_agg = await db.influencer_payouts.aggregate([
        {"$match": {"influencer_id": user["user_id"], "status": {"$in": ["pending", "approved", "paid"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    already_requested = paid_agg[0]["total"] if paid_agg else 0
    pending = round(total_commission + code_earnings - already_requested, 2)

    threshold = prof.get("payout_threshold", PAYOUT_MIN_USD)
    if pending < threshold:
        raise HTTPException(status_code=400, detail=f"Minimum payout is ${threshold:.2f}. Current pending: ${pending:.2f}")

    # Flip every unpaid creator_earnings row into 'requested' state so it
    # doesn't get double-counted in the next request. Admin payout settlement
    # flips them to 'paid' (or back to 'unpaid' on reject).
    payout_id = f"ipo_{uuid.uuid4().hex[:12]}"
    await db.creator_earnings.update_many(
        {"creator_id": user["user_id"], "status": "unpaid"},
        {"$set": {"status": "requested", "payout_id": payout_id, "requested_at": utc_now().isoformat()}},
    )

    doc = {
        "payout_id": payout_id,
        "influencer_id": user["user_id"],
        "amount": pending,
        "status": "pending",
        "stripe_transfer_id": None,
        "requested_at": utc_now().isoformat(),
        "notes": None,
        # Bookkeeping: which sources made up this payout.
        "from_affiliate_campaigns": round(total_commission, 2),
        "from_creator_codes": code_earnings,
    }
    await db.influencer_payouts.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Stripe Connect onboarding (reuse organizer's account on the same user)
# ---------------------------------------------------------------------------

class InfluencerStripeOnboardIn(BaseModel):
    return_url: str
    refresh_url: Optional[str] = None
    country: Optional[str] = None


@router.post("/influencer/stripe/onboard")
async def influencer_stripe_onboard(payload: InfluencerStripeOnboardIn, user: dict = Depends(get_current_user)):
    """Create or resume Stripe Connect Express onboarding for the influencer.

    Reuses `users.stripe_account_id` so a user who is both organizer and
    influencer has ONE Stripe account funding both flows.
    """
    stripe_sdk = _ensure_stripe()
    acct_id = user.get("stripe_account_id")

    if not acct_id:
        country = (payload.country or user.get("stripe_country") or "NZ").upper()
        try:
            acct = await asyncio.to_thread(
                stripe_sdk.Account.create,
                type="express",
                country=country,
                email=user.get("email"),
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                metadata={"platform_user_id": user["user_id"], "platform_role": "influencer"},
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Stripe couldn't create account: {exc}") from exc
        acct_id = acct["id"]
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"stripe_account_id": acct_id, "stripe_country": country, "stripe_created_at": utc_now().isoformat()}},
        )

    try:
        link = await asyncio.to_thread(
            stripe_sdk.AccountLink.create,
            account=acct_id,
            refresh_url=payload.refresh_url or payload.return_url,
            return_url=payload.return_url,
            type="account_onboarding",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Stripe couldn't generate onboarding link: {exc}") from exc

    return {"url": link["url"], "stripe_account_id": acct_id}


# ---------------------------------------------------------------------------
# Public marketplace
# ---------------------------------------------------------------------------

@router.get("/influencers")
async def list_marketplace(
    category: Optional[str] = None,
    city: Optional[str] = None,
    min_followers: int = 0,
    limit: int = 60,
):
    """Public discovery endpoint — anyone can browse active influencers."""
    q: dict = {"is_active": True}
    if category:
        q["categories"] = category.strip().lower()
    if city:
        q["city"] = {"$regex": f"^{city.strip()}", "$options": "i"}
    if min_followers > 0:
        q["follower_count_total"] = {"$gte": min_followers}

    items = []
    async for p in db.influencers.find(q, {"_id": 0}).sort("follower_count_total", -1).limit(min(limit, 100)):
        # Hide email/internal fields, expose only public fields
        items.append({
            "user_id": p["user_id"],
            "display_name": p.get("display_name"),
            "bio": p.get("bio"),
            "social_handles": p.get("social_handles") or {},
            "follower_count_total": p.get("follower_count_total", 0),
            "categories": p.get("categories") or [],
            "city": p.get("city"),
            "avatar_url": p.get("avatar_url"),
        })
    return items


@router.get("/influencers/{user_id}")
async def public_influencer_profile(user_id: str):
    p = await db.influencers.find_one({"user_id": user_id, "is_active": True}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Influencer not found")
    # Public stats
    agg = await db.affiliates.aggregate([
        {"$match": {"influencer_id": user_id}},
        {"$group": {"_id": None, "campaigns": {"$sum": 1}, "clicks": {"$sum": "$clicks"}}},
    ]).to_list(1)
    return {
        "user_id": p["user_id"],
        "display_name": p.get("display_name"),
        "bio": p.get("bio"),
        "social_handles": p.get("social_handles") or {},
        "follower_count_total": p.get("follower_count_total", 0),
        "categories": p.get("categories") or [],
        "city": p.get("city"),
        "avatar_url": p.get("avatar_url"),
        "stats": {
            "campaigns_total": agg[0]["campaigns"] if agg else 0,
            "total_clicks_driven": agg[0]["clicks"] if agg else 0,
        },
    }


# ---------------------------------------------------------------------------
# UTM generator (paid ads attribution)
# ---------------------------------------------------------------------------

@router.post("/organizer/utm-link")
async def generate_utm_link(payload: UtmLinkIn, user: dict = Depends(get_current_user)):
    """Wraps an event URL with utm_* params and (optionally) an affiliate code,
    so Facebook/Google Ads spend can be attributed back in Google Analytics
    or the platform's own affiliate dashboard."""
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Organizers only")
    try:
        parsed = urlparse(payload.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("invalid url")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Provide a valid http(s) URL") from exc

    qs = dict(parse_qsl(parsed.query))
    qs["utm_source"] = payload.source.strip()
    qs["utm_medium"] = payload.medium.strip()
    qs["utm_campaign"] = payload.campaign.strip()
    if payload.content:
        qs["utm_content"] = payload.content.strip()
    if payload.affiliate_code:
        code = payload.affiliate_code.strip().upper()
        aff = await db.affiliates.find_one(
            {"code": code, "active": True},
            {"_id": 0, "affiliate_id": 1, "created_by": 1},
        )
        if not aff:
            raise HTTPException(status_code=404, detail=f"Affiliate code {code} not found")
        # Only allow the organizer who owns it (or admin) to wrap it.
        if aff["created_by"] != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your affiliate code")
        qs["aff"] = code

    new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs), parsed.fragment))
    return {"url": new_url}
