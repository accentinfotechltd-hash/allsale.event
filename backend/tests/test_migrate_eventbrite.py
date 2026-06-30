"""Eventbrite migration endpoint — input validation + JSON-LD parsing.

We don't hit Eventbrite's live site from CI (flaky, slow, ToS-grey). Instead
we exercise `_extract_event_from_jsonld` + `_normalize_event` directly with
canned HTML, and only smoke-test the FastAPI route with URL-validation
inputs (which are pure-Python guards that never touch the network).
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now, hash_password  # noqa: E402

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


SAMPLE_EVENTBRITE_HTML = """
<!DOCTYPE html>
<html><head>
<script type="application/ld+json">{"@type": "WebPage"}</script>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "Sample Music Festival 2026",
  "description": "A test event description that should be copied over.",
  "startDate": "2026-08-15T19:00:00+12:00",
  "endDate": "2026-08-15T23:30:00+12:00",
  "image": "https://example.com/poster.jpg",
  "location": {
    "@type": "Place",
    "name": "Spark Arena",
    "address": {
      "streetAddress": "42 Mahuhu Crescent",
      "addressLocality": "Auckland",
      "postalCode": "1010",
      "addressCountry": "NZ"
    }
  },
  "organizer": { "@type": "Organization", "name": "Some Promoter Ltd", "url": "https://example.com" },
  "offers": [
    {"@type": "Offer", "name": "Early Bird", "price": 45.0, "priceCurrency": "NZD", "availability": "https://schema.org/InStock"},
    {"@type": "Offer", "name": "General Admission", "price": 65.0, "priceCurrency": "NZD"},
    {"@type": "Offer", "name": "VIP", "price": 150.0, "priceCurrency": "NZD", "availability": "https://schema.org/SoldOut"},
    {"@type": "Offer", "name": "Free", "price": 0, "priceCurrency": "NZD"}
  ]
}
</script>
</head><body></body></html>
"""


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("token") or body.get("access_token")


def test_parse_jsonld_normalizes_event_payload():
    # Pure-function test — no network, no event loop. Imported here to avoid
    # touching the FastAPI app/Motor init when only the parser is tested.
    from routers.migrations import _extract_event_from_jsonld, _normalize_event

    raw = _extract_event_from_jsonld(SAMPLE_EVENTBRITE_HTML)
    assert raw is not None
    assert raw["@type"] == "Event"

    draft = _normalize_event(raw)
    assert draft["title"] == "Sample Music Festival 2026"
    assert draft["description"].startswith("A test event description")
    assert draft["start_date"].startswith("2026-08-15T19:00:00")
    assert draft["end_date"].startswith("2026-08-15T23:30:00")
    assert draft["venue_name"] == "Spark Arena"
    assert "Mahuhu Crescent" in draft["venue_address"]
    assert draft["city"] == "Auckland"
    assert draft["country"] == "NZ"
    assert draft["image_url"] == "https://example.com/poster.jpg"
    assert draft["currency"] == "NZD"
    assert draft["source_organizer_name"] == "Some Promoter Ltd"

    # Free + sold-out tier handling — `Free` must be dropped, `VIP` kept but
    # flagged unavailable.
    tier_names = {t["name"] for t in draft["tiers"]}
    assert "Free" not in tier_names
    assert tier_names == {"Early Bird", "General Admission", "VIP"}
    vip = next(t for t in draft["tiers"] if t["name"] == "VIP")
    assert vip["available"] is False
    early = next(t for t in draft["tiers"] if t["name"] == "Early Bird")
    assert early["available"] is True
    assert early["price"] == 45.0


@pytest.mark.asyncio
async def test_migrate_eventbrite_url_validation():
    suffix = uuid.uuid4().hex[:8]
    email = f"migrate_{suffix}@example.com"
    await db.users.insert_one({
        "user_id": f"u_m_{suffix}", "name": "Migrator", "email": email,
        "password_hash": hash_password("Pass1234!"), "role": "organizer",
        "phone": "+64215559911", "created_at": utc_now().isoformat(),
    })
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await _login(client, email, "Pass1234!")
            h = {"Authorization": f"Bearer {tok}"}

            # 1. Reject non-Eventbrite hosts
            r = await client.post(f"{API}/migrate/eventbrite",
                                  json={"url": "https://www.google.com/event"}, headers=h)
            assert r.status_code == 400
            assert "Eventbrite" in r.json()["detail"]

            # 2. Reject malformed URLs
            r = await client.post(f"{API}/migrate/eventbrite",
                                  json={"url": "not-a-url"}, headers=h)
            assert r.status_code == 400

            # 3. Reject Eventbrite URLs that aren't event pages (e.g. discovery)
            r = await client.post(f"{API}/migrate/eventbrite",
                                  json={"url": "https://www.eventbrite.com/d/new-zealand/events/"}, headers=h)
            assert r.status_code == 400
            assert "event url" in r.json()["detail"].lower()

            # 4. Auth required — anon request gets 401/403
            r = await client.post(f"{API}/migrate/eventbrite",
                                  json={"url": "https://www.eventbrite.com/e/anything-tickets-1"})
            assert r.status_code in (401, 403)
    finally:
        await db.users.delete_one({"email": email})
