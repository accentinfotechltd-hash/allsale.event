"""Multi-pick editor's-pick lifecycle test."""
import os
import uuid
import pytest
import httpx

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


async def _admin_token(client: httpx.AsyncClient) -> str:
    # Use the dev admin seeded in core (admin@allsale.events / admin123)
    r = await client.post(f"{API}/auth/login", json={"email": "admin@allsale.events", "password": "admin123"})
    if r.status_code != 200:
        # Fallback: register a fresh admin via dev hook isn't available;
        # at minimum we'll register an organizer to exercise the public endpoint.
        return ""
    return r.json()["token"]


@pytest.mark.asyncio
async def test_multi_editor_pick_lifecycle():
    async with httpx.AsyncClient(timeout=15) as client:
        token = await _admin_token(client)
        if not token:
            pytest.skip("No admin account seeded; skipping multi-pick test.")
        auth = {"Authorization": f"Bearer {token}"}

        # 1. Create 3 approved events directly via the admin event creation.
        org_r = await client.post(f"{API}/auth/register", json={
            "email": f"orgmpick_{uuid.uuid4().hex[:6]}@example.com",
            "password": "OrgPass1!",
            "name": "MPick Org",
            "role": "organizer",
            "phone": "+64 21 555 4003",  # mandatory since Feb 2026
        })
        org_token = org_r.json()["token"]
        org_auth = {"Authorization": f"Bearer {org_token}"}

        event_ids = []
        for i in range(3):
            r = await client.post(f"{API}/events", json={
                "title": f"Multi Pick Event {i+1}",
                "description": "test",
                "category": "music",
                "venue": "v",
                "city": "Auckland",
                "date": "2030-01-01T20:00:00Z",
                "image_url": "https://example.com/x.jpg",
                "tiers": [{"name": "GA", "price": 0, "quantity": 100}],  # free to bypass Stripe-Connect gate
                "has_seatmap": False,
            }, headers=org_auth)
            ev_id = r.json()["event_id"]
            event_ids.append(ev_id)
            # Approve as admin
            ap = await client.post(f"{API}/admin/events/{ev_id}/approve", headers=auth)
            assert ap.status_code == 200, ap.text

        # 2. PATCH editor_pick with 3 picks
        r = await client.patch(f"{API}/admin/site-settings", json={
            "editor_pick": {
                "event_id": None,
                "blurb": "",
                "badge_text": "Trending",
                "picks": [
                    {"event_id": event_ids[0], "blurb": "First pick"},
                    {"event_id": event_ids[1], "blurb": "Second pick"},
                    {"event_id": event_ids[2], "blurb": "Third pick"},
                ],
            },
        }, headers=auth)
        assert r.status_code == 200, r.text

        # 3. Public endpoint returns all 3 picks
        r = await client.get(f"{API}/site-settings/editor-pick")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["badge_text"] == "Trending"
        assert len(body["picks"]) == 3
        # Legacy single-field still returns the first pick
        assert body["event"]["event_id"] == event_ids[0]
        assert body["blurb"] == "First pick"

        # 4. Remove the middle pick + reorder
        r = await client.patch(f"{API}/admin/site-settings", json={
            "editor_pick": {
                "picks": [
                    {"event_id": event_ids[2], "blurb": "Now first"},
                    {"event_id": event_ids[0], "blurb": "Now second"},
                ],
            },
        }, headers=auth)
        assert r.status_code == 200
        r = await client.get(f"{API}/site-settings/editor-pick")
        body = r.json()
        assert len(body["picks"]) == 2
        assert body["picks"][0]["event"]["event_id"] == event_ids[2]
        assert body["picks"][1]["event"]["event_id"] == event_ids[0]

        # 5. Send picks=[] to clear → falls back to first featured
        r = await client.patch(f"{API}/admin/site-settings", json={
            "editor_pick": {"picks": []},
        }, headers=auth)
        assert r.status_code == 200
        r = await client.get(f"{API}/site-settings/editor-pick")
        body = r.json()
        assert body["picks"] == []
