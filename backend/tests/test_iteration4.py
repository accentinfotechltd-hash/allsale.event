"""Iteration 4 tests: routers refactor + per-event drilldown analytics + CSV export + ETag conditional GET.

Covers:
- /api/organizer/events/{id}/analytics — schema (event/totals/tiers/days/hours[24]), AuthZ (403/404)
- /api/organizer/events/{id}/attendees.csv — content-type, Content-Disposition, header + rows
- /api/files/{path} — ETag header present, If-None-Match → 304 empty body
- Verify seeded demo organizer paid bookings on evt_5dba915db2be (non-zero values, 3 tiers)
"""
import os
import io
import csv as csv_mod
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@allsale.events", "password": "admin123"}
ORGANIZER = {"email": "organizer@allsale.events", "password": "organizer123"}
ATTENDEE = {"email": "attendee@allsale.events", "password": "attendee123"}

DEMO_EVENT_ID = "evt_5dba915db2be"  # Midnight Echoes — has paid bookings

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3sx\xd8\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _login(c):
    r = requests.post(f"{API}/auth/login", json=c, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def organizer_token():
    return _login(ORGANIZER)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def attendee_token():
    return _login(ATTENDEE)


# ------------------- Per-event drilldown analytics -------------------
class TestEventAnalyticsDrilldown:
    def test_schema_and_values_for_demo_event(self, organizer_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", headers=_h(organizer_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()

        # Top-level keys
        for k in ("event", "totals", "tiers", "days", "hours"):
            assert k in data, f"missing key {k}"

        # Event meta
        ev = data["event"]
        for k in ("event_id", "title", "venue", "city", "date", "category"):
            assert k in ev, f"missing event.{k}"
        assert ev["event_id"] == DEMO_EVENT_ID

        # Totals schema + non-zero (seeded paid bookings)
        t = data["totals"]
        for k in ("revenue", "tickets_sold", "capacity", "sell_through_pct", "bookings_count", "unique_attendees"):
            assert k in t, f"missing totals.{k}"
        assert t["revenue"] > 0, f"expected revenue > 0 for seeded demo event, got {t}"
        assert t["tickets_sold"] > 0
        assert t["bookings_count"] >= 1
        assert t["unique_attendees"] >= 1
        assert isinstance(t["sell_through_pct"], (int, float))
        assert 0 <= t["sell_through_pct"] <= 100

        # Tiers: should be array with 3 tiers expected (Early Bird, General, VIP)
        assert isinstance(data["tiers"], list)
        assert len(data["tiers"]) >= 1
        for row in data["tiers"]:
            for k in ("tier", "tickets", "revenue"):
                assert k in row

        # Days: array of {date,tickets,revenue}
        assert isinstance(data["days"], list)
        assert len(data["days"]) >= 1
        for row in data["days"]:
            for k in ("date", "tickets", "revenue"):
                assert k in row

        # Hours: must be exactly 24 entries with hour 0..23
        assert isinstance(data["hours"], list)
        assert len(data["hours"]) == 24
        for i, row in enumerate(data["hours"]):
            assert row["hour"] == i
            assert "tickets" in row

    def test_admin_can_view_any_event(self, admin_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200

    def test_404_for_unknown_event(self, organizer_token):
        r = requests.get(f"{API}/organizer/events/evt_does_not_exist/analytics", headers=_h(organizer_token), timeout=20)
        assert r.status_code == 404

    def test_403_for_attendee(self, attendee_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", headers=_h(attendee_token), timeout=20)
        assert r.status_code == 403

    def test_401_no_auth(self):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", timeout=20)
        assert r.status_code == 401

    def test_403_for_non_owner_organizer(self, organizer_token, admin_token):
        """Create an event as admin, then a different organizer should NOT be able to view its drilldown.

        We make the admin be the 'organizer_id' of the created event. The demo organizer (different user_id)
        should get 403.
        """
        payload = {
            "title": f"TEST_iter4_authz_{os.urandom(3).hex()}",
            "description": "authz test",
            "category": "music",
            "venue": "v", "city": "Auckland",
            "date": "2031-01-01T20:00:00",
            "image_url": "/api/files/placeholder.png",
            "has_seatmap": False,
            "tiers": [{"name": "GA", "price": 10, "capacity": 5}],
        }
        c = requests.post(f"{API}/events", json=payload, headers=_h(admin_token), timeout=20)
        assert c.status_code == 200, c.text
        eid = c.json()["event_id"]
        r = requests.get(f"{API}/organizer/events/{eid}/analytics", headers=_h(organizer_token), timeout=20)
        assert r.status_code == 403, r.text


# ------------------- CSV export -------------------
class TestAttendeesCsv:
    def test_csv_headers_and_content(self, organizer_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/attendees.csv", headers=_h(organizer_token), timeout=20)
        assert r.status_code == 200, r.text
        # content-type
        ct = r.headers.get("Content-Type", "")
        assert "text/csv" in ct.lower(), ct
        # disposition
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd.lower(), cd
        assert ".csv" in cd.lower()
        # body parse
        rows = list(csv_mod.reader(io.StringIO(r.text)))
        assert len(rows) >= 2, "header + at least 1 data row expected"
        header = rows[0]
        assert "Booking ID" in header
        assert "Email" in header
        # Data row(s)
        data_rows = rows[1:]
        for row in data_rows:
            assert len(row) == len(header)

    def test_admin_can_export(self, admin_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/attendees.csv", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("Content-Type", "").lower()

    def test_csv_404_unknown_event(self, organizer_token):
        r = requests.get(f"{API}/organizer/events/evt_nope/attendees.csv", headers=_h(organizer_token), timeout=20)
        assert r.status_code == 404

    def test_csv_403_attendee(self, attendee_token):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/attendees.csv", headers=_h(attendee_token), timeout=20)
        assert r.status_code == 403


# ------------------- ETag conditional GET on /api/files/{path} -------------------
class TestFilesETag:
    def test_etag_and_304(self, organizer_token):
        # Fresh upload
        files = {"file": ("etag.png", io.BytesIO(PNG_BYTES), "image/png")}
        u = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert u.status_code == 200
        url = u.json()["url"]

        # First GET — must return 200 + ETag
        r1 = requests.get(f"{BASE_URL}{url}", timeout=20)
        assert r1.status_code == 200, r1.text
        etag = r1.headers.get("ETag")
        assert etag, "ETag header missing"

        # Second GET with If-None-Match should be 304 empty body
        r2 = requests.get(f"{BASE_URL}{url}", headers={"If-None-Match": etag}, timeout=20)
        assert r2.status_code == 304, f"expected 304 got {r2.status_code}, body={r2.text[:200]}"
        # body must be empty
        assert len(r2.content) == 0
        # ETag echoed back
        assert r2.headers.get("ETag") == etag

    def test_mismatched_etag_returns_200(self, organizer_token):
        files = {"file": ("etag2.png", io.BytesIO(PNG_BYTES), "image/png")}
        u = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        url = u.json()["url"]
        r = requests.get(f"{BASE_URL}{url}", headers={"If-None-Match": '"deadbeef"'}, timeout=20)
        assert r.status_code == 200
        assert len(r.content) > 0


# ------------------- Refactor: routers structure smoke -------------------
class TestRouterStructureSmoke:
    """All previously-working endpoints still respond under the slim server.py."""

    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert "AURA" in r.text

    def test_events_list(self):
        r = requests.get(f"{API}/events", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_events_featured(self):
        r = requests.get(f"{API}/events/featured", timeout=10)
        assert r.status_code == 200

    def test_categories(self):
        r = requests.get(f"{API}/events/categories", timeout=10)
        assert r.status_code == 200

    def test_auth_me(self, organizer_token):
        r = requests.get(f"{API}/auth/me", headers=_h(organizer_token), timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == ORGANIZER["email"]

    def test_organizer_events(self, organizer_token):
        r = requests.get(f"{API}/organizer/events", headers=_h(organizer_token), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_organizer_aggregate_analytics(self, organizer_token):
        r = requests.get(f"{API}/organizer/analytics", headers=_h(organizer_token), timeout=10)
        assert r.status_code == 200
        body = r.json()
        for k in ("total_revenue", "tickets_sold", "events_count", "per_event", "series"):
            assert k in body

    def test_admin_events_list(self, admin_token):
        r = requests.get(f"{API}/admin/events", headers=_h(admin_token), timeout=10)
        assert r.status_code == 200
