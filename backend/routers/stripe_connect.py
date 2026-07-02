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
    # Feb 2026: the pod ships with STRIPE_API_KEY=sk_test_emergent which is a
    # PROXY key handled by Emergent's checkout wrapper. Stripe Connect (Express
    # onboarding + AccountLinks + transfers) hits api.stripe.com DIRECTLY and
    # will 401 on the placeholder key. Fail fast with a helpful message
    # instead of surfacing a cryptic Stripe SDK error to the organizer.
    if STRIPE_API_KEY.strip().lower() in {"sk_test_emergent", "sk_test_placeholder", ""}:
        raise HTTPException(
            status_code=503,
            detail=(
                "Stripe Connect can't run on the shared Emergent test key. "
                "Add your real Stripe test secret (sk_test_51…) to backend/.env "
                "as STRIPE_API_KEY, then restart the backend. Grab yours from "
                "https://dashboard.stripe.com/test/apikeys → 'Reveal test key token'."
            ),
        )
    _stripe_sdk.api_key = STRIPE_API_KEY


def _sget(obj, key, default=None):
    """Safely read a field off a Stripe SDK object.

    Stripe's Python SDK changed how StripeObject exposes fields — in newer
    versions the dict-style `.get()` method raises `AttributeError: get`
    (see the July 2026 bug that caused every onboarding to 502). Attribute
    access via `getattr` works consistently across versions AND is what
    Stripe now documents as the supported path. Falls back to dict-style
    `__getitem__` for the rare case where a nested value is a raw dict.

    A stored `None` is treated as "missing" and returns `default` — this
    mirrors the historical `.get() or fallback` idiom used throughout the
    router and keeps this refactor a no-behaviour-change.
    """
    if obj is None:
        return default
    val = getattr(obj, key, _MISSING)
    if val is _MISSING:
        try:
            val = obj[key]
        except (KeyError, TypeError):
            return default
    return val if val is not None else default


_MISSING = object()


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
    requirements = _sget(acct, "requirements") or {}
    currently_due = _sget(requirements, "currently_due") or []
    update = {
        "stripe_charges_enabled": bool(_sget(acct, "charges_enabled", False)),
        "stripe_payouts_enabled": bool(_sget(acct, "payouts_enabled", False)),
        "stripe_details_submitted": bool(_sget(acct, "details_submitted", False)),
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


def _describe_stripe_error(exc: Exception) -> str:
    """Turn a stripe.error.* into a buyer-friendly multi-line description.

    Stripe SDK exceptions carry the actual API error inside `json_body`.
    Plain `str(exc)` often drops the useful bits, so we extract message +
    code + type + http status manually.
    """
    parts: list[str] = []
    try:
        body = getattr(exc, "json_body", None) or {}
        err = (body.get("error") if isinstance(body, dict) else None) or {}
        msg = err.get("message") or getattr(exc, "user_message", None) or str(exc)
        code = err.get("code") or err.get("type") or ""
        status = getattr(exc, "http_status", None)
        if msg and msg != "get":
            parts.append(msg)
        if code:
            parts.append(f"({code})")
        if status:
            parts.append(f"[HTTP {status}]")
    except Exception:  # noqa: BLE001
        pass
    if not parts:
        # Last resort — use exception class name so the user sees *something*
        # meaningful instead of a one-word fragment.
        parts.append(f"{type(exc).__name__}: {exc}")
    return " ".join(parts).strip()


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
            raise HTTPException(status_code=502, detail=f"Stripe couldn't create the account — {_describe_stripe_error(exc)}") from exc
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
        # Feb 2026: Stripe's newer Python SDK returns a StripeObject that
        # does NOT expose dict `.get()` — attribute access is the supported
        # path. Using `link.get("expires_at")` raised `AttributeError: get`
        # and turned every onboarding into a 502 even though the API call
        # succeeded (HTTP 200 with a valid URL). Read fields via getattr.
        return {
            "url": _sget(link, "url"),
            "expires_at": _sget(link, "expires_at"),
            "stripe_account_id": account_id,
        }

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
                raise HTTPException(status_code=502, detail=f"Stripe rejected the link — {_describe_stripe_error(exc2)}") from exc2
        logger.exception(f"[stripe-connect] AccountLink.create failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Stripe couldn't generate the link — {_describe_stripe_error(exc)}") from exc


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

    # Audit row — used by /admin/stripe/webhook-health to confirm the
    # Stripe dashboard is wired correctly.
    try:
        await db.webhook_deliveries.insert_one({
            "delivery_id": payload.get("id") or f"manual_{utc_now().timestamp()}",
            "source": "stripe_connect",
            "event_type": event_type,
            "account_id": acct_id,
            "signature_verified": bool(secret),
            "received_at": utc_now().isoformat(),
        })
    except Exception:  # noqa: BLE001
        pass

    if event_type == "account.updated" and acct_id:
        refreshed = await _sync_account_from_stripe(acct_id)
        logger.info(f"[stripe-connect] account.updated mirrored for {acct_id} (user={(refreshed or {}).get('user_id')})")
    else:
        # Future events: transfer.created, transfer.failed, payout.paid —
        # log them for now; payouts router (phase 2) will react.
        logger.info(f"[stripe-connect] webhook noop: type={event_type} acct={acct_id}")
    return {"received": True}


@router.get("/admin/stripe/webhook-health")
async def stripe_webhook_health(user: dict = Depends(get_current_user)):
    """Diagnostic: did the user wire up the Stripe Connect webhook correctly?

    Returns:
      - secret_configured: bool   (STRIPE_CONNECT_WEBHOOK_SECRET env var set)
      - webhook_url:       the URL the user needs to paste into Stripe Dashboard
      - recent_deliveries: list of last 20 received deliveries
      - event_type_counts: rollup of received event types over last 30 days
      - last_seen_at:      most recent webhook arrival
      - critical_events_seen: per-event boolean for the required Connect
                              event types so the user knows which ones still
                              need to be enabled in the Stripe dashboard.
      - setup_instructions: step-by-step guide

    Admin-only.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    secret_configured = bool(os.environ.get("STRIPE_CONNECT_WEBHOOK_SECRET"))

    # Build the public webhook URL the user needs to paste into the Stripe
    # dashboard. We pull from platform_settings → public_origin, falling
    # back to the production domain.
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
    webhook_url = f"{origin}/api/webhook/stripe/connect"

    from datetime import timedelta
    since = (utc_now() - timedelta(days=30)).isoformat()

    recent = []
    last_seen_at = None
    async for d in db.webhook_deliveries.find(
        {"source": "stripe_connect"}, {"_id": 0},
    ).sort("received_at", -1).limit(20):
        recent.append(d)
        if last_seen_at is None:
            last_seen_at = d.get("received_at")

    counts: dict[str, int] = {}
    async for r in db.webhook_deliveries.aggregate([
        {"$match": {"source": "stripe_connect", "received_at": {"$gte": since}}},
        {"$group": {"_id": "$event_type", "n": {"$sum": 1}}},
    ]):
        counts[r["_id"] or "(unknown)"] = r["n"]

    # The Stripe docs recommend these for our Connect setup
    required_events = [
        "account.updated",
        "transfer.created",
        "transfer.reversed",
        "payout.paid",
        "payout.failed",
    ]
    critical_events_seen = {ev: ev in counts for ev in required_events}

    setup_instructions = [
        "1. Open Stripe Dashboard → Developers → Webhooks → Add endpoint",
        "2. Set 'Listen to events on Connected accounts' (toggle ON)",
        f"3. Paste this URL: {webhook_url}",
        "4. Select these events:\n" + "\n".join(f"   • {ev}" for ev in required_events),
        "5. Copy the 'Signing secret' (starts with whsec_…)",
        "6. On Railway: add env var STRIPE_CONNECT_WEBHOOK_SECRET=<that value>",
        "7. Redeploy. This panel will turn green within a few minutes.",
    ]

    return {
        "secret_configured": secret_configured,
        "webhook_url": webhook_url,
        "last_seen_at": last_seen_at,
        "recent_deliveries": recent,
        "event_type_counts": counts,
        "critical_events_seen": critical_events_seen,
        "required_events": required_events,
        "setup_instructions": setup_instructions,
    }


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
            "payout_recipients": e.get("payout_recipients") or [],
            "revenue_splits": e.get("revenue_splits") or [],
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


@router.get("/organizer/stripe/transfers")
async def organizer_transfers(user: dict = Depends(get_current_user)):
    """Organizer-facing transfer history — every payout + reversal that
    affected their connected Stripe account. Used by the new "Transfer
    history" page on the organizer dashboard."""
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Organizer only")
    items = []
    async for p in db.connect_payouts.find(
        {"organizer_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(500):
        # Hydrate event title for the row.
        if p.get("event_id"):
            ev = await db.events.find_one({"event_id": p["event_id"]}, {"_id": 0, "title": 1, "date": 1})
            if ev:
                p["event_title"] = ev.get("title")
                p["event_date"] = ev.get("date")
        items.append(p)
    total_paid = sum(p.get("net_amount", 0) for p in items if p.get("status") == "paid")
    total_reversed = sum(abs(p.get("net_amount", 0)) for p in items if p.get("status") == "reversed")
    return {
        "items": items,
        "total_paid": round(total_paid, 2),
        "total_reversed": round(total_reversed, 2),
        "net_settled": round(total_paid - total_reversed, 2),
    }


@router.post("/admin/bookings/{booking_id}/reverse-transfer")
async def admin_reverse_for_refund(booking_id: str, user: dict = Depends(get_current_user)):
    """Admin override — manually trigger a Stripe transfer reversal for a
    refunded booking. Idempotent; safe to call repeatedly."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    from connect_payouts_engine import reverse_transfer_for_refund
    return await reverse_transfer_for_refund(db, booking, triggered_by=f"admin:{user['user_id']}")


@router.get("/organizer/stripe/health")
async def organizer_stripe_health(user: dict = Depends(get_current_user)):
    """Self-service version of the admin health check — the calling
    organizer sees exactly what Stripe still needs from them.

    Same response shape as `/admin/users/{id}/stripe-health` so the two
    surfaces can share frontend logic.
    """
    if user.get("role") not in {"organizer", "admin"}:
        raise HTTPException(status_code=403, detail="Organizer only")
    acct_id = user.get("stripe_account_id")
    if not acct_id:
        return {
            "ok": False,
            "reason": "You haven't started Stripe onboarding yet.",
            "stripe_account_id": None,
        }
    _ensure_stripe()
    try:
        acct = await asyncio.to_thread(_stripe_sdk.Account.retrieve, acct_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[stripe-connect] self-health failed for {acct_id}: {exc}")
        return {
            "ok": False,
            "reason": _describe_stripe_error(exc),
            "stripe_account_id": acct_id,
        }
    requirements = _sget(acct, "requirements") or {}
    payload = {
        "ok": True,
        "stripe_account_id": acct_id,
        "country": _sget(acct, "country"),
        "charges_enabled": bool(_sget(acct, "charges_enabled", False)),
        "payouts_enabled": bool(_sget(acct, "payouts_enabled", False)),
        "details_submitted": bool(_sget(acct, "details_submitted", False)),
        "currently_due": list(_sget(requirements, "currently_due") or []),
        "past_due": list(_sget(requirements, "past_due") or []),
        "eventually_due": list(_sget(requirements, "eventually_due") or []),
        "disabled_reason": _sget(requirements, "disabled_reason"),
        "checked_at": utc_now().isoformat(),
    }
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "stripe_charges_enabled": payload["charges_enabled"],
            "stripe_payouts_enabled": payload["payouts_enabled"],
            "stripe_details_submitted": payload["details_submitted"],
            "stripe_requirements_due": payload["currently_due"],
            "stripe_last_synced_at": payload["checked_at"],
        }},
    )
    return payload


@router.get("/admin/users/{user_id}/stripe-health")
async def admin_stripe_health_check(user_id: str, user: dict = Depends(get_current_user)):
    """Live Stripe Connect diagnostics for one organizer.

    Calls `stripe.Account.retrieve` on the organizer's connected account and
    returns the current capability + requirements state, plus a flat list of
    what they still need to provide. Mirrors the fields into our user record
    so the Admin → Users table reflects the latest state.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    acct_id = target.get("stripe_account_id")
    if not acct_id:
        return {
            "ok": False,
            "reason": "Organizer hasn't started Stripe onboarding yet — no account to check.",
            "stripe_account_id": None,
        }
    _ensure_stripe()
    try:
        acct = await asyncio.to_thread(_stripe_sdk.Account.retrieve, acct_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[stripe-connect] health check failed for {acct_id}: {exc}")
        return {
            "ok": False,
            "reason": _describe_stripe_error(exc),
            "stripe_account_id": acct_id,
        }
    requirements = _sget(acct, "requirements") or {}
    cap = _sget(acct, "capabilities") or {}
    payload = {
        "ok": True,
        "stripe_account_id": acct_id,
        "country": _sget(acct, "country"),
        "email": _sget(acct, "email"),
        "charges_enabled": bool(_sget(acct, "charges_enabled", False)),
        "payouts_enabled": bool(_sget(acct, "payouts_enabled", False)),
        "details_submitted": bool(_sget(acct, "details_submitted", False)),
        "currently_due": list(_sget(requirements, "currently_due") or []),
        "past_due": list(_sget(requirements, "past_due") or []),
        "eventually_due": list(_sget(requirements, "eventually_due") or []),
        "disabled_reason": _sget(requirements, "disabled_reason"),
        "capabilities": {k: _sget(cap, k) for k in ("card_payments", "transfers") if _sget(cap, k) is not None},
        "checked_at": utc_now().isoformat(),
    }
    # Mirror so the Users table pill stays fresh.
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "stripe_charges_enabled": payload["charges_enabled"],
            "stripe_payouts_enabled": payload["payouts_enabled"],
            "stripe_details_submitted": payload["details_submitted"],
            "stripe_requirements_due": payload["currently_due"],
            "stripe_last_synced_at": payload["checked_at"],
        }},
    )
    return payload
