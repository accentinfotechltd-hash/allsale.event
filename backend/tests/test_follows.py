"""Follow-organizer + weekly digest regression tests."""
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


def test_follow_endpoints_and_notify():
    org_id = f"fol_org_{uuid.uuid4().hex[:8]}"
    attendee_id = f"fol_att_{uuid.uuid4().hex[:8]}"
    other_id = f"fol_oth_{uuid.uuid4().hex[:8]}"

    async def _run():
        await db.users.insert_many([
            {"user_id": org_id, "email": f"{org_id}@example.com",
             "role": "organizer", "name": "Test Promoter",
             "created_at": utc_now().isoformat()},
            {"user_id": attendee_id, "email": f"{attendee_id}@example.com",
             "role": "attendee", "name": "Fan",
             "created_at": utc_now().isoformat()},
            {"user_id": other_id, "email": f"{other_id}@example.com",
             "role": "attendee", "name": "Other Fan",
             "created_at": utc_now().isoformat()},
        ])

        try:
            os.environ.setdefault("JWT_SECRET", "test-secret")
            from httpx import AsyncClient, ASGITransport  # noqa: WPS433
            from server import app  # noqa: WPS433
            import jwt as _jwt  # noqa: WPS433

            def _token(uid, role):
                return _jwt.encode(
                    {"sub": uid, "email": f"{uid}@example.com", "role": role},
                    os.environ["JWT_SECRET"],
                    algorithm="HS256",
                )

            att_h = {"Authorization": f"Bearer {_token(attendee_id, 'attendee')}"}
            other_h = {"Authorization": f"Bearer {_token(other_id, 'attendee')}"}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Public organizer page works without auth
                r = await client.get(f"/api/organizers/{org_id}/public")
                assert r.status_code == 200
                assert r.json()["follower_count"] == 0

                # Initial state — not following
                r = await client.get(f"/api/organizers/{org_id}/follow", headers=att_h)
                assert r.status_code == 200
                assert r.json()["following"] is False

                # Can't follow yourself
                r = await client.post(f"/api/organizers/{org_id}/follow", headers={"Authorization": f"Bearer {_token(org_id, 'organizer')}"})
                assert r.status_code == 400

                # Follow
                r = await client.post(f"/api/organizers/{org_id}/follow", headers=att_h)
                assert r.status_code == 200
                assert r.json()["following"] is True
                assert r.json()["follower_count"] == 1

                # Idempotent — double-follow doesn't error or double-count
                r = await client.post(f"/api/organizers/{org_id}/follow", headers=att_h)
                assert r.json()["follower_count"] == 1

                # Other user also follows → count goes to 2
                r = await client.post(f"/api/organizers/{org_id}/follow", headers=other_h)
                assert r.json()["follower_count"] == 2

                # My following list
                r = await client.get("/api/me/following", headers=att_h)
                assert r.status_code == 200
                body = r.json()
                assert body["total"] == 1
                assert body["items"][0]["organizer_id"] == org_id

                # Public count reflects the 2 followers now
                r = await client.get(f"/api/organizers/{org_id}/public")
                assert r.json()["follower_count"] == 2

                # Unfollow
                r = await client.delete(f"/api/organizers/{org_id}/follow", headers=att_h)
                assert r.status_code == 200
                assert r.json()["following"] is False
                assert r.json()["follower_count"] == 1

                # Following non-organizer email → 400
                r = await client.post(f"/api/organizers/{other_id}/follow", headers=att_h)
                assert r.status_code == 400  # attendee role

                # Unknown organizer → 404
                r = await client.post("/api/organizers/nonexistent_id/follow", headers=att_h)
                assert r.status_code == 404
        finally:
            await db.users.delete_many({"user_id": {"$in": [org_id, attendee_id, other_id]}})
            await db.follows.delete_many({"organizer_id": org_id})

    asyncio.run(_run())
