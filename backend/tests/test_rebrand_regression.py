"""Iteration 18 — Rebrand AURA → Allsale Events: auth migration + email templates."""
from __future__ import annotations

import os
import sys
import re
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

API = os.environ.get("EXTERNAL_API_URL") or "https://seathold.preview.emergentagent.com"


# ---------------------------------------------------------------------------
# Auth migration — seeded @allsale.events accounts log in successfully
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("email,password,role", [
    ("admin@allsale.events", "admin123", "admin"),
    ("organizer@allsale.events", "organizer123", "organizer"),
    ("attendee@allsale.events", "attendee123", "attendee"),
])
def test_seeded_allsale_credentials_login(email, password, role):
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    body = r.json()
    assert "token" in body and isinstance(body["token"], str) and len(body["token"]) > 20
    assert body["email"] == email
    assert body["role"] == role
    # Brand check: admin/organizer display name should not contain 'AURA'
    if role in ("admin", "organizer"):
        assert "AURA" not in (body.get("name") or ""), f"User '{email}' name still says AURA: {body.get('name')!r}"


def test_legacy_aura_credentials_do_not_exist():
    """Legacy @aura.events accounts should have been migrated, so login fails."""
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@aura.events", "password": "admin123"}, timeout=10)
    assert r.status_code in (400, 401, 404)


# ---------------------------------------------------------------------------
# Regression: browse + event detail still work
# ---------------------------------------------------------------------------
def test_events_listing():
    r = requests.get(f"{API}/api/events", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert isinstance(items, list) and len(items) > 0


def test_event_detail_endpoint():
    r = requests.get(f"{API}/api/events", timeout=15)
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    eid = items[0]["event_id"]
    r2 = requests.get(f"{API}/api/events/{eid}", timeout=15)
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["event_id"] == eid
    # Verify organizer name was backfilled
    assert "AURA" not in (detail.get("organizer_name") or "")


# ---------------------------------------------------------------------------
# Email templates — no AURA brand text
# ---------------------------------------------------------------------------
def test_email_templates_rebranded():
    """All rendered email HTML should say 'Allsale Events' and not 'AURA'."""
    from emails import (
        _t_booking_confirmation, _t_organizer_event_approved,
        _t_organizer_payout_issued, _t_hold_expired, _t_refund_issued,
        _t_waitlist_spot_opened,
    )

    samples = []
    try:
        _, html, _ = _t_booking_confirmation({
            "user_name": "X", "event_title": "T", "event_date": "2026-01-01",
            "venue": "V", "tier_name": "GA", "quantity": 1, "amount": 10.0,
            "currency": "usd", "booking_id": "bkg_x",
            "qr_data_url": "data:image/png;base64,xx",
        })
        samples.append(("booking_confirmation", html))
    except Exception as e:
        print("booking_confirmation render error:", e)
    try:
        _, html, _ = _t_organizer_event_approved({
            "organizer_name": "O", "event_title": "T",
        })
        samples.append(("event_approved", html))
    except Exception as e:
        print("event_approved render error:", e)
    try:
        _, html, _ = _t_organizer_payout_issued({
            "organizer_name": "O", "amount": 10.0, "currency": "usd",
            "period_label": "Jan", "event_count": 1,
        })
        samples.append(("payout_issued", html))
    except Exception as e:
        print("payout_issued render error:", e)
    try:
        _, html, _ = _t_hold_expired({
            "user_name": "X", "event_title": "T",
        })
        samples.append(("hold_expired", html))
    except Exception as e:
        print("hold_expired render error:", e)

    assert len(samples) >= 2, f"Too few email templates rendered: {[s[0] for s in samples]}"
    for name, html in samples:
        assert "Allsale" in html, f"Email '{name}' missing 'Allsale': {html[:300]}"
        # Strip URLs and attributes (object-storage 'aura-tickets' path is intentionally preserved)
        without_urls = re.sub(r'https?://[^\s"\']+', '', html)
        without_attrs = re.sub(r'(href|src|alt|action|class|id|style)=["\'][^"\']*["\']', '', without_urls)
        assert "AURA" not in without_attrs, f"Email '{name}' contains AURA brand text: {without_attrs[:500]}"
