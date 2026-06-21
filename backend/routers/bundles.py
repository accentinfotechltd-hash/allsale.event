"""Season passes / multi-event bundles (c2).

A bundle bundles N events the same organizer owns into a single purchase.
At checkout completion the webhook creates one paid booking per event, so
the existing ticketing / QR / refund infrastructure works untouched.

Schema:
  • bundle_id, organizer_id
  • title, description, image_url
  • event_ids:  list (all must belong to organizer)
  • price:      flat bundle price (any currency that matches across events)
  • currency:   ISO 4217
  • capacity:   max bundles to sell (null = unlimited)
  • sold_count: incremented on successful purchase
  • status:     active | inactive
  • tier_name:  optional pinned tier name to allocate inside each event;
                falls back to the cheapest tier when null.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now, STRIPE_API_KEY, logger

try:
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout, CheckoutSessionRequest,
    )
    _STRIPE_AVAILABLE = True
except Exception:  # pragma: no cover
    StripeCheckout = None  # type: ignore
    CheckoutSessionRequest = None  # type: ignore
    _STRIPE_AVAILABLE = False

router = APIRouter(tags=["bundles"])


class BundleIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    image_url: Optional[str] = None
    event_ids: List[str] = Field(min_length=2, max_length=20)
    price: float = Field(gt=0)
    currency: str = "NZD"
    capacity: Optional[int] = Field(default=None, ge=1)
    tier_name: Optional[str] = None


def _bundle_to_public(b: dict) -> dict:
    b.pop("_id", None)
    return b


@router.post("/organizer/bundles")
async def create_bundle(payload: BundleIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    # All events must belong to this organizer (or admin override)
    events = []
    async for e in db.events.find({"event_id": {"$in": payload.event_ids}}, {"_id": 0}):
        events.append(e)
    if len(events) != len(payload.event_ids):
        raise HTTPException(status_code=400, detail="One or more events not found")
    if user.get("role") != "admin":
        bad = [e["event_id"] for e in events if e.get("organizer_id") != user["user_id"]]
        if bad:
            raise HTTPException(status_code=403, detail=f"Not your events: {bad}")
    currencies = {(e.get("currency") or "NZD").upper() for e in events}
    if len(currencies) > 1:
        raise HTTPException(status_code=400, detail=f"All events must share a currency (got {currencies})")

    bundle_id = f"bnd_{uuid.uuid4().hex[:12]}"
    doc = {
        "bundle_id": bundle_id,
        "organizer_id": user["user_id"],
        "organizer_name": user["name"],
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "image_url": payload.image_url or (events[0].get("image_url") if events else None),
        "event_ids": payload.event_ids,
        "price": round(float(payload.price), 2),
        "currency": currencies.pop() if currencies else payload.currency.upper(),
        "capacity": payload.capacity,
        "sold_count": 0,
        "status": "active",
        "tier_name": payload.tier_name,
        "created_at": utc_now().isoformat(),
    }
    await db.bundles.insert_one(doc)
    return _bundle_to_public(doc)


@router.get("/organizer/bundles")
async def list_my_bundles(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    q = {} if user.get("role") == "admin" else {"organizer_id": user["user_id"]}
    out = []
    async for b in db.bundles.find(q, {"_id": 0}).sort("created_at", -1):
        out.append(b)
    return out


@router.patch("/organizer/bundles/{bundle_id}")
async def update_bundle(bundle_id: str, payload: dict, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    bundle = await db.bundles.find_one({"bundle_id": bundle_id}, {"_id": 0})
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    if user.get("role") != "admin" and bundle["organizer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your bundle")
    EDITABLE = {"title", "description", "image_url", "status", "capacity", "price"}
    update = {k: v for k, v in (payload or {}).items() if k in EDITABLE}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided")
    update["updated_at"] = utc_now().isoformat()
    await db.bundles.update_one({"bundle_id": bundle_id}, {"$set": update})
    refreshed = await db.bundles.find_one({"bundle_id": bundle_id}, {"_id": 0})
    return _bundle_to_public(refreshed)


@router.get("/bundles/{bundle_id}")
async def get_bundle(bundle_id: str):
    """Public view — embeds the included events so the page can render
    a single fetch on the frontend."""
    b = await db.bundles.find_one({"bundle_id": bundle_id}, {"_id": 0})
    if not b or b.get("status") != "active":
        raise HTTPException(status_code=404, detail="Bundle not found")
    events = []
    async for e in db.events.find({"event_id": {"$in": b["event_ids"]}}, {"_id": 0}):
        events.append({
            "event_id": e["event_id"],
            "title": e["title"],
            "date": e.get("date"),
            "venue": e.get("venue"),
            "city": e.get("city"),
            "image_url": e.get("image_url"),
        })
    # Preserve organizer's ordering
    ev_map = {e["event_id"]: e for e in events}
    b["events"] = [ev_map[eid] for eid in b["event_ids"] if eid in ev_map]
    # Compute "save vs separately" — sum cheapest tier price for each event.
    total_separate = 0.0
    async for e in db.events.find({"event_id": {"$in": b["event_ids"]}}, {"_id": 0}):
        tiers = e.get("tiers") or []
        if e.get("has_seatmap"):
            total_separate += float(e.get("seat_price") or 0)
        elif tiers:
            total_separate += min(float(t.get("price") or 0) for t in tiers)
    b["total_separate"] = round(total_separate, 2)
    b["savings"] = max(0.0, round(total_separate - b["price"], 2))
    return _bundle_to_public(b)


class BundlePurchaseIn(BaseModel):
    origin_url: str


@router.post("/bundles/{bundle_id}/purchase")
async def purchase_bundle(bundle_id: str, payload: BundlePurchaseIn, request: Request, user: dict = Depends(get_current_user)):
    """Create a Stripe Checkout session for the bundle. On webhook payment
    success we mint one booking per included event under this user."""
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Payments unavailable")
    bundle = await db.bundles.find_one({"bundle_id": bundle_id}, {"_id": 0})
    if not bundle or bundle.get("status") != "active":
        raise HTTPException(status_code=404, detail="Bundle not found")
    if bundle.get("capacity") is not None and bundle.get("sold_count", 0) >= bundle["capacity"]:
        raise HTTPException(status_code=409, detail="Bundle is sold out")

    host_url = str(request.base_url)
    fwd_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if fwd_proto == "https" and host_url.startswith("http://"):
        host_url = "https://" + host_url[len("http://"):]
    webhook_url = (os.environ.get("STRIPE_WEBHOOK_URL") or "").strip() or f"{host_url}api/webhook/stripe"

    try:
        stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Stripe init failed: {exc}") from exc

    success_url = f"{payload.origin_url}/bundles/{bundle_id}/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{payload.origin_url}/bundles/{bundle_id}"
    purchase_id = f"bp_{uuid.uuid4().hex[:12]}"
    req = CheckoutSessionRequest(
        amount=float(bundle["price"]),
        currency=bundle["currency"].lower(),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "kind": "bundle",
            "bundle_id": bundle_id,
            "purchase_id": purchase_id,
            "user_id": user["user_id"],
            "user_email": user.get("email", ""),
        },
    )
    try:
        session = await stripe.create_checkout_session(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Stripe rejected: {exc}") from exc

    await db.bundle_purchases.insert_one({
        "purchase_id": purchase_id,
        "bundle_id": bundle_id,
        "user_id": user["user_id"],
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "stripe_session_id": session.session_id,
        "amount": float(bundle["price"]),
        "currency": bundle["currency"],
        "status": "pending",
        "booking_ids": [],
        "created_at": utc_now().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id, "purchase_id": purchase_id}


async def finalize_bundle_purchase(purchase_id: str) -> bool:
    """Mint one booking per included event. Idempotent — returns True on the
    first successful run, False on retries."""
    p = await db.bundle_purchases.find_one({"purchase_id": purchase_id}, {"_id": 0})
    if not p or p["status"] != "pending":
        return False
    bundle = await db.bundles.find_one({"bundle_id": p["bundle_id"]}, {"_id": 0})
    if not bundle:
        return False

    # Allocate per-event tier (pinned tier_name or cheapest)
    per_event_share = round(p["amount"] / len(bundle["event_ids"]), 2)
    booking_ids = []
    from fees import compute_fees  # local import to avoid circular
    from core import gen_qr_data_url

    # Admin's commission settings are the single source of truth for fee math.
    plat_settings = await db.platform_settings.find_one({"key": "commission"}, {"_id": 0}) or {}
    admin_pct = plat_settings.get("commission_percent")
    admin_flat = plat_settings.get("commission_flat_fee_per_ticket")

    for event_id in bundle["event_ids"]:
        event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
        if not event:
            logger.warning(f"[bundle] event {event_id} missing during finalize")
            continue
        tier_name = "Bundle"
        if not event.get("has_seatmap"):
            tiers = event.get("tiers") or []
            pinned = next((t for t in tiers if t.get("name") == bundle.get("tier_name")), None)
            chosen = pinned or (min(tiers, key=lambda t: float(t.get("price") or 0)) if tiers else None)
            tier_name = chosen["name"] if chosen else "Bundle"

        booking_id = f"bkg_{uuid.uuid4().hex[:12]}"
        booking_doc = {
            "booking_id": booking_id, "event_id": event_id,
            "event_title": event["title"], "event_date": event.get("date"),
            "event_venue": event.get("venue"), "event_image": event.get("image_url"),
            "user_id": p["user_id"], "user_email": p["user_email"], "user_name": p["user_name"],
            "tier_name": tier_name, "quantity": 1, "seats": [],
            "subtotal": per_event_share,
            "currency": p["currency"], "status": "paid",
            "bundle_id": bundle["bundle_id"], "bundle_purchase_id": purchase_id,
            "created_at": utc_now().isoformat(),
            "paid_at": utc_now().isoformat(),
        }
        fees = compute_fees(per_event_share, p["currency"], platform_pct=admin_pct, stripe_flat=admin_flat)
        booking_doc.update({
            "face_value": round(fees.face_value, 2),
            "platform_fee": round(fees.platform_fee, 2),
            "stripe_fee_estimated": round(fees.stripe_fee, 2),
            "service_fee": round(fees.service_fee, 2),
            "amount": round(fees.buyer_total, 2),
        })
        qr_payload = f"AURA|{booking_id}|{event_id}|{p['user_id']}"
        booking_doc["qr_code"] = gen_qr_data_url(qr_payload)
        await db.bookings.insert_one(booking_doc)
        booking_ids.append(booking_id)

    r = await db.bundle_purchases.update_one(
        {"purchase_id": purchase_id, "status": "pending"},
        {"$set": {
            "status": "completed",
            "booking_ids": booking_ids,
            "completed_at": utc_now().isoformat(),
        }},
    )
    if r.modified_count == 0:
        return False

    # Bump sold counter
    await db.bundles.update_one(
        {"bundle_id": p["bundle_id"]},
        {"$inc": {"sold_count": 1}},
    )

    # Best-effort buyer email — one combined "you've bought a season pass" line.
    try:
        from emails import send_template_fireforget
        if p.get("user_email"):
            send_template_fireforget(
                "booking_confirmation",
                p["user_email"],
                {
                    "user_name": p.get("user_name") or "there",
                    "event_title": bundle["title"],
                    "event_date": "Multiple events",
                    "venue": bundle.get("organizer_name") or "Allsale",
                    "city": "",
                    "tier_name": "Season pass",
                    "quantity": len(booking_ids),
                    "amount": p["amount"],
                    "booking_id": purchase_id,
                },
                db,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Bundle confirmation email failed")
    return True


@router.get("/me/bundles")
async def my_bundle_purchases(user: dict = Depends(get_current_user)):
    out = []
    async for p in db.bundle_purchases.find(
        {"user_id": user["user_id"], "status": "completed"},
        {"_id": 0},
    ).sort("created_at", -1):
        bundle = await db.bundles.find_one({"bundle_id": p["bundle_id"]}, {"_id": 0, "title": 1, "image_url": 1, "event_ids": 1})
        p["bundle"] = bundle
        out.append(p)
    return out
