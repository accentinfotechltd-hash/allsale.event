"""Tests for iteration 23: GET /api/influencer/my-codes, fee public settings,
avatar persistence on /influencer/enable, regression on existing influencer endpoints."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s, r.json()


@pytest.fixture(scope="module")
def org_session():
    s, data = _login("orgtester@allsale.events", "orgtest123")
    return s


@pytest.fixture(scope="module")
def fresh_attendee_session():
    email = f"TEST_attendee_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "testpass123"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pwd, "name": "Test Attendee"}, timeout=20)
    assert r.status_code in (200, 201), f"signup: {r.status_code} {r.text}"
    s = requests.Session()
    r2 = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r2.status_code == 200
    return s, email


# ----- fees -----
def test_fees_public_settings_no_auth():
    r = requests.get(f"{API}/fees/public-settings", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "platform_pct" in d
    assert "platform_flat_per_ticket" in d
    assert isinstance(d["platform_pct"], (int, float))
    assert isinstance(d["platform_flat_per_ticket"], (int, float))


# ----- my-codes for org tester (has 3 codes) -----
def test_my_codes_org_tester(org_session):
    r = org_session.get(f"{API}/influencer/my-codes", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d and "summary" in d
    items = d["items"]
    assert isinstance(items, list)
    assert len(items) >= 3, f"expected >=3 admin-assigned codes, got {len(items)}"
    expected_codes = {"AB", "TST585CF2", "QA_CHLOE15"}
    codes_present = {it["code"] for it in items}
    assert expected_codes.issubset(codes_present), f"missing codes: {expected_codes - codes_present}"
    # validate shape of first item
    sample = next(it for it in items if it["code"] in expected_codes)
    for f in ("code", "code_id", "kind", "value", "commission_percent", "active",
              "max_uses", "uses_count", "expires_at", "event",
              "paid_bookings", "tickets_sold", "revenue",
              "earnings_paid", "earnings_unpaid"):
        assert f in sample, f"field {f} missing in item"
    ev = sample.get("event") or {}
    if ev:
        for f in ("event_id", "title"):
            assert f in ev
    summary = d["summary"]
    for k in ("codes_total", "earnings_paid_total", "earnings_unpaid_total"):
        assert k in summary
    assert summary["codes_total"] == len(items)


def test_my_codes_fresh_user_empty(fresh_attendee_session):
    s, _ = fresh_attendee_session
    r = s.get(f"{API}/influencer/my-codes", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["items"] == []
    assert d["summary"]["codes_total"] == 0
    assert d["summary"]["earnings_paid_total"] == 0
    assert d["summary"]["earnings_unpaid_total"] == 0


# ----- avatar persistence -----
def test_influencer_enable_persists_avatar(fresh_attendee_session):
    s, _ = fresh_attendee_session
    avatar = f"https://example.com/test_{uuid.uuid4().hex[:6]}.jpg"
    payload = {
        "display_name": "Test Creator",
        "bio": "Avatar persistence test",
        "categories": ["music"],
        "avatar_url": avatar,
    }
    r = s.post(f"{API}/influencer/enable", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("avatar_url") == avatar

    # Verify GET reflects persistence
    r2 = s.get(f"{API}/influencer/me", timeout=20)
    assert r2.status_code == 200
    me = r2.json()
    assert me.get("enabled") is True
    assert me.get("avatar_url") == avatar


# ----- regression -----
def test_influencer_me_org(org_session):
    r = org_session.get(f"{API}/influencer/me", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("enabled") is True


def test_influencer_dashboard_org(org_session):
    r = org_session.get(f"{API}/influencer/dashboard", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "summary" in d and "campaigns" in d
    for k in ("total_clicks", "total_conversions", "conversion_rate_pct",
              "total_revenue_attributed", "total_commission_earned",
              "paid_out_total", "pending_payout"):
        assert k in d["summary"]


def test_admin_creator_codes_regression():
    s, _ = _login("admin@allsale.events", "admin123")
    r = s.get(f"{API}/admin/events/evt_656b89734cd7/creator-codes", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert isinstance(items, list)
    assert len(items) >= 1
