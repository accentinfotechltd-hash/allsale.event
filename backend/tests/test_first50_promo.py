"""Auto-generated 'FIRST50' flash promo on event approval."""
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


def test_first50_promo_seeded_on_approval():
    admin_id = f"adm_p_{uuid.uuid4().hex[:8]}"
    org_id = f"org_p_{uuid.uuid4().hex[:8]}"
    org2_id = f"org_p2_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_p_{uuid.uuid4().hex[:8]}"
    event2_id = f"evt_p2_{uuid.uuid4().hex[:8]}"
    event3_id = f"evt_p3_{uuid.uuid4().hex[:8]}"

    async def _run():
        await db.users.insert_many([
            {"user_id": admin_id, "email": f"{admin_id}@example.com", "role": "admin",
             "name": "Admin", "created_at": utc_now().isoformat()},
            {"user_id": org_id, "email": f"{org_id}@example.com", "role": "organizer",
             "name": "Org", "created_at": utc_now().isoformat()},
            {"user_id": org2_id, "email": f"{org2_id}@example.com", "role": "organizer",
             "name": "Org 2", "created_at": utc_now().isoformat()},
        ])
        await db.events.insert_many([
            {"event_id": event_id, "organizer_id": org_id, "status": "pending",
             "title": "T1", "date": utc_now().isoformat()},
            {"event_id": event2_id, "organizer_id": org_id, "status": "pending",
             "title": "T2", "date": utc_now().isoformat()},
            {"event_id": event3_id, "organizer_id": org2_id, "status": "pending",
             "title": "T3 — opt out", "auto_promo_disabled": True,
             "date": utc_now().isoformat()},
        ])

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
                # 1) Approve first event → FIRST50 code is created
                r = await client.post(f"/api/admin/events/{event_id}/approve", headers=headers)
                assert r.status_code == 200, r.text
                code = await db.discount_codes.find_one(
                    {"created_by": org_id, "code": "FIRST50"}, {"_id": 0}
                )
                assert code is not None
                assert code["kind"] == "percent"
                assert code["value"] == 10.0
                assert code["max_uses"] == 50
                assert code["auto_generated"] is True
                assert code["event_id"] == event_id

                # 2) Approve second event by same organizer → no duplicate
                r = await client.post(f"/api/admin/events/{event2_id}/approve", headers=headers)
                assert r.status_code == 200, r.text
                count = await db.discount_codes.count_documents(
                    {"created_by": org_id, "code": "FIRST50"}
                )
                assert count == 1, "FIRST50 promo should be idempotent per organizer"

                # 3) Opt-out event by another organizer → no promo created
                r = await client.post(f"/api/admin/events/{event3_id}/approve", headers=headers)
                assert r.status_code == 200, r.text
                count = await db.discount_codes.count_documents(
                    {"created_by": org2_id, "code": "FIRST50"}
                )
                assert count == 0, "auto_promo_disabled events should skip the promo"
        finally:
            await db.users.delete_many({"user_id": {"$in": [admin_id, org_id, org2_id]}})
            await db.events.delete_many({"event_id": {"$in": [event_id, event2_id, event3_id]}})
            await db.discount_codes.delete_many({"created_by": {"$in": [org_id, org2_id]}})

    asyncio.run(_run())
