"""Tests for endDate field on Event JSON-LD + backend create/PATCH support.

Verifies the recent fix that adds `end_date` (Optional[str]) to EventIn,
threads it through create / PATCH and into the public GET response.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ORG_EMAIL = "orgtester@allsale.events"
ORG_PASS = "orgtest123"
ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASS = "admin123"

EXISTING_EVENT_NO_END = "evt_656b89734cd7"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def org_token():
    return _login(ORG_EMAIL, ORG_PASS)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def attendee_token():
    # Register a unique attendee
    import time
    email = f"TEST_attendee_{int(time.time())}@allsale.events"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Test Attendee", "email": email, "password": "testpass123", "role": "attendee"
    }, timeout=15)
    if r.status_code not in (200, 201):
        pytest.skip(f"could not register attendee: {r.status_code} {r.text}")
    return r.json().get("token") or r.json().get("access_token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Existing event GET (no end_date in DB) ----------
def test_existing_event_get_no_end_date():
    """Existing event evt_656b89734cd7 returns successfully — end_date may be null."""
    r = requests.get(f"{API}/events/{EXISTING_EVENT_NO_END}", timeout=15)
    assert r.status_code == 200, f"unexpected {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data.get("date"), "event must have a start date"
    # end_date may legitimately be null/missing for this event — frontend derives +3h
    assert data.get("end_date") in (None, "") or isinstance(data.get("end_date"), str)


# ---------- Backend CREATE accepts end_date ----------
def test_create_event_with_end_date_persists(org_token):
    payload = {
        "title": "TEST_ENDDATE_Event_Explicit",
        "description": "Testing explicit endDate persistence",
        "category": "Music",
        "venue": "Test Venue",
        "city": "Auckland",
        "country": "NZ",
        "date": "2027-08-15T18:00:00Z",
        "end_date": "2027-08-15T23:00:00Z",  # +5h
        "image_url": "https://example.com/a.jpg",
        "currency": "NZD",
        "tiers": [{"name": "GA", "price": 50, "capacity": 100}],
    }
    r = requests.post(f"{API}/events", json=payload, headers=_auth(org_token), timeout=20)
    assert r.status_code in (200, 201), f"create failed {r.status_code}: {r.text[:400]}"
    created = r.json()
    event_id = created.get("event_id")
    assert event_id, f"no event_id in response: {created}"
    # Echo back
    assert created.get("end_date") == "2027-08-15T23:00:00Z", f"end_date echo wrong: {created.get('end_date')}"
    # GET to verify persistence
    g = requests.get(f"{API}/events/{event_id}", timeout=15)
    assert g.status_code == 200
    assert g.json().get("end_date") == "2027-08-15T23:00:00Z"
    # stash for downstream
    pytest.event_with_end = event_id


# ---------- Regression: optional ----------
def test_create_event_without_end_date(org_token):
    payload = {
        "title": "TEST_ENDDATE_Event_NoEnd",
        "description": "Testing default endDate derivation",
        "category": "Music",
        "venue": "Test Venue",
        "city": "Auckland",
        "country": "NZ",
        "date": "2027-09-10T19:00:00Z",
        "image_url": "https://example.com/b.jpg",
        "currency": "NZD",
        "tiers": [{"name": "GA", "price": 30, "capacity": 50}],
    }
    r = requests.post(f"{API}/events", json=payload, headers=_auth(org_token), timeout=20)
    assert r.status_code in (200, 201), f"create no-end failed {r.status_code}: {r.text[:400]}"
    created = r.json()
    event_id = created.get("event_id")
    assert event_id
    # end_date should be null or missing
    assert created.get("end_date") in (None, ""), f"expected null end_date, got {created.get('end_date')}"
    pytest.event_without_end = event_id


# ---------- PATCH end_date ----------
def test_patch_end_date_as_owner(org_token):
    event_id = getattr(pytest, "event_without_end", None)
    if not event_id:
        pytest.skip("dependency event missing")
    r = requests.patch(
        f"{API}/events/{event_id}",
        json={"end_date": "2027-09-10T22:30:00Z"},
        headers=_auth(org_token),
        timeout=15,
    )
    assert r.status_code == 200, f"patch failed {r.status_code}: {r.text[:300]}"
    g = requests.get(f"{API}/events/{event_id}", timeout=15)
    assert g.status_code == 200
    assert g.json().get("end_date") == "2027-09-10T22:30:00Z"


# ---------- PATCH auth: attendee cannot edit ----------
def test_patch_end_date_as_attendee_forbidden(attendee_token):
    event_id = getattr(pytest, "event_without_end", None) or EXISTING_EVENT_NO_END
    r = requests.patch(
        f"{API}/events/{event_id}",
        json={"end_date": "2099-01-01T00:00:00Z"},
        headers=_auth(attendee_token),
        timeout=15,
    )
    # attendee role often returns 403; some apps return 401. Accept both.
    assert r.status_code in (401, 403), f"expected forbidden, got {r.status_code}: {r.text[:200]}"


# ---------- Admin can PATCH end_date on any event ----------
def test_patch_end_date_as_admin(admin_token):
    event_id = getattr(pytest, "event_with_end", None)
    if not event_id:
        pytest.skip("dependency event missing")
    r = requests.patch(
        f"{API}/events/{event_id}",
        json={"end_date": "2027-08-16T01:00:00Z"},
        headers=_auth(admin_token),
        timeout=15,
    )
    assert r.status_code == 200, f"admin patch failed {r.status_code}: {r.text[:300]}"
    g = requests.get(f"{API}/events/{event_id}", timeout=15)
    assert g.status_code == 200
    assert g.json().get("end_date") == "2027-08-16T01:00:00Z"
