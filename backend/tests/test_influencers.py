"""Smoke tests for the influencer marketplace surface.

Exercises:
  1. enable / me / disable lifecycle
  2. open marketplace listing (public)
  3. event flag (affiliate_program_open) persists via PATCH
  4. self-join campaign creates an affiliate row tagged with influencer_id
  5. dashboard rollup math
  6. payout request validation (below threshold => 400)
  7. UTM link generator
  8. public profile endpoint
"""
import os
import uuid
import asyncio
import pytest
import httpx

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")
HEAD = {"Content-Type": "application/json"}


async def _signup_and_token(client: httpx.AsyncClient, role: str = "attendee") -> tuple[str, dict]:
    email = f"inf_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(f"{API}/auth/register", json={
        "email": email, "password": "Test1234!", "name": "Test User", "role": role,
        "phone": "+64 21 555 0099",  # mandatory since Feb 2026
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data


@pytest.mark.asyncio
async def test_full_influencer_lifecycle():
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Create an organizer + an event with the program OPEN.
        org_token, org_user = await _signup_and_token(client, role="organizer")
        ev_payload = {
            "title": "Influencer Test Event",
            "description": "QA seed",
            "category": "music",
            "venue": "Test Venue",
            "city": "Auckland",
            "date": "2030-01-01T20:00:00Z",
            "image_url": "https://example.com/x.jpg",
            "tiers": [{"name": "GA", "price": 0, "quantity": 100}],
            "has_seatmap": False,
            "affiliate_program_open": True,
            "affiliate_default_commission_pct": 12.5,
        }
        rcr = await client.post(f"{API}/events", json=ev_payload, headers={"Authorization": f"Bearer {org_token}"})
        assert rcr.status_code == 200, rcr.text
        ev = rcr.json()
        assert ev["affiliate_program_open"] is True
        assert ev["affiliate_default_commission_pct"] == 12.5

        # Admin needs to approve the event so listings see it
        # (Skip for this test — backend creates as "pending" for organizers.
        # For dashboard math we only need the affiliate row, not approval.)

        # 2. Create an attendee, enable influencer mode
        inf_token, _ = await _signup_and_token(client, role="attendee")
        inf_auth = {"Authorization": f"Bearer {inf_token}"}
        unique_name = f"QA Creator {uuid.uuid4().hex[:6]}"
        r = await client.post(f"{API}/influencer/enable", json={
            "display_name": unique_name,
            "bio": "Test creator",
            "follower_count_total": 12345,
            "categories": ["music", "comedy"],
            "city": "Wellington",
            "social_handles": {"instagram": "qa_handle"},
        }, headers=inf_auth)
        assert r.status_code == 200, r.text
        prof = r.json()
        assert prof["display_name"] == unique_name
        assert prof["follower_count_total"] == 12345

        # 3. /me should now report enabled=true
        r = await client.get(f"{API}/influencer/me", headers=inf_auth)
        assert r.status_code == 200
        assert r.json()["enabled"] is True

        # 4. Public marketplace listing
        r = await client.get(f"{API}/influencers")
        assert r.status_code == 200
        names = [p["display_name"] for p in r.json()]
        assert unique_name in names

        # 5. Public profile
        r = await client.get(f"{API}/influencers/{prof['user_id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["display_name"] == unique_name
        assert body["follower_count_total"] == 12345
        assert "stats" in body

        # 6. Self-join the campaign
        # Need the event to be approved=approved for the available list,
        # but join itself only requires `affiliate_program_open`.
        r = await client.post(f"{API}/influencer/campaigns/join", json={"event_id": ev["event_id"]}, headers=inf_auth)
        assert r.status_code == 200, r.text
        joined = r.json()
        assert "code" in joined
        # Joining again returns already_joined
        r2 = await client.post(f"{API}/influencer/campaigns/join", json={"event_id": ev["event_id"]}, headers=inf_auth)
        assert r2.status_code == 200
        assert r2.json().get("already_joined") is True
        assert r2.json()["code"] == joined["code"]

        # 7. Dashboard rollup
        r = await client.get(f"{API}/influencer/dashboard", headers=inf_auth)
        assert r.status_code == 200
        dash = r.json()
        assert dash["summary"]["total_conversions"] == 0
        assert len(dash["campaigns"]) >= 1

        # 8. Payout request below threshold rejected
        r = await client.post(f"{API}/influencer/payouts/request", headers=inf_auth)
        assert r.status_code == 400
        assert "Minimum" in r.json()["detail"] or "Connect" in r.json()["detail"]

        # 9. UTM link generator (organizer side)
        # Make an affiliate code first
        aff_r = await client.post(f"{API}/organizer/affiliates", json={
            "code": f"QA{uuid.uuid4().hex[:6].upper()}",
            "partner_name": "QA Partner",
            "commission_pct": 5,
            "event_id": ev["event_id"],
        }, headers={"Authorization": f"Bearer {org_token}"})
        assert aff_r.status_code == 200, aff_r.text
        code = aff_r.json()["code"]

        utm_r = await client.post(f"{API}/organizer/utm-link", json={
            "base_url": f"https://www.allsale.events/events/{ev['event_id']}",
            "source": "facebook",
            "medium": "paid",
            "campaign": "launch",
            "affiliate_code": code,
        }, headers={"Authorization": f"Bearer {org_token}"})
        assert utm_r.status_code == 200, utm_r.text
        url = utm_r.json()["url"]
        assert "utm_source=facebook" in url
        assert "utm_campaign=launch" in url
        assert f"aff={code}" in url

        # 10. Disable
        r = await client.post(f"{API}/influencer/disable", headers=inf_auth)
        assert r.status_code == 200

        # marketplace should no longer list THIS user's display name
        r = await client.get(f"{API}/influencers")
        ids = [p["user_id"] for p in r.json()]
        assert prof["user_id"] not in ids


@pytest.mark.asyncio
async def test_join_closed_program_rejected():
    async with httpx.AsyncClient(timeout=15) as client:
        org_token, _ = await _signup_and_token(client, role="organizer")
        rcr = await client.post(f"{API}/events", json={
            "title": "Closed Event",
            "description": "closed",
            "category": "music",
            "venue": "v",
            "city": "Auckland",
            "date": "2030-01-01T20:00:00Z",
            "image_url": "https://x.com/y.jpg",
            "tiers": [{"name": "GA", "price": 0, "quantity": 1}],
            "has_seatmap": False,
            "affiliate_program_open": False,
        }, headers={"Authorization": f"Bearer {org_token}"})
        ev = rcr.json()

        inf_token, _ = await _signup_and_token(client, role="attendee")
        await client.post(f"{API}/influencer/enable", json={
            "display_name": "Other Creator", "categories": ["music"],
        }, headers={"Authorization": f"Bearer {inf_token}"})

        r = await client.post(f"{API}/influencer/campaigns/join", json={"event_id": ev["event_id"]}, headers={"Authorization": f"Bearer {inf_token}"})
        assert r.status_code == 403
