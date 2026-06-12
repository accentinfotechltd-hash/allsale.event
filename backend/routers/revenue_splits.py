"""Multi-organizer revenue splits — organizer-side config.

Lets an event owner share ticket revenue with one or more co-organizers
(e.g. promoter 70 / venue 30). Each co-organizer must have their own
verified Stripe Connect account; the payout engine
(`connect_payouts_engine._attempt_event_payout`) issues a separate
`stripe.Transfer` per recipient at event-end + 5d hold.

Endpoints:
  GET    /api/organizer/events/{event_id}/revenue-splits
  PUT    /api/organizer/events/{event_id}/revenue-splits
  DELETE /api/organizer/events/{event_id}/revenue-splits
  GET    /api/organizer/users/lookup?email=foo@bar.com  (find recipient)

The schema stored on the event:
  revenue_splits: [{user_id, label, percent}]
                where percentages must sum to 100 (±0.5 to tolerate UI rounding).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now

router = APIRouter(tags=["revenue-splits"])


class SplitIn(BaseModel):
    user_id: str  # platform user_id of the co-organizer
    label: Optional[str] = None  # e.g. "Venue", "Promoter"
    percent: float = Field(ge=0.0, le=100.0)


class SplitsIn(BaseModel):
    splits: List[SplitIn]


async def _assert_event_owner(event_id: str, user: dict) -> dict:
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    is_owner = event.get("organizer_id") == user["user_id"]
    is_admin = user.get("role") == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Only the event owner or an admin can configure splits")
    return event


async def _hydrate_splits(splits: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in splits or []:
        uid = s.get("user_id")
        u = await db.users.find_one({"user_id": uid}, {"_id": 0}) if uid else None
        out.append({
            "user_id": uid,
            "label": s.get("label") or (u.get("name") if u else "recipient"),
            "percent": float(s.get("percent") or 0),
            "name": (u or {}).get("name"),
            "email": (u or {}).get("email"),
            "stripe_account_id": (u or {}).get("stripe_account_id"),
            "stripe_payouts_enabled": bool((u or {}).get("stripe_payouts_enabled")),
            "stripe_charges_enabled": bool((u or {}).get("stripe_charges_enabled")),
        })
    return out


@router.get("/organizer/events/{event_id}/revenue-splits")
async def get_splits(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await _assert_event_owner(event_id, user)
    raw = event.get("revenue_splits") or []
    hydrated = await _hydrate_splits(raw)
    total_pct = round(sum(s["percent"] for s in hydrated), 2)
    return {
        "event_id": event_id,
        "splits": hydrated,
        "total_percent": total_pct,
        "configured": bool(raw),
    }


@router.put("/organizer/events/{event_id}/revenue-splits")
async def put_splits(event_id: str, payload: SplitsIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await _assert_event_owner(event_id, user)

    splits = payload.splits or []
    if not splits:
        raise HTTPException(status_code=400, detail="At least one recipient required (or DELETE to clear).")

    # Dedupe by user_id (last write wins for label/percent)
    seen: dict[str, dict] = {}
    for s in splits:
        if not s.user_id:
            raise HTTPException(status_code=400, detail="Each split needs a user_id")
        seen[s.user_id] = s.model_dump()
    deduped = list(seen.values())

    # Validate sum
    total = round(sum(float(s.get("percent") or 0) for s in deduped), 2)
    if abs(total - 100.0) > 0.5:
        raise HTTPException(
            status_code=400,
            detail=f"Splits must sum to 100% (got {total:.2f}%).",
        )

    # Validate every recipient is a real user. Co-organizers without Connect
    # are allowed for setup, but the payout engine will skip them with a
    # warning until they verify — surface this back in the response.
    warnings: list[str] = []
    for s in deduped:
        u = await db.users.find_one({"user_id": s["user_id"]}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=400, detail=f"User {s['user_id']} not found")
        if u.get("role") not in {"organizer", "admin"}:
            raise HTTPException(
                status_code=400,
                detail=f"{u.get('email')} is not an organizer. They must upgrade their account first.",
            )
        if not u.get("stripe_payouts_enabled"):
            warnings.append(
                f"{u.get('name') or u.get('email')} hasn't finished Stripe Connect — their share won't pay out until they do."
            )

    # Ensure event owner is in the splits, or add an implicit row (defensive).
    # The UI builds this for us; we just persist it as-is.

    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {
            "revenue_splits": deduped,
            "revenue_splits_updated_at": utc_now().isoformat(),
            "revenue_splits_updated_by": user["user_id"],
        }},
    )

    hydrated = await _hydrate_splits(deduped)
    return {
        "ok": True,
        "event_id": event_id,
        "splits": hydrated,
        "total_percent": total,
        "warnings": warnings,
    }


@router.delete("/organizer/events/{event_id}/revenue-splits")
async def clear_splits(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    await _assert_event_owner(event_id, user)
    await db.events.update_one(
        {"event_id": event_id},
        {"$unset": {
            "revenue_splits": "",
            "revenue_splits_updated_at": "",
            "revenue_splits_updated_by": "",
        }},
    )
    return {"ok": True, "event_id": event_id, "cleared": True}


@router.get("/organizer/users/lookup")
async def lookup_user(email: str, user: dict = Depends(get_current_user)):
    """Used by the splits UI to add a co-organizer by email. Returns the
    minimal info needed to render an "invite" card with Stripe Connect status.

    Only organizers/admins can lookup. Returns 404 if no match.
    """
    await require_role(user, "organizer", "admin")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email required")
    import re as _re
    target = await db.users.find_one(
        # Case-insensitive exact match — users often sign up with mixed-case
        # emails, but the splits UI takes whatever they type.
        {"email": {"$regex": f"^{_re.escape(email.strip())}$", "$options": "i"}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1,
         "stripe_account_id": 1, "stripe_payouts_enabled": 1,
         "stripe_charges_enabled": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="No user with that email — ask them to sign up first.")
    return {
        "user_id": target["user_id"],
        "name": target.get("name"),
        "email": target.get("email"),
        "role": target.get("role"),
        "stripe_account_id": target.get("stripe_account_id"),
        "stripe_payouts_enabled": bool(target.get("stripe_payouts_enabled")),
        "stripe_charges_enabled": bool(target.get("stripe_charges_enabled")),
    }
