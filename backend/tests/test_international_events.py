"""End-to-end test for international event support — country & timezone."""
import os
import uuid
import pytest
import httpx

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


async def _organizer_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{API}/auth/register", json={
        "email": f"intl_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test1234!",
        "name": "Intl Test",
        "role": "organizer",
    })
    return r.json()["token"]


@pytest.mark.asyncio
async def test_country_timezone_lifecycle():
    async with httpx.AsyncClient(timeout=15) as client:
        token = await _organizer_token(client)
        auth = {"Authorization": f"Bearer {token}"}

        # 1. Create an event in India
        r = await client.post(f"{API}/events", json={
            "title": "Mumbai Show",
            "description": "test",
            "category": "music",
            "venue": "NSCI Dome",
            "city": "Mumbai",
            "country": "IN",
            "timezone": "Asia/Kolkata",
            "date": "2030-06-01T20:00:00Z",
            "image_url": "https://example.com/x.jpg",
            "currency": "INR",
            "tiers": [{"name": "GA", "price": 999, "quantity": 100}],
            "has_seatmap": False,
        }, headers=auth)
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev["country"] == "IN"
        assert ev["timezone"] == "Asia/Kolkata"
        assert ev["currency"] == "INR"
        ev_id = ev["event_id"]

        # 2. Create another in NZ — default country path
        r = await client.post(f"{API}/events", json={
            "title": "Auckland Show",
            "description": "test",
            "category": "music",
            "venue": "Spark Arena",
            "city": "Auckland",
            "date": "2030-06-02T20:00:00Z",
            "image_url": "https://example.com/x.jpg",
            "currency": "NZD",
            "tiers": [{"name": "GA", "price": 50, "quantity": 100}],
            "has_seatmap": False,
        }, headers=auth)
        assert r.status_code == 200
        nz_ev = r.json()
        assert nz_ev["country"] == "NZ"  # defaults applied

        # Admin-approve both so they appear in public listings
        admin = await client.post(f"{API}/auth/login", json={"email": "admin@allsale.events", "password": "admin123"})
        if admin.status_code != 200:
            pytest.skip("No admin seeded")
        a_auth = {"Authorization": f"Bearer {admin.json()['token']}"}
        await client.post(f"{API}/admin/events/{ev_id}/approve", headers=a_auth)
        await client.post(f"{API}/admin/events/{nz_ev['event_id']}/approve", headers=a_auth)

        # 3. /events?country=IN returns only the Mumbai event
        r = await client.get(f"{API}/events", params={"country": "IN"})
        assert r.status_code == 200
        ids = [e["event_id"] for e in r.json()]
        assert ev_id in ids
        assert nz_ev["event_id"] not in ids

        # 4. /events/countries lists both
        r = await client.get(f"{API}/events/countries")
        assert r.status_code == 200
        codes = {row["country"] for row in r.json()}
        assert "IN" in codes
        assert "NZ" in codes

        # 5. PATCH the Mumbai event → switch to UAE
        r = await client.patch(f"{API}/events/{ev_id}", json={
            "country": "AE", "timezone": "Asia/Dubai",
        }, headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["country"] == "AE"
        assert r.json()["timezone"] == "Asia/Dubai"

        # 6. Legacy events without country still show NZ via event_to_public
        # (Already covered by the default-case test above.)
