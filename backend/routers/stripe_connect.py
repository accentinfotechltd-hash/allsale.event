"""Stripe Connect Express — organizer onboarding & status.

Flow (separate-charges-and-transfers / hold-until-event model):
  1. Organizer clicks "Connect with Stripe" → `POST /stripe/connect/onboard`.
  2. Backend lazily creates a Stripe **Express** Connect account if the user
     doesn't have one (`stripe_account_id` is empty), then mints a fresh
     `AccountLink` and returns its URL.
  3. The organizer completes KYC on Stripe's hosted onboarding pages.
  4. Stripe redirects them back to `return_url`. Frontend polls
     `GET /stripe/connect/status` to refresh the badge.
  5. Stripe also calls our `/api/webhook/stripe/connect` with
     `account.updated` events — we mirror `charges_enabled`,
     `payouts_enabled`, `details_submitted` on the user record so the
     dashboard reflects truth without a manual poll.

We do NOT add `application_fee_amount` to the buyer checkout — the platform
collects 100% of the ticket money into its own Stripe balance and disburses
the organizer share (minus platform fee) via a `Transfer` after the event
date (Phase 2 — scheduler). That gives Allsale full control over refunds
and chargebacks during the event hold window.

Env vars:
  STRIPE_API_KEY               — platform secret key (already used elsewhere).
  STRIPE_CONNECT_WEBHOOK_SECRET — set after creating the Connect webhook in
                                  the Stripe dashboard. Without it we accept
                                  any payload (dev/sandbox only).
  PLATFORM_FEE_BPS             — basis points (500 = 5%). Used by the
                                  payout scheduler in phase 2.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import db, get_current_user, utc_now, STRIPE_API_KEY, logger

try:
    import stripe as _stripe_sdk  # type: ignore
    _STRIPE_AVAILABLE = True
except Exception:  # pragma: no cover
    _stripe_sdk = None  # type: ignore
    _STRIPE_AVAILABLE = False


router = APIRouter(tags=["stripe-connect"])


def _ensure_stripe() -> None:
    if not _STRIPE_AVAILABLE or not STRIPE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe Connect is not configured — set STRIPE_API_KEY first.",
        )
    _stripe_sdk.api_key = STRIPE_API_KEY


def _connect_status_payload(u: dict) -> dict:
    return {
        "stripe_account_id": u.get("stripe_account_id"),
        "stripe_charges_enabled": bool(u.get("stripe_charges_enabled")),
        "stripe_payouts_enabled": bool(u.get("stripe_payouts_enabled")),
        "stripe_details_submitted": bool(u.get("stripe_details_submitted")),
        "stripe_requirements_due": u.get("stripe_requirements_due") or [],
        "stripe_last_synced_at": u.get("stripe_last_synced_at"),
    }


async def _sync_account_from_stripe(account_id: str) -> Optional[dict]:
    """Pull the latest Connect account state and mirror it on the user row.
    Returns the updated user doc, or None if no user owns this account_id."""
    _ensure_stripe()
    try:
        acct = await asyncio.to_thread(_stripe_sdk.Account.retrieve, account_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[stripe-connect] sync failed for {account_id}: {exc}")
        return None
    requirements = acct.get("requirements") or {}
    currently_due = requirements.get("currently_due") or []
    update = {
        "stripe_charges_enabled": bool(acct.get("charges_enabled")),
        "stripe_payouts_enabled": bool(acct.get("payouts_enabled")),
        "stripe_details_submitted": bool(acct.get("details_submitted")),
        "stripe_requirements_due": list(currently_due),
        "stripe_last_synced_at": utc_now().isoformat(),
    }
    res = await db.users.update_one(
        {"stripe_account_id": account_id},
        {"$set": update},
    )
    if res.matched_count == 0:
        return None
    return await db.users.find_one({"stripe_account_id": account_id}, {"_id": 0})


class OnboardIn(BaseModel):
    return_url: str  # frontend URL to send the organizer back to (e.g. /organizer)
    refresh_url: Optional[str] = None  # used by Stripe if the AccountLink expires
    country: Optional[str] = None  # ISO 3166-1 alpha-2 (NZ, AU, US, IN, …)


@router.post("/stripe/connect/onboard")
async def onboard(payload: OnboardIn, user: dict = Depends(get_current_user)):
    """Create-or-resume Connect Express onboarding for the calling organizer.

    If we already have a `stripe_account_id` but Stripe rejects it (deleted in
    dashboard, wrong key mode, etc.), we wipe the stored ID and create a
    fresh Express account on the next attempt so the user doesn't get stuck.
    """
    _ensure_stripe()
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Only organizers can connect Stripe")

    acct_id = user.get("stripe_account_id")

    async def _create_account() -> str:
        country = (payload.country or user.get("stripe_country") or user.get("country") or "NZ").upper()
        try:
            acct = await asyncio.to_thread(
                _stripe_sdk.Account.create,
                type="express",
                country=country,
                email=user.get("email"),
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                metadata={
                    "platform_user_id": user["user_id"],
                    "platform_role": user.get("role", "organizer"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[stripe-connect] Account.create failed: {exc}")
            raise HTTPException(status_code=502, detail=f"Stripe couldn't create the account — {exc}") from exc
        new_id = acct["id"]
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "stripe_account_id": new_id,
                "stripe_country": country,
                "stripe_created_at": utc_now().isoformat(),
            }},
        )
        return new_id

    async def _make_link(account_id: str) -> dict:
        refresh = payload.refresh_url or payload.return_url
        link = await asyncio.to_thread(
            _stripe_sdk.AccountLink.create,
            account=account_id,
            refresh_url=refresh,
            return_url=payload.return_url,
            type="account_onboarding",
        )
        return {"url": link["url"], "expires_at": link.get("expires_at"), "stripe_account_id": account_id}

    if not acct_id:
        acct_id = await _create_account()

    try:
        return await _make_link(acct_id)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # If the stored account ID is unknown/invalid (e.g. test-mode ID with
        # a live key, or it was deleted in the Stripe dashboard) reset and
        # try once more with a fresh account.
        recoverable = any(
            tag in msg.lower()
            for tag in ("no such account", "does not exist", "testmode", "invalid request", "permission")
        )
        if recoverable:
            logger.warning(f"[stripe-connect] stale acct {acct_id} ({msg[:120]}) — recreating")
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$unset": {
                    "stripe_account_id": "",
                    "stripe_country": "",
                    "stripe_created_at": "",
                    "stripe_charges_enabled": "",
                    "stripe_payouts_enabled": "",
                    "stripe_details_submitted": "",
                    "stripe_requirements_due": "",
                    "stripe_last_synced_at": "",
                }},
            )
            try:
                new_id = await _create_account()
                return await _make_link(new_id)
            except HTTPException:
                raise
            except Exception as exc2:  # noqa: BLE001
                logger.exception(f"[stripe-connect] recovery failed: {exc2}")
                raise HTTPException(status_code=502, detail=f"Stripe rejected the link — {exc2}") from exc2
        logger.exception(f"[stripe-connect] AccountLink.create failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Stripe couldn't generate the link — {exc}") from exc


@router.get("/stripe/connect/status")
async def status(user: dict = Depends(get_current_user)):
    """Return current Connect state. Re-syncs from Stripe if we have an
    account_id and the cached state is stale (>60s) — keeps the badge fresh
    when the user comes back from Stripe's onboarding without us having
    received the webhook yet.

    Wrapped defensively so a stale `stripe_account_id` (deleted in Stripe
    dashboard, wrong mode, etc.) never produces a bare HTTP 500 for the
    frontend — we surface the cached state and let the user re-onboard.
    """
    try:
        acct_id = user.get("stripe_account_id")
        if not acct_id:
            return _connect_status_payload(user)

        last = user.get("stripe_last_synced_at")
        is_stale = True
        if last:
            try:
                from datetime import datetime, timezone, timedelta
                then = datetime.fromisoformat(last)
                if then.tzinfo is None:
                    then = then.replace(tzinfo=timezone.utc)
                is_stale = (utc_now() - then) > timedelta(seconds=60)
            except Exception:  # noqa: BLE001
                is_stale = True

        if is_stale and _STRIPE_AVAILABLE and STRIPE_API_KEY:
            try:
                refreshed = await _sync_account_from_stripe(acct_id)
                if refreshed:
                    user = refreshed
            except Exception as exc:  # noqa: BLE001
                # Stale or mismatched-mode account ID — log + fall back to
                # cached state rather than 500ing the page.
                logger.warning(f"[stripe-connect] status sync failed for {acct_id}: {exc}")
        return _connect_status_payload(user)
    except Exception as exc:  # noqa: BLE001  (last-resort guard)
        logger.exception(f"[stripe-connect] status crashed: {exc}")
        return {
            "stripe_account_id": user.get("stripe_account_id"),
            "stripe_charges_enabled": False,
            "stripe_payouts_enabled": False,
            "stripe_details_submitted": False,
            "stripe_requirements_due": [],
            "stripe_last_synced_at": None,
            "_warning": f"Could not refresh Stripe state: {str(exc)[:200]}",
        }


@router.post("/stripe/connect/dashboard-link")
async def dashboard_link(user: dict = Depends(get_current_user)):
    """Generate a one-time login URL for the organizer's Stripe Express
    dashboard (where they manage their bank info, payouts, taxes)."""
    _ensure_stripe()
    acct_id = user.get("stripe_account_id")
    if not acct_id:
        raise HTTPException(status_code=400, detail="No Stripe Connect account yet")
    try:
        link = await asyncio.to_thread(_stripe_sdk.Account.create_login_link, acct_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[stripe-connect] login_link failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Stripe rejected the link: {exc}") from exc
    return {"url": link["url"]}


@router.post("/stripe/connect/reset")
async def reset_connect(user: dict = Depends(get_current_user)):
    """Wipe the user's Stripe Connect fields so the next "Connect with Stripe"
    click starts from scratch. Useful when an account got stuck in a bad mode
    (test ID with live key, deleted in Stripe dashboard, etc.).

    Safe to call repeatedly. Does NOT delete the account on Stripe's side —
    just unhooks it from this user record. If the user is mid-onboarding on
    Stripe's hosted page, they can complete and we'll re-link via webhook,
    but a fresh "Connect with Stripe" click will create a brand-new account.
    """
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Only organizers can reset")
    prev = user.get("stripe_account_id")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$unset": {
            "stripe_account_id": "",
            "stripe_country": "",
            "stripe_created_at": "",
            "stripe_charges_enabled": "",
            "stripe_payouts_enabled": "",
            "stripe_details_submitted": "",
            "stripe_requirements_due": "",
            "stripe_last_synced_at": "",
        }},
    )
    logger.info(f"[stripe-connect] reset for user={user['user_id']} (was {prev})")
    return {"ok": True, "previous_account_id": prev}


# ---------- Webhook (Connect events) ----------
@router.post("/webhook/stripe/connect")
async def connect_webhook(request: Request):
    """Listens for `account.updated` (and a few related Connect events) so we
    can mirror onboarding state without round-trips."""
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Stripe not available")
    body = await request.body()
    secret = os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET") or ""
    sig = request.headers.get("stripe-signature") or ""
    payload: dict
    if secret:
        try:
            event = _stripe_sdk.Webhook.construct_event(body, sig, secret)
            payload = dict(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[stripe-connect] webhook signature rejected: {exc}")
            raise HTTPException(status_code=400, detail="Invalid signature") from exc
    else:
        # No secret configured (dev/sandbox) — accept JSON as-is and just log.
        import json as _json
        try:
            payload = _json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        logger.warning("[stripe-connect] webhook secret not set — accepting unverified payload")

    event_type = payload.get("type") or ""
    data = (payload.get("data") or {}).get("object") or {}
    acct_id = data.get("id") if event_type.startswith("account.") else data.get("account") or payload.get("account")

    if event_type == "account.updated" and acct_id:
        refreshed = await _sync_account_from_stripe(acct_id)
        logger.info(f"[stripe-connect] account.updated mirrored for {acct_id} (user={(refreshed or {}).get('user_id')})")
    else:
        # Future events: transfer.created, transfer.failed, payout.paid —
        # log them for now; payouts router (phase 2) will react.
        logger.info(f"[stripe-connect] webhook noop: type={event_type} acct={acct_id}")
    return {"received": True}


# ---------- Event payouts (Batch 2) ----------
from connect_payouts_engine import (  # noqa: E402  (kept here so /webhook stays compact above)
    _attempt_event_payout,
    PAYOUT_HOLD_HOURS,
    PLATFORM_FEE_BPS,
)


@router.get("/organizer/event-payouts")
async def organizer_event_payouts(user: dict = Depends(get_current_user)):
    """For the calling organizer, return each of their events with its payout
    state + a countdown showing how many hours of the hold window remain.

    Used by the organizer dashboard to render the "Hold ends in X days" badge.
    """
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Organizer only")
    items: list[dict] = []
    cursor = db.events.find(
        {"organizer_id": user["user_id"]}, {"_id": 0}
    ).sort("date", -1).limit(200)
    from datetime import datetime, timezone, timedelta
    now = utc_now()
    async for e in cursor:
        try:
            ev_dt = datetime.fromisoformat((e.get("date") or "").replace("Z", "+00:00"))
            if ev_dt.tzinfo is None:
                ev_dt = ev_dt.replace(tzinfo=timezone.utc)
            ends_at = ev_dt + timedelta(hours=PAYOUT_HOLD_HOURS)
            hold_remaining_hours = max(0, int((ends_at - now).total_seconds() // 3600))
        except Exception:
            hold_remaining_hours = None
        items.append({
            "event_id": e["event_id"],
            "title": e.get("title"),
            "date": e.get("date"),
            "currency": e.get("currency", "NZD"),
            "payout_status": e.get("payout_status"),
            "payout_amount": e.get("payout_amount"),
            "payout_gross": e.get("payout_gross"),
            "payout_platform_fee": e.get("payout_platform_fee"),
            "payout_transfer_id": e.get("payout_transfer_id"),
            "payout_error": e.get("payout_error"),
            "payout_processed_at": e.get("payout_processed_at"),
            "hold_remaining_hours": hold_remaining_hours,
        })
    return {
        "items": items,
        "platform_fee_bps": PLATFORM_FEE_BPS,
        "hold_hours": PAYOUT_HOLD_HOURS,
    }


@router.post("/admin/stripe/payouts/{event_id}/run")
async def admin_run_event_payout(event_id: str, user: dict = Depends(get_current_user)):
    """Force an immediate payout attempt for one event (admin override).
    Bypasses the 5-day hold but still respects Stripe idempotency."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    res = await _attempt_event_payout(db, event, triggered_by=f"admin:{user['user_id']}")
    return res


@router.get("/admin/stripe/payouts")
async def admin_list_event_payouts(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    items = []
    async for p in db.connect_payouts.find({}, {"_id": 0}).sort("created_at", -1).limit(500):
        items.append(p)
    return {"items": items, "platform_fee_bps": PLATFORM_FEE_BPS, "hold_hours": PAYOUT_HOLD_HOURS}
