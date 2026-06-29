"""Admin revenue headline endpoint — month-over-month KPI for /admin/revenue page."""
from __future__ import annotations

import os
import requests
import pytest

API = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_headline_shape(admin_token):
    r = requests.get(
        f"{API}/api/admin/revenue/headline",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("current_month", "previous_month", "delta_percent", "today_fees", "today_count"):
        assert k in body, f"missing key {k} in response"
    # Bucket shapes
    for bucket in ("current_month", "previous_month"):
        b = body[bucket]
        for k in ("gross", "platform_fees", "stripe_fees", "count", "currency", "label", "start", "end"):
            assert k in b, f"{bucket} missing {k}"
        assert isinstance(b["platform_fees"], (int, float))
        assert isinstance(b["count"], int)


def test_headline_labels_are_month_names(admin_token):
    r = requests.get(
        f"{API}/api/admin/revenue/headline",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    body = r.json()
    # "June 2026", "May 2026", etc. — must contain a 4-digit year + capitalised month name
    import re
    pat = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$")
    assert pat.match(body["current_month"]["label"]), body["current_month"]["label"]
    assert pat.match(body["previous_month"]["label"]), body["previous_month"]["label"]


def test_headline_delta_null_when_previous_zero(admin_token):
    """delta_percent must be None (not 0, not inf) when previous month had no revenue."""
    r = requests.get(
        f"{API}/api/admin/revenue/headline",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    body = r.json()
    if body["previous_month"]["platform_fees"] == 0:
        assert body["delta_percent"] is None
    else:
        assert isinstance(body["delta_percent"], (int, float))


def test_headline_403_for_non_admin():
    """Non-admin tokens must be rejected."""
    import uuid
    email = f"hero_gate_{uuid.uuid4().hex[:6]}@example.com"
    reg = requests.post(
        f"{API}/api/auth/register",
        json={"name": "Hero Gate", "email": email, "password": "test1234", "role": "attendee", "phone": "+64 21 555 6666"},
        timeout=10,
    )
    tok = reg.json()["token"]
    r = requests.get(
        f"{API}/api/admin/revenue/headline",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r.status_code == 403, r.text
