"""Iteration 8 tests — On-site QR check-in.

Covers:
- POST /api/organizer/checkin with qr_payload + idempotency
- POST /api/organizer/checkin with booking_id (manual entry)
- Validation: invalid QR, different event, unpaid booking, non-existent booking
- AuthZ: non-organizer-owner 403; non-organizer role 403
- GET /api/organizer/events/{id}/checkin-stats
- POST /api/organizer/events/{id}/checkin/{bid}/undo
- GET /api/organizer/events/{id}/attendance-report.csv
"""
import os
import csv
import io
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL

ADMIN = {"email": "admin@allsale.events", "password": "admin123"}
ORG = {"email": "organizer@allsale.events", "password": "organizer123"}
ATT = {"email": "attendee@allsale.events", "password": "attendee123"}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mongo = MongoClient(MONGO_URL)[DB_NAME]


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user_id"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_auth():
    t, uid = _login(ADMIN)
    return {"token": t, "user_id": uid}


@pytest.fixture(scope="module")
def org_auth():
    t, uid = _login(ORG)
    return {"token": t, "user_id": uid}


@pytest.fixture(scope="module")
def att_auth():
    t, uid = _login(ATT)
    return {"token": t, "user_id": uid}


@pytest.fixture(scope="module")
def organizer_event(org_auth):
    """Pick any tier-based event owned by the demo organizer."""
    r = requests.get(f"{BASE_URL}/api/organizer/events", headers=_h(org_auth["token"]), timeout=15)
    assert r.status_code == 200, r.text
    events = [e for e in r.json() if not e.get("has_seatmap") and (e.get("tiers") or [])]
    assert events, "Need at least one tier-based organizer event"
    return events[0]


@pytest.fixture(scope="module")
def other_organizer_event(org_auth):
    """A *different* event also owned by demo org for cross-event tests."""
    r = requests.get(f"{BASE_URL}/api/organizer/events", headers=_h(org_auth["token"]), timeout=15)
    events = [e for e in r.json() if not e.get("has_seatmap") and (e.get("tiers") or [])]
    return events[1] if len(events) > 1 else None


def _create_paid_booking(att_token, event):
    """Hold a single ticket then mark it paid via mongo."""
    tier = event["tiers"][0]
    r = requests.post(
        f"{BASE_URL}/api/bookings/hold",
        json={"event_id": event["event_id"], "tier_name": tier["name"], "quantity": 1},
        headers=_h(att_token), timeout=15,
    )
    assert r.status_code == 200, r.text
    bid = r.json()["booking_id"]
    _mongo.bookings.update_one(
        {"booking_id": bid},
        {"$set": {"status": "paid", "paid_at": "2026-01-01T00:00:00+00:00"},
         "$unset": {"checked_in": "", "checked_in_at": "", "checked_in_by": ""}},
    )
    return bid


def _create_pending_booking(att_token, event):
    tier = event["tiers"][0]
    r = requests.post(
        f"{BASE_URL}/api/bookings/hold",
        json={"event_id": event["event_id"], "tier_name": tier["name"], "quantity": 1},
        headers=_h(att_token), timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["booking_id"]


# ============ Check-in core ============
class TestCheckinCore:
    def test_checkin_with_qr_payload_marks_paid(self, org_auth, att_auth, organizer_event):
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": f"AURA|{bid}|x|y"},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["already_checked_in"] is False
        assert data["booking"]["booking_id"] == bid
        assert data["booking"]["checked_in_at"]
        # DB verification
        b = _mongo.bookings.find_one({"booking_id": bid}, {"_id": 0})
        assert b["checked_in"] is True
        assert b["checked_in_by"] == org_auth["user_id"]

    def test_checkin_idempotent_second_call(self, org_auth, att_auth, organizer_event):
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        payload = {"event_id": organizer_event["event_id"], "qr_payload": f"AURA|{bid}"}
        r1 = requests.post(f"{BASE_URL}/api/organizer/checkin", json=payload, headers=_h(org_auth["token"]), timeout=15)
        assert r1.status_code == 200
        t1 = r1.json()["booking"]["checked_in_at"]
        r2 = requests.post(f"{BASE_URL}/api/organizer/checkin", json=payload, headers=_h(org_auth["token"]), timeout=15)
        assert r2.status_code == 200
        assert r2.json()["already_checked_in"] is True
        # checked_in_at unchanged
        assert r2.json()["booking"]["checked_in_at"] == t1

    def test_checkin_with_booking_id_direct(self, org_auth, att_auth, organizer_event):
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "booking_id": bid},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["already_checked_in"] is False
        assert r.json()["booking"]["booking_id"] == bid


# ============ Validation errors ============
class TestCheckinValidation:
    def test_invalid_qr_string_400(self, org_auth, organizer_event):
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": "NOTAQR"},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 400
        assert "Invalid QR" in r.json()["detail"]

    def test_empty_qr_and_no_booking_id_400(self, org_auth, organizer_event):
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": ""},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_different_event_400(self, org_auth, att_auth, organizer_event, other_organizer_event):
        if not other_organizer_event:
            pytest.skip("Need 2 organizer events for cross-event test")
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        # Try check-in at OTHER event
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": other_organizer_event["event_id"], "qr_payload": f"AURA|{bid}"},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "different event" in r.json()["detail"].lower()

    def test_pending_unpaid_400(self, org_auth, att_auth, organizer_event):
        bid = _create_pending_booking(att_auth["token"], organizer_event)
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": f"AURA|{bid}"},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 400
        assert "pending" in r.json()["detail"].lower()

    def test_non_existent_booking_404(self, org_auth, organizer_event):
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": "AURA|bkg_doesnotexist123"},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 404


# ============ AuthZ ============
class TestCheckinAuthZ:
    def test_attendee_role_403(self, att_auth, organizer_event):
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": "AURA|bkg_x"},
            headers=_h(att_auth["token"]), timeout=15,
        )
        assert r.status_code == 403

    def test_other_organizer_403(self, organizer_event):
        # Create a NEW organizer who does not own this event
        email = f"test_{uuid.uuid4().hex[:8]}@aura.example.com"
        r = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"name": "TEST other org", "email": email, "password": "Pass123!", "role": "organizer"},
            timeout=15,
        )
        assert r.status_code == 200
        token = r.json()["token"]
        r2 = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "qr_payload": "AURA|bkg_x"},
            headers=_h(token), timeout=15,
        )
        assert r2.status_code == 403


# ============ Stats ============
class TestCheckinStats:
    def test_stats_shape(self, org_auth, att_auth, organizer_event):
        # Ensure at least one fresh check-in exists
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "booking_id": bid},
            headers=_h(org_auth["token"]), timeout=15,
        )
        r = requests.get(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/checkin-stats",
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        for k in ("total_bookings", "checked_in_count", "no_shows_count", "total_tickets", "percent", "recent"):
            assert k in d, f"Missing {k}"
        assert d["total_bookings"] >= 1
        assert d["checked_in_count"] >= 1
        assert d["no_shows_count"] == d["total_bookings"] - d["checked_in_count"]
        assert isinstance(d["recent"], list)
        assert len(d["recent"]) <= 20
        # Recent should be sorted DESC by checked_in_at
        if len(d["recent"]) >= 2:
            assert d["recent"][0]["checked_in_at"] >= d["recent"][1]["checked_in_at"]
        # Our just-checked-in booking should appear in recent
        assert any(rcv["booking_id"] == bid for rcv in d["recent"])

    def test_stats_non_owner_403(self, att_auth, organizer_event):
        r = requests.get(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/checkin-stats",
            headers=_h(att_auth["token"]), timeout=15,
        )
        assert r.status_code == 403


# ============ Undo ============
class TestCheckinUndo:
    def test_undo_reverses_checkin(self, org_auth, att_auth, organizer_event):
        bid = _create_paid_booking(att_auth["token"], organizer_event)
        # check in
        r = requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "booking_id": bid},
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        # undo
        r = requests.post(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/checkin/{bid}/undo",
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        b = _mongo.bookings.find_one({"booking_id": bid}, {"_id": 0})
        assert b["checked_in"] is False
        assert "checked_in_at" not in b
        assert "checked_in_by" not in b

    def test_undo_non_owner_403(self, att_auth, organizer_event):
        r = requests.post(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/checkin/bkg_x/undo",
            headers=_h(att_auth["token"]), timeout=15,
        )
        assert r.status_code == 403


# ============ Attendance report CSV ============
class TestAttendanceReport:
    def test_csv_columns_and_sort_order(self, org_auth, att_auth, organizer_event):
        # Create one attended + one no-show
        b_attended = _create_paid_booking(att_auth["token"], organizer_event)
        b_noshow = _create_paid_booking(att_auth["token"], organizer_event)
        requests.post(
            f"{BASE_URL}/api/organizer/checkin",
            json={"event_id": organizer_event["event_id"], "booking_id": b_attended},
            headers=_h(org_auth["token"]), timeout=15,
        )
        r = requests.get(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/attendance-report.csv",
            headers=_h(org_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == [
            "Status", "Name", "Email", "Booking ID", "Tier / Seats",
            "Quantity", "Amount Paid", "Checked In At", "Discount Code",
        ]
        data_rows = rows[1:]
        statuses = [r[0] for r in data_rows]
        # Attended come before no-shows
        first_noshow = statuses.index("NO-SHOW") if "NO-SHOW" in statuses else len(statuses)
        last_attended = max((i for i, s in enumerate(statuses) if s == "ATTENDED"), default=-1)
        assert last_attended < first_noshow, "ATTENDED rows must precede NO-SHOW rows"
        # Both bookings present
        bids_in_csv = {r[3] for r in data_rows}
        assert b_attended in bids_in_csv
        assert b_noshow in bids_in_csv

    def test_report_non_owner_403(self, att_auth, organizer_event):
        r = requests.get(
            f"{BASE_URL}/api/organizer/events/{organizer_event['event_id']}/attendance-report.csv",
            headers=_h(att_auth["token"]), timeout=15,
        )
        assert r.status_code == 403
