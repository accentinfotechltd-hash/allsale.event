"""Self-serve refund-window policy.

Lets organizers publish a public refund policy on each event (e.g. "full
refund up to 48h before the show"). Attendees can self-cancel and receive
an automated Stripe refund when their booking falls inside the window.

Endpoints:
  GET  /api/events/{event_id}/refund-policy
       Public read of the event's policy (used by event detail + checkout).
  GET  /api/me/bookings/{booking_id}/refund-eligibility
       Per-booking dry-run: am I inside the window? what amount would I get?
  POST /api/me/bookings/{booking_id}/refund-request
       Performs the refund. Idempotent via the booking's status — once a
       booking is `refunded`, further calls return the existing record.

Policy schema (stored on the event):
  {
    "enabled": bool,
    "hours_before_event": int,     # window
    "refund_pct": int,             # 0-100, % of face_value
    "include_fees": bool,          # if true, service fees are also refunded
  }
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["refunds"])

try:
    import stripe as _stripe  # type: ignore
    _STRIPE = True
except Exception:  # noqa: BLE001
    _stripe = None  # type: ignore
    _STRIPE = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_event_dt(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _normalize_policy(p: Optional[dict]) -> dict:
    """Coerce a stored / submitted policy into the canonical shape."""
    if not p or not isinstance(p, dict):
        return {"enabled": False}
    enabled = bool(p.get("enabled"))
    hours = max(0, min(8760, int(p.get("hours_before_event") or 0)))  # cap at 1 year
    pct = max(0, min(100, int(p.get("refund_pct") if p.get("refund_pct") is not None else 100)))
    include_fees = bool(p.get("include_fees"))
    return {
        "enabled": enabled,
        "hours_before_event": hours,
        "refund_pct": pct,
        "include_fees": include_fees,
    }


def _compute_refund_amount(booking: dict, policy: dict) -> dict:
    """Given a paid booking + policy, compute the refundable amount."""
    pct = policy.get("refund_pct", 100) / 100.0
    face_value = float(booking.get("face_value") or 0)
    service_fee = float(booking.get("service_fee") or 0)
    total_paid = float(booking.get("amount") or (face_value + service_fee))

    # Refund of face value (always).
    refundable_face = round(face_value * pct, 2)
    # Optionally refund service fees too.
    refundable_fees = round(service_fee * pct, 2) if policy.get("include_fees") else 0.0
    total_refund = round(min(refundable_face + refundable_fees, total_paid), 2)

    return {
        "face_value": face_value,
        "service_fee": service_fee,
        "total_paid": total_paid,
        "refundable_face": refundable_face,
        "refundable_fees": refundable_fees,
        "total_refund": total_refund,
    }


# ---------------------------------------------------------------------------
# public read
# ---------------------------------------------------------------------------

@router.get("/events/{event_id}/refund-policy")
async def get_event_refund_policy(event_id: str):
    ev = await db.events.find_one({"event_id": event_id}, {"_id": 0, "refund_policy": 1, "date": 1})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    policy = _normalize_policy(ev.get("refund_policy"))
    return {"event_id": event_id, "policy": policy}


# ---------------------------------------------------------------------------
# eligibility check
# ---------------------------------------------------------------------------

@router.get("/me/bookings/{booking_id}/refund-eligibility")
async def refund_eligibility(booking_id: str, user: dict = Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your booking")

    event = await db.events.find_one({"event_id": booking.get("event_id")}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    policy = _normalize_policy(event.get("refund_policy"))

    # Hard preconditions.
    if booking.get("status") == "refunded":
        return {
            "eligible": False,
            "reason": "This booking has already been refunded.",
            "policy": policy,
            "already_refunded": True,
            "refund_at": booking.get("refunded_at"),
        }
    if booking.get("status") != "paid":
        return {"eligible": False, "reason": "Only paid bookings are refundable.", "policy": policy}
    if not policy.get("enabled"):
        return {"eligible": False, "reason": "Organizer hasn't enabled self-serve refunds.", "policy": policy}

    ev_dt = _parse_event_dt(event.get("date"))
    if not ev_dt:
        return {"eligible": False, "reason": "Event date unknown.", "policy": policy}

    hours_remaining = (ev_dt - utc_now()).total_seconds() / 3600.0
    if hours_remaining <= 0:
        return {"eligible": False, "reason": "Event has started — refund window closed.", "policy": policy, "hours_remaining": 0}
    if hours_remaining < policy.get("hours_before_event", 0):
        return {
            "eligible": False,
            "reason": f"Cut-off is {policy['hours_before_event']}h before event — currently {round(hours_remaining,1)}h to go.",
            "policy": policy,
            "hours_remaining": round(hours_remaining, 1),
        }

    amounts = _compute_refund_amount(booking, policy)
    return {
        "eligible": True,
        "policy": policy,
        "hours_remaining": round(hours_remaining, 1),
        "amounts": amounts,
        "currency": booking.get("currency", event.get("currency", "NZD")),
    }


# ---------------------------------------------------------------------------
# request the refund
# ---------------------------------------------------------------------------

class RefundReason(BaseModel):
    reason: Optional[str] = None


@router.post("/me/bookings/{booking_id}/refund-request")
async def refund_request(booking_id: str, payload: RefundReason | None = None, user: dict = Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your booking")

    # Idempotent: re-running for an already-refunded booking returns its record.
    if booking.get("status") == "refunded":
        return {
            "ok": True,
            "already_refunded": True,
            "stripe_refund_id": booking.get("stripe_refund_id"),
            "refunded_at": booking.get("refunded_at"),
            "amount_refunded": booking.get("amount_refunded"),
        }
    if booking.get("status") != "paid":
        raise HTTPException(status_code=400, detail="Only paid bookings can be refunded.")

    event = await db.events.find_one({"event_id": booking.get("event_id")}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    policy = _normalize_policy(event.get("refund_policy"))
    if not policy.get("enabled"):
        raise HTTPException(status_code=400, detail="This event doesn't allow self-serve refunds.")

    ev_dt = _parse_event_dt(event.get("date"))
    if not ev_dt:
        raise HTTPException(status_code=400, detail="Event date unknown — contact support.")
    hours_remaining = (ev_dt - utc_now()).total_seconds() / 3600.0
    if hours_remaining < policy.get("hours_before_event", 0):
        raise HTTPException(
            status_code=400,
            detail=f"Refund window closed (cut-off is {policy['hours_before_event']}h before event).",
        )

    amounts = _compute_refund_amount(booking, policy)
    if amounts["total_refund"] <= 0:
        # Policy says 0% — short-circuit, just cancel the booking without Stripe.
        await db.bookings.update_one(
            {"booking_id": booking_id},
            {"$set": {
                "status": "refunded",
                "amount_refunded": 0,
                "refund_reason": (payload.reason if payload else None),
                "refunded_at": utc_now().isoformat(),
                "refunded_by": user["user_id"],
                "self_serve": True,
            }},
        )
        await _release_seats(booking)
        return {"ok": True, "amount_refunded": 0, "stripe_refund_id": None, "policy": policy}

    # Hit Stripe. We refund the payment_intent directly (not via Checkout
    # Session) so we work for both PaymentIntent and Checkout flows.
    pi = booking.get("stripe_payment_intent") or booking.get("payment_intent_id")
    if not pi and not booking.get("stripe_session_id"):
        raise HTTPException(status_code=400, detail="No Stripe charge found on this booking.")

    if _STRIPE and os.environ.get("STRIPE_API_KEY"):
        _stripe.api_key = os.environ["STRIPE_API_KEY"]
        try:
            kwargs = {
                "amount": int(round(amounts["total_refund"] * 100)),
                "metadata": {
                    "booking_id": booking_id,
                    "event_id": event["event_id"],
                    "user_id": user["user_id"],
                    "policy_pct": str(policy.get("refund_pct")),
                    "self_serve": "true",
                },
                "reason": "requested_by_customer",
            }
            if pi:
                kwargs["payment_intent"] = pi
            else:
                # Need to look up the charge from the checkout session.
                sess = await _stripe.checkout.Session.retrieve_async(booking["stripe_session_id"]) if hasattr(_stripe.checkout.Session, "retrieve_async") else _stripe.checkout.Session.retrieve(booking["stripe_session_id"])
                if sess.payment_intent:
                    kwargs["payment_intent"] = sess.payment_intent
                else:
                    raise HTTPException(status_code=400, detail="Stripe charge not yet settled — try again in a few minutes.")
            refund = _stripe.Refund.create(**kwargs, idempotency_key=f"refund-{booking_id}")
            refund_id = refund.get("id") if isinstance(refund, dict) else getattr(refund, "id", None)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[refund] stripe refund failed for {booking_id}: {exc}")
            raise HTTPException(status_code=500, detail=f"Stripe refund failed: {str(exc)[:200]}")
    else:
        # No Stripe configured (test env) — still mark refunded.
        refund_id = None

    now_iso = utc_now().isoformat()
    await db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "status": "refunded",
            "amount_refunded": amounts["total_refund"],
            "stripe_refund_id": refund_id,
            "refund_reason": (payload.reason if payload else None),
            "refunded_at": now_iso,
            "refunded_by": user["user_id"],
            "self_serve": True,
        }},
    )

    # Release the seats/tier capacity so they go back on sale.
    await _release_seats(booking)

    # If the event has already been paid out, reverse the Connect transfer
    # so the platform recovers the portion it just refunded to the buyer.
    try:
        from connect_payouts_engine import reverse_transfer_for_refund
        await reverse_transfer_for_refund(db, booking, triggered_by=f"self-serve:{user['user_id']}")
    except Exception as exc:  # noqa: BLE001 — never fail the refund on this
        logger.warning(f"[refund] connect reversal failed (non-fatal) for {booking_id}: {exc}")

    return {
        "ok": True,
        "amount_refunded": amounts["total_refund"],
        "stripe_refund_id": refund_id,
        "policy": policy,
        "amounts": amounts,
    }


async def _release_seats(booking: dict) -> None:
    """Mark this booking's seats as available again on the event."""
    event_id = booking.get("event_id")
    if not event_id:
        return
    seats = booking.get("seats") or []
    if seats:
        await db.events.update_one(
            {"event_id": event_id},
            {"$pull": {"booked_seats": {"$in": seats}}},
        )
    # Tiered: bookings should be deducted from sold counts. Some events track
    # this via aggregate; just nudging the booking status is enough for the
    # availability count to reflect.
