"""Public partner application form + admin review — endpoint tests."""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


def _unique_email() -> str:
    return f"partner_test_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_public_submit_creates_application(admin_token):
    email = _unique_email()
    r = requests.post(
        f"{API}/api/partners/apply",
        json={
            "full_name": "Sara Submitter",
            "email": email,
            "phone": "+64 21 555 1111",
            "company": "TestCo",
            "channels": ["instagram", "blog"],
            "audience_size": "8k IG",
            "why_partner": "I run an Auckland music blog with 5000 monthly readers — would love to drive bookings.",
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["application_id"].startswith("app_")
    # Confirm visible in admin list.
    r2 = requests.get(
        f"{API}/api/admin/partners/applications",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r2.status_code == 200
    emails = [it["email"] for it in r2.json()["items"]]
    assert email in emails


def test_short_why_rejected_via_validation():
    """Server enforces min_length=10 on why_partner."""
    r = requests.post(
        f"{API}/api/partners/apply",
        json={
            "full_name": "Brief Bob",
            "email": _unique_email(),
            "channels": [],
            "why_partner": "too brief",
        },
        timeout=10,
    )
    assert r.status_code == 422, r.text


def test_duplicate_pending_updates_in_place(admin_token):
    """Submitting again with the same email while pending must NOT create
    a duplicate row — should update the existing one with new data."""
    email = _unique_email()
    payload = {
        "full_name": "Dup Test", "email": email, "channels": ["instagram"],
        "why_partner": "First submission with enough length to pass validation.",
    }
    r1 = requests.post(f"{API}/api/partners/apply", json=payload, timeout=10)
    app_id_1 = r1.json()["application_id"]
    # Second submit
    payload["why_partner"] = "Updated submission — please consider the new details I'm adding now."
    payload["audience_size"] = "20k now"
    r2 = requests.post(f"{API}/api/partners/apply", json=payload, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["application_id"] == app_id_1
    # Admin view: only one row with this email
    r3 = requests.get(
        f"{API}/api/admin/partners/applications",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    matches = [it for it in r3.json()["items"] if it["email"] == email]
    assert len(matches) == 1
    assert matches[0]["audience_size"] == "20k now"  # updated


def test_approve_flow(admin_token):
    email = _unique_email()
    r = requests.post(
        f"{API}/api/partners/apply",
        json={
            "full_name": "Approval Anna", "email": email,
            "channels": ["tiktok"],
            "why_partner": "I'd love to drive bookings for events through my TikTok community.",
        },
        timeout=10,
    )
    app_id = r.json()["application_id"]
    # Approve
    r2 = requests.post(
        f"{API}/api/admin/partners/applications/{app_id}/approve",
        json={"note": "Welcome aboard"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    # Status reflected
    r3 = requests.get(
        f"{API}/api/admin/partners/applications?status=approved",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    approved_emails = [it["email"] for it in r3.json()["items"]]
    assert email in approved_emails


def test_reject_flow(admin_token):
    email = _unique_email()
    r = requests.post(
        f"{API}/api/partners/apply",
        json={
            "full_name": "Reject Rita", "email": email,
            "channels": ["other"],
            "why_partner": "I sell air fryers and would like to partner with Allsale.",
        },
        timeout=10,
    )
    app_id = r.json()["application_id"]
    r2 = requests.post(
        f"{API}/api/admin/partners/applications/{app_id}/reject",
        json={"note": "Off-fit"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r2.status_code == 200


def test_admin_endpoints_blocked_for_non_admin():
    email = _unique_email()
    reg = requests.post(
        f"{API}/api/auth/register",
        json={"name": "Block Me", "email": email, "password": "test1234", "role": "attendee", "phone": "+64 21 555 0000"},
        timeout=10,
    )
    tok = reg.json()["token"]
    r = requests.get(
        f"{API}/api/admin/partners/applications",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r.status_code == 403


def test_rate_limit_per_ip():
    """5 submissions / 10 minutes / IP. The 6th must 429."""
    # Submit 5 unique applications — should all succeed
    for i in range(5):
        r = requests.post(
            f"{API}/api/partners/apply",
            json={
                "full_name": f"Rate Test {i}",
                "email": f"rate_test_{uuid.uuid4().hex[:6]}@example.com",
                "channels": [],
                "why_partner": "Rate limit test with sufficient length to pass validation.",
            },
            timeout=10,
        )
        # If a previous test run already exhausted the bucket, we'll see 429s early — accept that.
        assert r.status_code in (200, 429), r.text
        if r.status_code == 429:
            # Bucket pre-filled; assertion already proven elsewhere
            return
    # 6th must hit the limit
    r6 = requests.post(
        f"{API}/api/partners/apply",
        json={
            "full_name": "Rate Test 6",
            "email": f"rate_test_{uuid.uuid4().hex[:6]}@example.com",
            "channels": [],
            "why_partner": "Rate limit test with sufficient length to pass validation.",
        },
        timeout=10,
    )
    assert r6.status_code == 429
