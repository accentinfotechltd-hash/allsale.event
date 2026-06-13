"""Webhook silent-failure scheduler check + affiliate banner endpoint."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from scheduler import _check_webhook_silent_failure  # noqa: E402


def test_webhook_silent_failure_alert():
    """Scenarios:
      1. Secret NOT set → no alert (the admin panel already covers this).
      2. Secret set, but never received any webhook ever → no alert (grace).
      3. Secret set, last delivery > 48h ago → alert fires.
      4. Secret set, last delivery within 48h → no alert.
      5. Already-sent dedupe — second call within 22h is silent.
    """
    async def _run():
        # Clean slate
        await db.platform_settings.delete_one({"key": "webhook_health"})

        # Always force "9am UTC" so the time-gate inside the function passes.
        fake_now = datetime.now(timezone.utc).replace(hour=9, minute=15)

        with patch("scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            # Preserve the class methods we still need
            mock_dt.fromisoformat = datetime.fromisoformat

            # --- 1) No secret → no alert
            with patch.dict(os.environ, {}, clear=False):
                if "STRIPE_CONNECT_WEBHOOK_SECRET" in os.environ:
                    del os.environ["STRIPE_CONNECT_WEBHOOK_SECRET"]
                got = await _check_webhook_silent_failure(db)
                assert got is False, "should not alert when secret missing"

            # --- 2) Secret set, no deliveries ever → grace period
            with patch.dict(os.environ, {"STRIPE_CONNECT_WEBHOOK_SECRET": "whsec_test"}):
                await db.webhook_deliveries.delete_many({"source": "stripe_connect"})
                got = await _check_webhook_silent_failure(db)
                assert got is False, "should not alert on a fresh deployment"

                # --- 3) Old delivery (> 48h ago) → alert
                old_iso = (fake_now - timedelta(hours=72)).isoformat()
                await db.webhook_deliveries.insert_one({
                    "delivery_id": f"test_{uuid.uuid4().hex}",
                    "source": "stripe_connect",
                    "event_type": "account.updated",
                    "received_at": old_iso,
                })
                got = await _check_webhook_silent_failure(db)
                assert got is True, "should alert when last delivery > 48h ago"

                # --- 5) Dedupe — second call inside 22h is silent
                got = await _check_webhook_silent_failure(db)
                assert got is False, "should dedupe within 22h"

                # --- 4) Add a fresh delivery → no alert
                await db.platform_settings.delete_one({"key": "webhook_health"})
                fresh_iso = (fake_now - timedelta(hours=2)).isoformat()
                await db.webhook_deliveries.insert_one({
                    "delivery_id": f"test_{uuid.uuid4().hex}",
                    "source": "stripe_connect",
                    "event_type": "account.updated",
                    "received_at": fresh_iso,
                })
                got = await _check_webhook_silent_failure(db)
                assert got is False, "should not alert when recent delivery exists"

        # Cleanup
        await db.webhook_deliveries.delete_many({"event_type": "account.updated", "delivery_id": {"$regex": "^test_"}})
        await db.platform_settings.delete_one({"key": "webhook_health"})

    asyncio.run(_run())


def test_affiliate_resolve_endpoint_used_by_banner():
    """The AffiliateBanner calls GET /api/affiliate/{code}. Validate it
    returns partner_name + commission_pct so the banner can render."""
    org_id = f"bn_org_{uuid.uuid4().hex[:8]}"

    async def _run():
        await db.users.insert_one({
            "user_id": org_id, "email": f"{org_id}@example.com",
            "role": "organizer", "name": "Org",
            "created_at": utc_now().isoformat(),
        })

        try:
            from httpx import AsyncClient, ASGITransport  # noqa: WPS433
            from server import app  # noqa: WPS433
            os.environ.setdefault("JWT_SECRET", "test-secret")
            import jwt as _jwt  # noqa: WPS433

            token = _jwt.encode(
                {"sub": org_id, "email": f"{org_id}@example.com", "role": "organizer"},
                os.environ["JWT_SECRET"], algorithm="HS256",
            )
            headers = {"Authorization": f"Bearer {token}"}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                # Create affiliate
                r = await c.post(
                    "/api/organizer/affiliates",
                    json={"code": "BANNER", "partner_name": "Banner Test Partner",
                          "commission_pct": 12},
                    headers=headers,
                )
                assert r.status_code == 200

                # Public resolve (no auth) — what the banner calls
                r = await c.get("/api/affiliate/BANNER")
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["partner_name"] == "Banner Test Partner"
                assert body["commission_pct"] == 12

                # Unknown code → 404 so banner stays hidden
                r = await c.get("/api/affiliate/DOESNOTEXIST")
                assert r.status_code == 404
        finally:
            await db.users.delete_one({"user_id": org_id})
            await db.affiliates.delete_many({"created_by": org_id})

    asyncio.run(_run())
