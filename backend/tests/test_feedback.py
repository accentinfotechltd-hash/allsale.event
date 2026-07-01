"""Post-event NPS feedback flow."""
import os
import uuid
import pytest
import httpx

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


@pytest.mark.asyncio
async def test_feedback_submission_flow():
    async with httpx.AsyncClient(timeout=15) as client:
        # Bootstrap an organizer + event + booking
        org = await client.post(f"{API}/auth/register", json={
            "email": f"fb_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test1234!", "name": "FB", "role": "organizer",
            "phone": "+64 21 555 4001",  # mandatory since Feb 2026
        })
        org_auth = {"Authorization": f"Bearer {org.json()['token']}"}

        ev = await client.post(f"{API}/events", json={
            "title": "Feedback Test",
            "description": "x",
            "category": "music",
            "venue": "v",
            "city": "Auckland",
            "date": "2030-01-01T20:00:00Z",
            "image_url": "https://example.com/x.jpg",
            "tiers": [{"name": "GA", "price": 0, "quantity": 100}],  # free to bypass Stripe-Connect gate
            "has_seatmap": False,
        }, headers=org_auth)
        event_id = ev.json()["event_id"]

        # Manually insert a paid booking row (simulating a real purchase)
        from motor.motor_asyncio import AsyncIOMotorClient
        client_db = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
        db = client_db[os.environ.get("DB_NAME", "test")]
        bid = "bk_" + uuid.uuid4().hex[:12]
        await db.bookings.insert_one({
            "booking_id": bid,
            "event_id": event_id,
            "user_id": org.json()["user_id"],
            "user_email": org.json()["email"],
            "status": "paid",
            "amount": 10,
        })

        # 1. GET feedback context
        r = await client.get(f"{API}/feedback/{bid}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["event"]["title"] == "Feedback Test"
        assert body["existing"] is None

        # 2. POST 5 stars
        r = await client.post(f"{API}/feedback/{bid}", json={
            "stars": 5,
            "comment": "Best night ever!",
            "display_name": "Sarah",
        })
        assert r.status_code == 200

        # 3. Re-GET shows existing rating
        r = await client.get(f"{API}/feedback/{bid}")
        assert r.json()["existing"]["stars"] == 5
        assert r.json()["existing"]["comment"] == "Best night ever!"

        # 4. Update to 3 stars (overwrite)
        r = await client.post(f"{API}/feedback/{bid}", json={"stars": 3})
        assert r.status_code == 200
        r = await client.get(f"{API}/feedback/{bid}")
        assert r.json()["existing"]["stars"] == 3

        # 5. Public event-feedback endpoint shows aggregate
        r = await client.get(f"{API}/events/{event_id}/feedback")
        body = r.json()
        assert body["count"] == 1
        assert body["avg_stars"] == 3.0
        # Comment only shows for >=4★, so this submission's comment is hidden
        assert body["comments"] == []

        # Bad booking_id → 404
        r = await client.get(f"{API}/feedback/bk_doesnotexist")
        assert r.status_code == 404

        # Out-of-range stars → 422
        r = await client.post(f"{API}/feedback/{bid}", json={"stars": 6})
        assert r.status_code == 422

        # Cleanup
        await db.bookings.delete_one({"booking_id": bid})
        client_db.close()
