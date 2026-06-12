"""Regression test for admin events submission-trend endpoint."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402


def test_submission_trend_endpoint():
    admin_id = f"adm_st_{uuid.uuid4().hex[:8]}"
    orig_id = f"org_st_{uuid.uuid4().hex[:8]}"

    def _ev(*, created_hours_ago: int, status: str = "pending"):
        return {
            "event_id": f"evt_st_{uuid.uuid4().hex[:10]}",
            "organizer_id": orig_id,
            "title": "Trend Test",
            "status": status,
            "date": utc_now().isoformat(),
            "created_at": (utc_now() - timedelta(hours=created_hours_ago)).isoformat(),
        }

    now_event = _ev(created_hours_ago=2)  # last 24h
    earlier_event = _ev(created_hours_ago=10)  # last 24h
    yesterday_event = _ev(created_hours_ago=30)  # prev 24h (24-48h)
    old_event = _ev(created_hours_ago=24 * 10)  # 10 days ago (within 14d window)
    way_old = _ev(created_hours_ago=24 * 30)  # 30d ago (outside default window)

    async def _run():
        await db.users.insert_many([
            {"user_id": admin_id, "email": f"{admin_id}@example.com",
             "role": "admin", "name": "Admin", "created_at": utc_now().isoformat()},
            {"user_id": orig_id, "email": f"{orig_id}@example.com",
             "role": "organizer", "name": "Org", "created_at": utc_now().isoformat()},
        ])
        await db.events.insert_many([now_event, earlier_event, yesterday_event, old_event, way_old])

        try:
            os.environ.setdefault("JWT_SECRET", "test-secret")
            from httpx import AsyncClient, ASGITransport  # noqa: WPS433
            from server import app  # noqa: WPS433
            import jwt as _jwt  # noqa: WPS433

            token = _jwt.encode(
                {"sub": admin_id, "email": f"{admin_id}@example.com", "role": "admin"},
                os.environ["JWT_SECRET"],
                algorithm="HS256",
            )
            headers = {"Authorization": f"Bearer {token}"}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Default 14-day window
                r = await client.get("/api/admin/events/submission-trend", headers=headers)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["days"] == 14
                assert body["submitted_24h"] == 2  # two events in last 24h
                assert body["submitted_prev_24h"] == 1  # one in 24-48h
                # delta = (2-1)/1 * 100 = +100%
                assert body["delta_pct"] == 100.0
                # Total in 14-day window = 4 (all but the 30-day-old)
                # NOTE: Filtering by `created_at >= since` will include any
                # demo / leftover events too, so we only assert ours are >= 4.
                assert body["total_in_window"] >= 4

                # Non-admin call → 403
                attendee_token = _jwt.encode(
                    {"sub": orig_id, "email": f"{orig_id}@example.com", "role": "organizer"},
                    os.environ["JWT_SECRET"],
                    algorithm="HS256",
                )
                r = await client.get(
                    "/api/admin/events/submission-trend",
                    headers={"Authorization": f"Bearer {attendee_token}"},
                )
                assert r.status_code == 403
        finally:
            await db.users.delete_many({"user_id": {"$in": [admin_id, orig_id]}})
            await db.events.delete_many({"event_id": {"$in": [
                now_event["event_id"], earlier_event["event_id"],
                yesterday_event["event_id"], old_event["event_id"], way_old["event_id"],
            ]}})

    asyncio.run(_run())
