"""Per-event affiliate / referral codes — click tracking + cookie + attribution."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402


def test_affiliate_create_track_attribute():
    org_id = f"aff_org_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_aff_{uuid.uuid4().hex[:8]}"

    async def _run():
        await db.users.insert_one({
            "user_id": org_id, "email": f"{org_id}@example.com",
            "role": "organizer", "name": "Org",
            "created_at": utc_now().isoformat(),
        })
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": org_id, "status": "approved",
            "title": "Affiliated Show", "date": utc_now().isoformat(),
            "currency": "NZD",
        })

        try:
            os.environ.setdefault("JWT_SECRET", "test-secret")
            from httpx import AsyncClient, ASGITransport  # noqa: WPS433
            from server import app  # noqa: WPS433
            import jwt as _jwt  # noqa: WPS433

            tok = _jwt.encode(
                {"sub": org_id, "email": f"{org_id}@example.com", "role": "organizer"},
                os.environ["JWT_SECRET"], algorithm="HS256",
            )
            org_h = {"Authorization": f"Bearer {tok}"}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                # 1) Bad code rejected
                r = await c.post(
                    "/api/organizer/affiliates",
                    json={"code": "??", "partner_name": "X", "commission_pct": 10},
                    headers=org_h,
                )
                assert r.status_code == 400

                # 2) Valid create
                r = await c.post(
                    "/api/organizer/affiliates",
                    json={
                        "code": "promo50",  # lowercased — normalized to PROMO50
                        "partner_name": "Influencer A",
                        "commission_pct": 15,
                        "event_id": event_id,
                    },
                    headers=org_h,
                )
                assert r.status_code == 200, r.text
                affiliate = r.json()
                assert affiliate["code"] == "PROMO50"
                assert affiliate["commission_pct"] == 15.0

                # 3) Duplicate code rejected
                r = await c.post(
                    "/api/organizer/affiliates",
                    json={"code": "PROMO50", "partner_name": "Dup", "commission_pct": 5},
                    headers=org_h,
                )
                assert r.status_code == 409

                # 4) List shows it with zero conversions
                r = await c.get("/api/organizer/affiliates", headers=org_h)
                assert r.status_code == 200
                rows = r.json()
                assert len(rows) >= 1
                row = next(x for x in rows if x["code"] == "PROMO50")
                assert row["conversions"] == 0
                assert row["commission_owed"] == 0.0

                # 5) Click track sets cookie + redirects + increments
                r = await c.get(
                    f"/api/affiliate/track?code=PROMO50&event_id={event_id}",
                    follow_redirects=False,
                )
                assert r.status_code == 302
                assert "aff_code" in r.headers.get("set-cookie", "").lower()
                assert "PROMO50" in r.headers.get("set-cookie", "")
                # Click counter bumped
                aff = await db.affiliates.find_one({"code": "PROMO50"}, {"_id": 0, "clicks": 1})
                assert aff["clicks"] == 1

                # 6) Unknown code still redirects (graceful), no cookie
                r = await c.get(
                    f"/api/affiliate/track?code=NOEXIST&event_id={event_id}",
                    follow_redirects=False,
                )
                assert r.status_code == 302
                assert "aff_code" not in r.headers.get("set-cookie", "").lower()

                # 7) Resolve lookup
                r = await c.get("/api/affiliate/PROMO50")
                assert r.status_code == 200
                assert r.json()["partner_name"] == "Influencer A"

                # 8) Attribution helper: a booking with affiliate cookie present
                #    picks up the attribution.
                from routers.affiliates import attribute_booking
                booking_doc = {"booking_id": "bk_aff_test", "event_id": event_id}
                await attribute_booking(booking_doc, "PROMO50")
                assert booking_doc["affiliate_code"] == "PROMO50"
                assert booking_doc["affiliate_id"] == affiliate["affiliate_id"]
                assert booking_doc["affiliate_commission_pct"] == 15.0

                # 9) Event-scoped affiliate ignores other events
                booking_doc2 = {"booking_id": "bk_aff_test2", "event_id": "evt_other"}
                await attribute_booking(booking_doc2, "PROMO50")
                assert "affiliate_code" not in booking_doc2

                # 10) Edit + deactivate
                r = await c.patch(
                    f"/api/organizer/affiliates/{affiliate['affiliate_id']}",
                    json={"commission_pct": 25, "notes": "Bumped"},
                    headers=org_h,
                )
                assert r.status_code == 200
                aff = await db.affiliates.find_one({"affiliate_id": affiliate["affiliate_id"]}, {"_id": 0})
                assert aff["commission_pct"] == 25
                assert aff["notes"] == "Bumped"

                r = await c.delete(
                    f"/api/organizer/affiliates/{affiliate['affiliate_id']}",
                    headers=org_h,
                )
                assert r.status_code == 200
                aff = await db.affiliates.find_one({"affiliate_id": affiliate["affiliate_id"]}, {"_id": 0})
                assert aff["active"] is False

                # 11) Inactive affiliate isn't resolved
                r = await c.get("/api/affiliate/PROMO50")
                assert r.status_code == 404
        finally:
            await db.users.delete_one({"user_id": org_id})
            await db.events.delete_one({"event_id": event_id})
            await db.affiliates.delete_many({"created_by": org_id})
            await db.affiliate_clicks.delete_many({"code": "PROMO50"})

    asyncio.run(_run())
