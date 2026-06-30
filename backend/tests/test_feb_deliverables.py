"""Backend tests for the three Feb-2026 deliverables:

1. POST /api/admin/organizers/backfill-welcome-emails — idempotent legacy welcome blast
2. PUT  /api/auth/change-password — now sends a confirmation alert email
3. GET  /api/gift-cards/{code}/balance — public balance lookup

Hits the live running backend (localhost:8001). Collapsed into one async test
because Motor caches its connection on the first event loop it sees, and
pytest-asyncio gives each test a fresh loop by default.
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


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("token") or body.get("access_token")


@pytest.mark.asyncio
async def test_feb_deliverables_full_flow():
    suffix = uuid.uuid4().hex[:8]
    legacy_a = f"legacy_a_{suffix}@example.com"
    legacy_b = f"legacy_b_{suffix}@example.com"
    stamped_c = f"stamped_c_{suffix}@example.com"
    noadmin_email = f"noadmin_{suffix}@example.com"
    pw_email = f"pwchange_{suffix}@example.com"
    pwd_hashed = hash_password("Pass1234!")
    gc_code = f"GC-TEST-{suffix.upper()}"
    gc_card_id = f"gc_test_{suffix}"
    pw_uid = f"u_pw_{suffix}"

    await db.users.insert_many([
        # Welcome backfill fixtures
        {"user_id": f"u_la_{suffix}", "name": "Legacy A", "email": legacy_a,
         "password_hash": pwd_hashed, "role": "organizer", "phone": "+64215550001",
         "created_at": utc_now().isoformat()},
        {"user_id": f"u_lb_{suffix}", "name": "Legacy B", "email": legacy_b,
         "password_hash": pwd_hashed, "role": "organizer", "phone": "+64215550002",
         "created_at": utc_now().isoformat()},
        {"user_id": f"u_sc_{suffix}", "name": "Stamped C", "email": stamped_c,
         "password_hash": pwd_hashed, "role": "organizer", "phone": "+64215550003",
         "organizer_welcome_sent_at": utc_now().isoformat(),
         "created_at": utc_now().isoformat()},
        # 403 fixture
        {"user_id": f"u_na_{suffix}", "name": "Org NoAdmin", "email": noadmin_email,
         "password_hash": pwd_hashed, "role": "organizer", "phone": "+64215550009",
         "created_at": utc_now().isoformat()},
        # Password change fixture
        {"user_id": pw_uid, "name": "Pw Tester", "email": pw_email,
         "password_hash": hash_password("OldPass123!"), "role": "organizer", "phone": "+64215550010",
         "created_at": utc_now().isoformat()},
    ])
    await db.gift_cards.insert_one({
        "card_id": gc_card_id, "code": gc_code, "amount": 50.0, "balance": 50.0,
        "currency": "NZD", "status": "active", "purchased_by": "u_test",
        "recipient_email": f"recipient_{suffix}@example.com",
        "created_at": utc_now().isoformat(),
    })

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            admin_tok = await _login(client, "admin@allsale.events", "admin123")
            admin_h = {"Authorization": f"Bearer {admin_tok}"}

            # =====================================================================
            # 1) Welcome backfill — dry-run, send-with-limit, idempotency
            # =====================================================================
            r = await client.post(f"{API}/admin/organizers/backfill-welcome-emails",
                                  json={"dry_run": True}, headers=admin_h)
            assert r.status_code == 200, r.text
            base = r.json()
            assert base["dry_run"] is True
            base_eligible = base["eligible"]
            assert base_eligible >= 2

            # Send to 2 with limit so we don't blast every legacy org.
            r = await client.post(f"{API}/admin/organizers/backfill-welcome-emails",
                                  json={"dry_run": False, "limit": 2}, headers=admin_h)
            assert r.status_code == 200
            assert r.json()["sent"] == 2

            # Pre-stamped user is left alone.
            sc = await db.users.find_one({"email": stamped_c})
            assert sc.get("organizer_welcome_sent_at")

            # Eligible count dropped by exactly 2.
            r = await client.post(f"{API}/admin/organizers/backfill-welcome-emails",
                                  json={"dry_run": True}, headers=admin_h)
            assert r.json()["eligible"] == base_eligible - 2

            # 1b. Non-admin gets 403.
            org_tok = await _login(client, noadmin_email, "Pass1234!")
            r = await client.post(f"{API}/admin/organizers/backfill-welcome-emails",
                                  json={"dry_run": True},
                                  headers={"Authorization": f"Bearer {org_tok}"})
            assert r.status_code == 403

            # =====================================================================
            # 2) Change password — confirmation email log row created
            # =====================================================================
            pw_tok = await _login(client, pw_email, "OldPass123!")
            r = await client.put(
                f"{API}/auth/change-password",
                json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
                headers={"Authorization": f"Bearer {pw_tok}"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is True

            # The email is fired by send_template_fireforget which runs as a
            # background task. Poll briefly for the log row to appear.
            import asyncio as _asyncio
            log = None
            for _ in range(20):  # up to ~4s
                log = await db.email_logs.find_one({"template": "password_changed_alert", "to": pw_email})
                if log:
                    break
                await _asyncio.sleep(0.2)
            assert log is not None
            assert log["template"] == "password_changed_alert"

            # New password works on next login; old rejected.
            r = await client.post(f"{API}/auth/login",
                                  json={"email": pw_email, "password": "NewPass456!"})
            assert r.status_code == 200
            r = await client.post(f"{API}/auth/login",
                                  json={"email": pw_email, "password": "OldPass123!"})
            assert r.status_code != 200

            # =====================================================================
            # 3) Gift card balance — public lookup
            # =====================================================================
            r = await client.get(f"{API}/gift-cards/{gc_code}/balance")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["code"] == gc_code
            assert body["amount"] == 50.0
            assert body["balance"] == 50.0
            assert body["status"] == "active"

            # Case-insensitive code normalisation.
            r = await client.get(f"{API}/gift-cards/{gc_code.lower()}/balance")
            assert r.status_code == 200
            assert r.json()["code"] == gc_code

            # Unknown code → 404.
            r = await client.get(f"{API}/gift-cards/NOSUCHCARD-{suffix}/balance")
            assert r.status_code == 404
    finally:
        await db.users.delete_many({"email": {"$in": [
            legacy_a, legacy_b, stamped_c, noadmin_email, pw_email,
        ]}})
        await db.gift_cards.delete_one({"card_id": gc_card_id})
        await db.email_logs.delete_many({"to": pw_email, "template": "password_changed_alert"})
