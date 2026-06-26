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


# ----- iter-24: optional-discount creator codes -----
def _admin_session():
    s, _ = _login("admin@allsale.events", "admin123")
    return s


# Use a stable event known to exist in dev: DHARPAKAD — Auckland (07 June Show)
_DHARPAKAD_EVENT_ID = "evt_396bf50315b9"


def _delete_test_code(admin_s, code_str):
    """Best-effort cleanup so the unique-code constraint doesn't trip subsequent runs."""
    r = admin_s.get(f"{API}/admin/events/{_DHARPAKAD_EVENT_ID}/creator-codes", timeout=15)
    if r.status_code != 200:
        return
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    for c in items:
        if c.get("code") == code_str:
            admin_s.delete(f"{API}/admin/events/{_DHARPAKAD_EVENT_ID}/creator-codes/{c['code_id']}", timeout=15)


def test_creator_code_commission_only_no_discount():
    admin = _admin_session()
    code_str = f"AUTOTEST_C{uuid.uuid4().hex[:4].upper()}"
    _delete_test_code(admin, code_str)
    payload = {
        "code": code_str,
        "creator_email": "orgtester@allsale.events",
        "kind": "percent",
        "commission_percent": 8,
        # NB: NO `value` field — pure commission code
    }
    r = admin.post(f"{API}/admin/events/{_DHARPAKAD_EVENT_ID}/creator-codes", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["value"] == 0.0
    assert doc["commission_percent"] == 8.0
    _delete_test_code(admin, code_str)


def test_creator_code_blocks_no_discount_and_no_commission():
    admin = _admin_session()
    code_str = f"AUTOTEST_N{uuid.uuid4().hex[:4].upper()}"
    payload = {
        "code": code_str,
        "creator_email": "orgtester@allsale.events",
        "kind": "percent",
    }
    r = admin.post(f"{API}/admin/events/{_DHARPAKAD_EVENT_ID}/creator-codes", json=payload, timeout=20)
    assert r.status_code == 400
    assert "code with neither has no effect" in r.json().get("detail", "").lower() or \
           "discount value" in r.json().get("detail", "").lower()


def test_creator_code_discount_only_no_commission():
    admin = _admin_session()
    code_str = f"AUTOTEST_D{uuid.uuid4().hex[:4].upper()}"
    _delete_test_code(admin, code_str)
    payload = {
        "code": code_str,
        "creator_email": "orgtester@allsale.events",
        "kind": "percent",
        "value": 12,
    }
    r = admin.post(f"{API}/admin/events/{_DHARPAKAD_EVENT_ID}/creator-codes", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["value"] == 12.0
    assert doc.get("commission_percent") in (None, 0, 0.0)
    _delete_test_code(admin, code_str)


# ----- iter-24b: organizer-scoped creator-code endpoints -----
# orgtester is both an organizer and an enrolled creator; they own at least one event.
def _org_owned_event_id(org_s):
    r = org_s.get(f"{API}/organizer/events", timeout=15)
    assert r.status_code == 200, r.text
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert items, "no events owned by orgtester — seed fixture mismatch"
    return items[0]["event_id"]


def test_organizer_can_list_creator_codes_on_own_event(org_session):
    eid = _org_owned_event_id(org_session)
    r = org_session.get(f"{API}/organizer/events/{eid}/creator-codes", timeout=20)
    assert r.status_code == 200, r.text
    assert "items" in r.json()


def test_organizer_can_search_creators(org_session):
    r = org_session.get(f"{API}/organizer/creator-codes/users-search?q=org", timeout=15)
    assert r.status_code == 200, r.text
    assert "items" in r.json()


def test_organizer_can_crud_creator_code_on_own_event(org_session):
    eid = _org_owned_event_id(org_session)
    code_str = f"ORGTST_{uuid.uuid4().hex[:5].upper()}"
    # Create
    create = org_session.post(
        f"{API}/organizer/events/{eid}/creator-codes",
        json={"code": code_str, "creator_email": "orgtester@allsale.events",
              "kind": "percent", "value": 15, "commission_percent": 7},
        timeout=20,
    )
    assert create.status_code == 200, create.text
    code_id = create.json()["code_id"]
    # Edit
    edit = org_session.patch(
        f"{API}/organizer/events/{eid}/creator-codes/{code_id}",
        json={"value": 22, "commission_percent": 10},
        timeout=20,
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["value"] == 22.0
    assert edit.json()["commission_percent"] == 10.0
    # Deactivate
    delr = org_session.delete(f"{API}/organizer/events/{eid}/creator-codes/{code_id}", timeout=15)
    assert delr.status_code == 200, delr.text
    assert delr.json().get("deactivated") == code_id


def test_organizer_blocked_from_other_organizers_event(org_session):
    """orgtester must NOT be able to list/manage creator codes on an event they don't own."""
    admin_s, _ = _login("admin@allsale.events", "admin123")
    all_events = admin_s.get(f"{API}/admin/events?limit=200", timeout=20).json()
    items = all_events if isinstance(all_events, list) else all_events.get("items", [])
    me_user_id = "user_2492358084d3"  # orgtester
    foreign = next((it for it in items if it.get("organizer_id") and it["organizer_id"] != me_user_id), None)
    if not foreign:
        pytest.skip("no foreign event to test cross-owner protection")
    r = org_session.get(f"{API}/organizer/events/{foreign['event_id']}/creator-codes", timeout=15)
    assert r.status_code == 403, r.text
