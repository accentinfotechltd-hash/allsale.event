"""Recruitment leads admin pipeline — end-to-end flow.

Covers: bulk upsert + dedupe, list filters, send-flyer + status flip,
delete, and the auto-conversion hook from /api/auth/register.

One async test to dodge the Motor/pytest-asyncio event-loop quirk.
"""
from __future__ import annotations

import asyncio
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

from core import db  # noqa: E402

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("token") or body.get("access_token")


@pytest.mark.asyncio
async def test_recruitment_leads_full_lifecycle():
    suffix = uuid.uuid4().hex[:8]
    org_email = f"rl_org_{suffix}@example.com"
    inf_email = f"rl_inf_{suffix}@example.com"
    dup_email = f"rl_dup_{suffix}@example.com"
    convert_email = f"rl_convert_{suffix}@example.com"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            admin_tok = await _login(client, "admin@allsale.events", "admin123")
            h = {"Authorization": f"Bearer {admin_tok}"}

            # =====================================================================
            # 1) Bulk create — 3 valid + 1 garbage row (no @) → 3 created, 1 skipped
            # =====================================================================
            r = await client.post(f"{API}/admin/recruitment-leads", json={
                "leads": [
                    {"name": "Org Lead", "email": org_email, "source": "eventfinda", "event_count": 24, "kind": "organizer"},
                    {"name": "Influencer Lead", "email": inf_email, "source": "instagram", "kind": "influencer"},
                    {"name": "Dup Lead", "email": dup_email, "source": "eventfinda", "event_count": 5},
                    {"name": "Garbage", "email": "not-an-email", "source": "manual"},
                ],
            }, headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["created"] == 3
            assert body["skipped"] == 1
            assert body["updated"] == 0

            # =====================================================================
            # 2) Re-upload SAME emails with new event_count → all 3 updated, 0 created
            # =====================================================================
            r = await client.post(f"{API}/admin/recruitment-leads", json={
                "leads": [
                    {"name": "Org Lead — Refined", "email": org_email, "event_count": 42},
                    {"name": "Influencer Lead", "email": inf_email, "kind": "influencer"},
                    {"name": "Dup Lead Updated", "email": dup_email, "notes": "Big promoter"},
                ],
            }, headers=h)
            body = r.json()
            assert body["created"] == 0
            assert body["updated"] == 3

            # Check the org lead's event_count was updated to 42.
            r = await client.get(f"{API}/admin/recruitment-leads", params={"q": suffix}, headers=h)
            items = r.json()["items"]
            org_lead = next((l for l in items if l["email"] == org_email), None)
            assert org_lead is not None
            assert org_lead["event_count"] == 42
            assert org_lead["name"] == "Org Lead — Refined"

            # =====================================================================
            # 3) Filter by kind=influencer — only inf_email should show
            # =====================================================================
            r = await client.get(f"{API}/admin/recruitment-leads",
                                 params={"kind": "influencer", "q": suffix}, headers=h)
            items = r.json()["items"]
            assert all(l["kind"] == "influencer" for l in items)
            assert any(l["email"] == inf_email for l in items)

            # =====================================================================
            # 4) Send flyer to org + inf leads — status flips to "contacted"
            # =====================================================================
            r = await client.get(f"{API}/admin/recruitment-leads", params={"q": suffix}, headers=h)
            ids_to_send = [l["lead_id"] for l in r.json()["items"]
                            if l["email"] in (org_email, inf_email)]
            assert len(ids_to_send) == 2

            r = await client.post(f"{API}/admin/recruitment-leads/send-flyer",
                                  json={"lead_ids": ids_to_send}, headers=h)
            assert r.status_code == 200
            res = r.json()
            assert res["sent"] == 2

            # Status should be "contacted" now.
            await asyncio.sleep(0.3)  # let the fire-and-forget catch up
            for email in (org_email, inf_email):
                lead = await db.recruitment_leads.find_one({"email": email})
                assert lead["status"] == "contacted"
                assert lead.get("contacted_at")
                # Org lead → organizer flyer; inf lead → influencer flyer.
                expected = "organizer_features_flyer" if email == org_email else "influencer_features_flyer"
                assert lead.get("last_flyer_kind") == expected

            # =====================================================================
            # 5) Auto-conversion: register a new user with the dup_email
            #    → lead is stamped "signed_up" with the user_id linked.
            # =====================================================================
            # First add a "convert me" lead that will be signed_up via register.
            await client.post(f"{API}/admin/recruitment-leads", json={
                "leads": [{"name": "Convert Me", "email": convert_email, "source": "eventfinda", "kind": "organizer"}],
            }, headers=h)

            r = await client.post(f"{API}/auth/register", json={
                "name": "Convert Me", "email": convert_email,
                "password": "Pass1234!", "role": "organizer", "phone": "+64215559999",
            })
            assert r.status_code == 200, r.text

            await asyncio.sleep(0.3)
            lead = await db.recruitment_leads.find_one({"email": convert_email})
            assert lead["status"] == "signed_up"
            assert lead.get("signed_up_user_id")
            assert lead.get("signed_up_at")

            # =====================================================================
            # 6) Delete a lead
            # =====================================================================
            r = await client.get(f"{API}/admin/recruitment-leads", params={"q": suffix}, headers=h)
            dup_id = next(l["lead_id"] for l in r.json()["items"] if l["email"] == dup_email)
            r = await client.delete(f"{API}/admin/recruitment-leads/{dup_id}", headers=h)
            assert r.status_code == 200
            r = await client.delete(f"{API}/admin/recruitment-leads/{dup_id}", headers=h)
            assert r.status_code == 404  # already gone

            # =====================================================================
            # 7) Non-admin cannot use any of the lead endpoints
            # =====================================================================
            non_admin_tok = await _login(client, convert_email, "Pass1234!")
            r = await client.get(f"{API}/admin/recruitment-leads",
                                 headers={"Authorization": f"Bearer {non_admin_tok}"})
            assert r.status_code == 403
    finally:
        await db.recruitment_leads.delete_many({"email": {"$in": [
            org_email, inf_email, dup_email, convert_email,
        ]}})
        await db.users.delete_many({"email": convert_email})
