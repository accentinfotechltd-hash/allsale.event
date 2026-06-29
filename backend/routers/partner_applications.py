"""Public partner application intake + admin review.

Anyone can submit `POST /partners/apply` (no auth) — captures contact + reach
info into `partner_applications`. Admin reviews via `GET /admin/partners/applications`
and approves → fires the existing marketing-partner creation flow.

Design notes:
- Public endpoint is rate-limited by IP via a simple in-process bucket so a
  single bot can't flood the inbox. Per-IP cap: 5 submissions / 10 minutes.
- Each application stores `ip`, `user_agent`, and `referrer` for audit only.
- Approval is a manual admin decision — we do NOT auto-create a real
  marketing partner record. Admin reviews then clicks "Approve" which
  surfaces a follow-up modal to set the commission %.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from core import db, get_current_user, utc_now
from emails import send_template_fireforget

logger = logging.getLogger("aura.partner_applications")
router = APIRouter(tags=["partner-applications"])


# ---------- Rate-limit bucket (per-IP) -------------------------------------
_RATE_WINDOW_SEC = 600  # 10 minutes
_RATE_MAX_REQUESTS = 5
_rate_buckets: "defaultdict[str, deque[float]]" = defaultdict(deque)


def _rate_limit_ok(ip: str) -> bool:
    """Sliding-window: drop timestamps older than window, then check count."""
    now = time.time()
    bucket = _rate_buckets[ip]
    while bucket and now - bucket[0] > _RATE_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= _RATE_MAX_REQUESTS:
        return False
    bucket.append(now)
    return True


# ---------- Models ---------------------------------------------------------
class PartnerApplicationIn(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    company: Optional[str] = Field(default=None, max_length=120)
    channels: list[str] = Field(default_factory=list)  # ['instagram', 'tiktok', ...]
    audience_size: Optional[str] = Field(default=None, max_length=80)
    why_partner: str = Field(..., min_length=10, max_length=1500)


class _AdminDecision(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


def _admin_only(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


def _scrub_input(s: Optional[str]) -> Optional[str]:
    """Strip control chars + over-long whitespace runs."""
    if s is None:
        return None
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


# ---------- Public submit --------------------------------------------------
@router.post("/partners/apply")
async def submit_partner_application(payload: PartnerApplicationIn, request: Request) -> dict:
    """Public endpoint: prospective partner sends a single application.
    Returns `{ok: true, application_id}` so the frontend can show a success
    state with a reference number for follow-up emails.
    """
    ip = (request.client.host if request.client else None) or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or "unknown"
    if not _rate_limit_ok(ip):
        raise HTTPException(status_code=429, detail="Too many submissions — please try again in 10 minutes.")

    # Idempotency: if the same email already has a `pending` application,
    # update its `last_resubmitted_at` instead of creating a duplicate row.
    email_norm = payload.email.lower().strip()
    existing = await db.partner_applications.find_one({"email": email_norm, "status": "pending"})

    app_doc = {
        "application_id": existing["application_id"] if existing else f"app_{uuid.uuid4().hex[:14]}",
        "full_name": _scrub_input(payload.full_name) or "",
        "email": email_norm,
        "phone": _scrub_input(payload.phone),
        "company": _scrub_input(payload.company),
        "channels": [c for c in (payload.channels or []) if isinstance(c, str) and c.strip()][:12],
        "audience_size": _scrub_input(payload.audience_size),
        "why_partner": _scrub_input(payload.why_partner) or "",
        "status": "pending",
        "ip": ip[:64],
        "user_agent": (request.headers.get("user-agent") or "")[:300],
        "referrer": (request.headers.get("referer") or "")[:300],
    }
    if existing:
        app_doc["last_resubmitted_at"] = utc_now().isoformat()
        await db.partner_applications.update_one(
            {"application_id": existing["application_id"]},
            {"$set": app_doc},
        )
    else:
        app_doc["created_at"] = utc_now().isoformat()
        await db.partner_applications.insert_one(app_doc)

    # Fire-and-forget: notify admin + acknowledge applicant. Wrapped in try
    # so a Resend hiccup doesn't fail the form submission.
    try:
        admin_users = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1}).to_list(length=20)
        for au in admin_users:
            if au.get("email"):
                send_template_fireforget(
                    "partner_application_admin_notify",
                    au["email"],
                    {
                        "applicant_name": app_doc["full_name"],
                        "applicant_email": app_doc["email"],
                        "applicant_company": app_doc.get("company") or "(none)",
                        "channels": ", ".join(app_doc.get("channels") or []) or "(not specified)",
                        "audience_size": app_doc.get("audience_size") or "(not specified)",
                        "why_partner": app_doc.get("why_partner") or "",
                        "application_id": app_doc["application_id"],
                    },
                    db,
                )
        send_template_fireforget(
            "partner_application_received",
            app_doc["email"],
            {
                "applicant_name": app_doc["full_name"],
                "application_id": app_doc["application_id"],
            },
            db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partner-apply] email dispatch failed: %s", str(exc)[:200])

    return {"ok": True, "application_id": app_doc["application_id"]}


# ---------- Admin review ---------------------------------------------------
@router.get("/admin/partners/applications")
async def list_partner_applications(
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
) -> dict:
    """List partner applications. Default: most recent first."""
    _admin_only(user)
    q: dict = {}
    if status in ("pending", "approved", "rejected"):
        q["status"] = status
    cur = db.partner_applications.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    items = [doc async for doc in cur]

    # Summary counts (one tiny aggregation)
    counts: dict = {"pending": 0, "approved": 0, "rejected": 0}
    async for row in db.partner_applications.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]):
        if row["_id"] in counts:
            counts[row["_id"]] = int(row["n"])
    return {"items": items, "summary": counts}


@router.post("/admin/partners/applications/{application_id}/approve")
async def approve_partner_application(
    application_id: str,
    payload: _AdminDecision,
    user: dict = Depends(get_current_user),
) -> dict:
    """Mark approved + email applicant. Does NOT auto-create the marketing
    partner record — that's a separate admin flow with commission %; this
    just unblocks them to schedule a call / send a contract.
    """
    _admin_only(user)
    app_doc = await db.partner_applications.find_one({"application_id": application_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc.get("status") == "approved":
        return {"ok": True, "already_approved": True}

    await db.partner_applications.update_one(
        {"application_id": application_id},
        {"$set": {
            "status": "approved",
            "reviewer_id": user.get("user_id"),
            "reviewed_at": utc_now().isoformat(),
            "decision_note": _scrub_input(payload.note),
        }},
    )

    try:
        send_template_fireforget(
            "partner_application_approved",
            app_doc["email"],
            {
                "applicant_name": app_doc.get("full_name") or "there",
                "note": _scrub_input(payload.note) or "",
            },
            db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[partner-apply] approval email failed: %s", str(exc)[:200])

    return {"ok": True}


@router.post("/admin/partners/applications/{application_id}/reject")
async def reject_partner_application(
    application_id: str,
    payload: _AdminDecision,
    user: dict = Depends(get_current_user),
) -> dict:
    """Mark rejected. Optional `note` is shown to admin in the table; we do
    NOT email a rejection — admin chases manually if they want to."""
    _admin_only(user)
    app_doc = await db.partner_applications.find_one({"application_id": application_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    await db.partner_applications.update_one(
        {"application_id": application_id},
        {"$set": {
            "status": "rejected",
            "reviewer_id": user.get("user_id"),
            "reviewed_at": utc_now().isoformat(),
            "decision_note": _scrub_input(payload.note),
        }},
    )
    return {"ok": True}
