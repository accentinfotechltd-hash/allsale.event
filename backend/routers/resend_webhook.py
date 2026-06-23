"""Resend webhook receiver — captures email open / click / bounce events.

Configure your Resend project to POST events to:
  https://<your-host>/api/webhooks/resend

Each event lands in the `email_events` collection so admin dashboards can
compute open- and click-rates per recruitment-flyer campaign by joining
`flyer_campaigns.resend_ids` → `email_events.resend_id`.

We intentionally accept ANY payload shape (Resend has changed it twice in
the last 12 months). The two fields we actually need are `type` and either
`data.id` or `data.email_id`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Request

from core import db

logger = logging.getLogger("aura.webhooks.resend")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/resend")
async def resend_webhook(request: Request) -> Dict[str, Any]:
    """Receives webhook events from Resend. Always returns 200 even on
    malformed payloads — Resend will mark the delivery failed and retry
    otherwise, flooding our logs.
    """
    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("[resend-webhook] non-JSON body: %s", exc)
        return {"ok": True, "reason": "non_json"}

    event_type = (payload or {}).get("type") or "unknown"
    data = (payload or {}).get("data") or {}
    # Resend's payload uses `email_id` in some events and `id` in others.
    resend_id = data.get("email_id") or data.get("id")
    recipient = None
    to_field = data.get("to")
    if isinstance(to_field, list) and to_field:
        recipient = to_field[0]
    elif isinstance(to_field, str):
        recipient = to_field

    record = {
        "resend_id": resend_id,
        "event_type": event_type,
        "recipient": recipient,
        "subject": data.get("subject"),
        "click_url": (data.get("click") or {}).get("link") if isinstance(data.get("click"), dict) else None,
        "user_agent": (data.get("click") or {}).get("user_agent") if isinstance(data.get("click"), dict) else None,
        "received_at": _utc_now_iso(),
        "raw": payload,
    }
    try:
        await db.email_events.insert_one(record)
    except Exception as exc:  # pragma: no cover
        logger.exception("[resend-webhook] failed to store event: %s", exc)
        # Still 200 so Resend doesn't retry storms.
    return {"ok": True}
