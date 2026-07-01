"""Regression tests for the embed widget tracking + analytics.

Covers:
  - Tracking pixel returns a real 1x1 GIF without errors when org/event missing.
  - Tracking writes to embed_events with normalized host and kind.
  - Organizer analytics rollup buckets by host + event correctly.
  - Loader JS now contains the `track(` helper.
"""
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


async def test_embed_tracking_pixel_and_analytics():
    organizer_id = f"em_org_{uuid.uuid4().hex[:8]}"
    other_id = f"em_other_{uuid.uuid4().hex[:8]}"
    event_a = f"evt_em_a_{uuid.uuid4().hex[:8]}"
    event_b = f"evt_em_b_{uuid.uuid4().hex[:8]}"

    await db.users.insert_one({
        "user_id": organizer_id,
        "email": f"{organizer_id}@example.com",
        "role": "organizer",
        "name": "Embed Org",
        "created_at": utc_now().isoformat(),
    })
    await db.events.insert_many([
        {"event_id": event_a, "organizer_id": organizer_id, "title": "A",
         "status": "approved", "date": utc_now().isoformat()},
        {"event_id": event_b, "organizer_id": organizer_id, "title": "B",
         "status": "approved", "date": utc_now().isoformat()},
    ])

    try:
        os.environ.setdefault("JWT_SECRET", "test-secret")
        from httpx import AsyncClient, ASGITransport  # noqa: WPS433
        from server import app  # noqa: WPS433
        import jwt as _jwt  # noqa: WPS433

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1) Bare pixel call returns a 1x1 GIF
            r = await client.get("/api/embed/track")
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("image/gif")
            assert len(r.content) > 30  # the GIF body
            assert r.content[:6] == b"GIF89a"

            # 2) Three impressions for event_a from promoter.co.nz
            for _ in range(3):
                await client.get(
                    f"/api/embed/track?organizer_id={organizer_id}&event_id={event_a}&kind=impression",
                    headers={"Referer": "https://promoter.co.nz/shows"},
                )
            # 1 click for event_a from the same host
            await client.get(
                f"/api/embed/track?organizer_id={organizer_id}&event_id={event_a}&kind=click",
                headers={"Referer": "https://promoter.co.nz/shows"},
            )
            # 2 impressions for event_b from venuegroup.com
            for _ in range(2):
                await client.get(
                    f"/api/embed/track?organizer_id={organizer_id}&event_id={event_b}&kind=impression",
                    headers={"Referer": "https://venuegroup.com/page"},
                )
            # Noise from another org — must NOT show up
            await client.get(
                f"/api/embed/track?organizer_id={other_id}&kind=impression",
                headers={"Referer": "https://noise.com"},
            )

            # Verify rows landed in DB
            got = await db.embed_events.count_documents({"organizer_id": organizer_id})
            assert got == 6

            # 3) Organizer analytics rollup
            token = _jwt.encode(
                {"sub": organizer_id, "email": f"{organizer_id}@example.com", "role": "organizer"},
                os.environ["JWT_SECRET"],
                algorithm="HS256",
            )
            r = await client.get(
                "/api/organizer/embed/analytics?days=30",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["totals"]["impressions"] == 5
            assert body["totals"]["clicks"] == 1
            # CTR = 1/5 * 100
            assert body["totals"]["ctr_pct"] == 20.0

            by_host = {h["host"]: h for h in body["by_host"]}
            assert by_host["promoter.co.nz"]["impressions"] == 3
            assert by_host["promoter.co.nz"]["clicks"] == 1
            assert by_host["venuegroup.com"]["impressions"] == 2

            by_event = {e["event_id"]: e for e in body["by_event"]}
            assert by_event[event_a]["impressions"] == 3
            assert by_event[event_a]["clicks"] == 1
            assert by_event[event_b]["impressions"] == 2
            # Titles hydrated
            assert by_event[event_a]["title"] == "A"

            # 4) Loader JS contains track helper
            r = await client.get("/api/embed/events.js")
            assert r.status_code == 200
            assert "function track(" in r.text
            assert "/api/embed/track" in r.text
    finally:
        await db.users.delete_one({"user_id": organizer_id})
        await db.events.delete_many({"event_id": {"$in": [event_a, event_b]}})
        await db.embed_events.delete_many({"organizer_id": {"$in": [organizer_id, other_id]}})

