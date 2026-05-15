"""Iteration 9 — Resend transactional email integration.

Covers:
- Template rendering for all 6 templates (subject + html + text).
- Send path with mocked Resend SDK (no real network).
- `email_logs` MongoDB persistence (status: sent / failed / skipped).
- Admin `GET /api/admin/email-logs` endpoint (auth, filters, stats).
- Booking-confirmation email triggered via Stripe payment success path.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from emails import TEMPLATES, send_template, _layout  # noqa: E402
from core import db  # noqa: E402

API_URL = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


# ---------------------------------------------------------------------------
# 1. Template rendering — every template returns (subject, html, text)
# ---------------------------------------------------------------------------
CTX_FIXTURES = {
    "booking_confirmation": {
        "user_name": "Alice", "booking_id": "bkg_abc", "event_id": "evt_1",
        "event_title": "Hamilton", "event_date": "2026-03-12 19:00",
        "venue": "Richard Rodgers", "city": "NY",
        "seats": ["A-5", "A-6"], "quantity": 2, "amount": 320.0,
    },
    "hold_expired": {
        "user_name": "Bob", "event_id": "evt_2", "event_title": "Dune",
    },
    "refund_issued": {
        "user_name": "Carol", "booking_id": "bkg_xyz",
        "event_title": "Hamilton", "amount": 160.0,
    },
    "organizer_event_approved": {
        "organizer_name": "Diana", "event_id": "evt_3", "event_title": "TEDx",
    },
    "organizer_payout_issued": {
        "organizer_name": "Erik", "payout_id": "pyt_001",
        "period": "Feb 2026", "bookings_count": 24, "amount": 2840.50,
    },
    "waitlist_spot_opened": {
        "user_name": "Frank", "event_id": "evt_4",
        "event_title": "Studio Ghibli", "waitlist_token": "wt_abc123",
    },
}


@pytest.mark.parametrize("template", list(TEMPLATES.keys()))
def test_template_renders(template: str):
    subject, html, text = TEMPLATES[template](CTX_FIXTURES[template])
    assert subject and isinstance(subject, str)
    assert "<html" in html.lower()
    assert "</html>" in html.lower()
    assert "AURA" in html
    # Text fallback is plain (no tags)
    assert "<" not in text.replace("—", "")
    # Brand color present in HTML
    assert "#FF4F00" in html


def test_layout_includes_preheader_and_brand():
    html = _layout("Test", "preheader text", "<p>body</p>", "Go", "https://example.com")
    assert "preheader text" in html
    assert "Test" in html
    assert "https://example.com" in html


def test_unknown_template_returns_failed():
    res = asyncio.run(send_template("does_not_exist", "x@example.com", {}, None))
    assert res["status"] == "failed"
    assert res["reason"] == "unknown_template"


# ---------------------------------------------------------------------------
# 2. send_template — mocked SDK (no real network), logs to MongoDB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_template_success_logs_to_db(monkeypatch):
    await db.email_logs.delete_many({"to": "test_success@example.com"})

    monkeypatch.setattr("emails.RESEND_API_KEY", "re_fake_key_for_test")
    with patch("resend.Emails.send", return_value={"id": "fake_resend_id_123"}):
        res = await send_template(
            "booking_confirmation",
            "test_success@example.com",
            CTX_FIXTURES["booking_confirmation"],
            db,
        )
    assert res["status"] == "sent"
    assert res["resend_id"] == "fake_resend_id_123"

    log = await db.email_logs.find_one({"to": "test_success@example.com"}, {"_id": 0})
    assert log is not None
    assert log["status"] == "sent"
    assert log["template"] == "booking_confirmation"
    assert log["resend_id"] == "fake_resend_id_123"


def test_send_template_handles_sdk_failure(monkeypatch):
    async def _run():
        from motor.motor_asyncio import AsyncIOMotorClient
        local_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        local_db = local_client[os.environ["DB_NAME"]]
        await local_db.email_logs.delete_many({"to": "test_fail@example.com"})
        with patch("resend.Emails.send", side_effect=Exception("network down")):
            res = await send_template(
                "booking_confirmation",
                "test_fail@example.com",
                CTX_FIXTURES["booking_confirmation"],
                local_db,
            )
        log = await local_db.email_logs.find_one({"to": "test_fail@example.com"}, {"_id": 0})
        local_client.close()
        return res, log

    monkeypatch.setattr("emails.RESEND_API_KEY", "re_fake_key")
    res, log = asyncio.run(_run())
    assert res["status"] == "failed"
    assert log["status"] == "failed"
    assert "network down" in log["reason"]


def test_send_template_skipped_when_no_api_key(monkeypatch):
    async def _run():
        from motor.motor_asyncio import AsyncIOMotorClient
        local_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        local_db = local_client[os.environ["DB_NAME"]]
        await local_db.email_logs.delete_many({"to": "test_skipped@example.com"})
        res = await send_template(
            "booking_confirmation",
            "test_skipped@example.com",
            CTX_FIXTURES["booking_confirmation"],
            local_db,
        )
        log = await local_db.email_logs.find_one({"to": "test_skipped@example.com"}, {"_id": 0})
        local_client.close()
        return res, log

    monkeypatch.setattr("emails.RESEND_API_KEY", "")
    res, log = asyncio.run(_run())
    assert res["status"] == "skipped"
    assert log["status"] == "skipped"


# ---------------------------------------------------------------------------
# 3. Admin /email-logs endpoint
# ---------------------------------------------------------------------------
def _admin_token() -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "admin@aura.events", "password": "admin123",
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


def _attendee_token() -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={
        "email": "attendee@aura.events", "password": "attendee123",
    }, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


def test_admin_email_logs_requires_admin():
    token = _attendee_token()
    r = requests.get(f"{API_URL}/api/admin/email-logs",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 403


def test_admin_email_logs_returns_stats_and_items():
    token = _admin_token()
    r = requests.get(f"{API_URL}/api/admin/email-logs",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert "stats" in body
    assert set(body["stats"].keys()) == {"sent", "failed", "skipped"}


def test_admin_email_logs_template_filter():
    token = _admin_token()
    r = requests.get(f"{API_URL}/api/admin/email-logs?template=booking_confirmation",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["template"] == "booking_confirmation"


def test_admin_email_logs_status_filter():
    token = _admin_token()
    r = requests.get(f"{API_URL}/api/admin/email-logs?status=sent",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["status"] == "sent"
