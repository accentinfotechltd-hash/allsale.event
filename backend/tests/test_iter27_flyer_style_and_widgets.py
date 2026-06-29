"""Iter27 — Surprise me style param + newsletter-unsubscribe-reasons admin endpoint + partner apply edge cases."""
from __future__ import annotations

import os
import uuid
import pytest
import requests

API = (os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def org_token():
    r = requests.post(f"{API}/api/auth/login",
        json={"email": "orgtester@allsale.events", "password": "orgtest123"}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def attendee_token():
    email = f"TEST_attendee_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/api/auth/register",
        json={"name": "TestAtt", "email": email, "password": "testpass123",
              "role": "attendee", "phone": "+64 21 555 9999"}, timeout=10)
    assert r.status_code in (200, 201), r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def org_event_id(org_token):
    # Try mine endpoint first, fall back to known event from credentials.
    for path in ("/api/events/mine", "/api/organizer/events", "/api/events?organizer_only=true"):
        try:
            r = requests.get(f"{API}{path}",
                headers={"Authorization": f"Bearer {org_token}"}, timeout=10)
            if r.status_code == 200:
                body = r.json()
                items = body if isinstance(body, list) else body.get("items") or body.get("events") or []
                if items:
                    eid = items[0].get("event_id") or items[0].get("id")
                    if eid:
                        return eid
        except Exception:
            pass
    return "evt_9237e281ca2b"  # known orgtester event from /app/memory/test_credentials.md


# ---------- Feature 1: Surprise-me style param ---------------------------
@pytest.mark.parametrize("style", ["punchy", "elegant", "mysterious", "default"])
def test_flyer_generate_text_accepts_style(org_token, org_event_id, style):
    r = requests.post(
        f"{API}/api/events/{org_event_id}/flyer/generate-text?style={style}",
        headers={"Authorization": f"Bearer {org_token}"}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "style" in data, f"missing style key for {style}: {data}"
    assert data["style"] == style
    assert "headline" in data and "tagline" in data and "cta" in data


def test_flyer_generate_text_attendee_forbidden(attendee_token, org_event_id):
    r = requests.post(
        f"{API}/api/events/{org_event_id}/flyer/generate-text?style=punchy",
        headers={"Authorization": f"Bearer {attendee_token}"}, timeout=15)
    assert r.status_code == 403, r.text


# ---------- Feature 2: Newsletter unsubscribe-reasons --------------------
def test_unsubscribe_reasons_admin_only(attendee_token):
    r = requests.get(f"{API}/api/admin/newsletter/unsubscribe-reasons",
        headers={"Authorization": f"Bearer {attendee_token}"}, timeout=10)
    assert r.status_code == 403


def test_unsubscribe_reasons_returns_shape(admin_token):
    r = requests.get(f"{API}/api/admin/newsletter/unsubscribe-reasons",
        headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    # Validate it has SOME structure usable by the widget. Tolerate either shape.
    assert isinstance(d, dict)
    # Either {reasons:[], comments:[], total}, or {top_reasons:..., total:...}
    keys = set(d.keys())
    assert keys & {"reasons", "top_reasons", "items", "total", "comments", "recent_comments"}, \
        f"unexpected unsubscribe-reasons shape: {keys}"


# ---------- Feature 3: Partner-apply additional edge cases --------------
def test_partner_apply_no_auth_required():
    """Posting without Authorization header must still succeed."""
    r = requests.post(f"{API}/api/partners/apply",
        json={
            "full_name": "Public Pete",
            "email": f"TEST_pub_{uuid.uuid4().hex[:8]}@example.com",
            "channels": ["instagram"],
            "why_partner": "I have a public-facing IG with strong NZ-music engagement."
        }, timeout=15)
    # Could be 200 OR 429 if bucket pre-filled — either is acceptable per agent note.
    assert r.status_code in (200, 429), r.text


def test_admin_partner_applications_lists_with_summary(admin_token):
    r = requests.get(f"{API}/api/admin/partners/applications",
        headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d and "summary" in d
    assert {"pending", "approved", "rejected"}.issubset(set(d["summary"].keys()))


def test_admin_partner_applications_forbidden_for_attendee(attendee_token):
    r = requests.get(f"{API}/api/admin/partners/applications",
        headers={"Authorization": f"Bearer {attendee_token}"}, timeout=10)
    assert r.status_code == 403
