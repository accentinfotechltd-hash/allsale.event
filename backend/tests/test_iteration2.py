"""Iteration 2 tests: uploads, aisles, atomic seat reservation, seed aisles, checkout flow.
Focuses on new functionality added on top of iteration 1.
"""
import os
import io
import uuid
import pytest
import requests
import concurrent.futures

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aura.events", "password": "admin123"}
ORGANIZER = {"email": "organizer@aura.events", "password": "organizer123"}
ATTENDEE = {"email": "attendee@aura.events", "password": "attendee123"}


def _login(c):
    r = requests.post(f"{API}/auth/login", json=c, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# Minimal 1x1 PNG (valid PNG signature) for upload tests
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3sx\xd8\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session")
def organizer_token():
    return _login(ORGANIZER)


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def attendee_token():
    return _login(ATTENDEE)


@pytest.fixture(scope="session")
def events():
    r = requests.get(f"{API}/events", timeout=20)
    assert r.status_code == 200
    return r.json()


# ------------------- Uploads -------------------
class TestUploads:
    def test_upload_requires_auth(self):
        files = {"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, timeout=20)
        assert r.status_code == 401

    def test_upload_forbidden_attendee(self, attendee_token):
        files = {"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(attendee_token), timeout=20)
        assert r.status_code == 403

    def test_upload_bad_extension(self, organizer_token):
        files = {"file": ("evil.exe", io.BytesIO(b"MZ\x00\x00"), "application/octet-stream")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 400

    def test_upload_organizer_success_and_serve(self, organizer_token):
        files = {"file": ("cover.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # Iter3: object storage migration — url is /api/files/<storage_path>
        assert body["url"].startswith("/api/files/"), body
        assert body["path"].endswith(".png")
        # File served
        g = requests.get(f"{BASE_URL}{body['url']}", timeout=20)
        assert g.status_code == 200
        ct = g.headers.get("content-type", "")
        assert "image" in ct.lower() or "png" in ct.lower(), f"Unexpected content-type: {ct}"
        assert g.content[:8] == PNG_BYTES[:8]
        pytest._uploaded_url = body["url"]

    def test_upload_admin_success(self, admin_token):
        files = {"file": ("admin.jpg", io.BytesIO(PNG_BYTES), "image/jpeg")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(admin_token), timeout=20)
        assert r.status_code == 200


# ------------------- Events new fields (aisles + seat_map_image_url) -------------------
class TestEventNewFields:
    def test_seeded_roast_has_16_aisles(self, events):
        roast = next((e for e in events if "Roast" in e.get("title", "")), None)
        assert roast, "Seeded 'Stand-Up Saturday: The Roast' event missing"
        r = requests.get(f"{API}/events/{roast['event_id']}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("has_seatmap") is True
        assert isinstance(data.get("aisles"), list)
        assert len(data["aisles"]) == 16, f"Expected 16 aisles, got {len(data['aisles'])}"
        assert "booked_seats" in data and "held_seats" in data

    def test_seeded_hamilton_has_20_aisles(self, events):
        ham = next((e for e in events if "Hamilton" in e.get("title", "")), None)
        assert ham, "Seeded 'Hamilton' event missing"
        r = requests.get(f"{API}/events/{ham['event_id']}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert len(data.get("aisles", [])) == 20, f"Expected 20 aisles, got {len(data.get('aisles', []))}"

    def test_create_event_with_aisles_and_backdrop(self, organizer_token):
        backdrop = getattr(pytest, "_uploaded_url", "/api/uploads/test.png")
        payload = {
            "title": f"TEST_seatmap_{uuid.uuid4().hex[:6]}",
            "description": "test", "category": "theater",
            "venue": "v", "city": "Auckland",
            "date": "2030-06-01T00:00:00",
            "image_url": backdrop,
            "has_seatmap": True,
            "seat_rows": 4, "seat_cols": 4, "seat_price": 25.0,
            "aisles": ["A-2", "B-2"],
            "seat_map_image_url": backdrop,
            "tiers": [],
        }
        r = requests.post(f"{API}/events", json=payload, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["aisles"] == ["A-2", "B-2"]
        assert body["seat_map_image_url"] == backdrop


# ------------------- Atomic seat hold (concurrency + aisle rejection) -------------------
class TestAtomicSeatHold:
    @pytest.fixture(scope="class")
    def seatmap_event(self, events):
        sm = [e for e in events if e.get("has_seatmap")]
        assert sm
        return sm[0]

    def test_hold_aisle_rejected(self, attendee_token, seatmap_event):
        # seeded Roast has aisles at col 6 and 7 for each row -> "A-6"
        aisle_seat = seatmap_event.get("aisles", ["A-6"])[0]
        payload = {"event_id": seatmap_event["event_id"], "seats": [aisle_seat]}
        r = requests.post(f"{API}/bookings/hold", json=payload, headers=_h(attendee_token), timeout=20)
        assert r.status_code == 400, r.text
        assert "aisle" in r.text.lower()

    def test_two_concurrent_holds_one_wins(self, attendee_token, seatmap_event):
        seat = f"Q-{uuid.uuid4().hex[:4]}"
        payload = {"event_id": seatmap_event["event_id"], "seats": [seat]}

        def post():
            return requests.post(f"{API}/bookings/hold", json=payload, headers=_h(attendee_token), timeout=20)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as exe:
            fs = [exe.submit(post) for _ in range(2)]
            results = [f.result() for f in fs]

        codes = sorted([r.status_code for r in results])
        # Atomic compound index must guarantee exactly one wins
        assert codes == [200, 409], f"Expected [200,409], got {codes}: {[r.text for r in results]}"
        # The 409 message must indicate seat taken
        loser = [r for r in results if r.status_code == 409][0]
        assert "just got taken" in loser.text.lower() or "taken" in loser.text.lower()

    def test_duplicate_key_via_db(self, attendee_token, seatmap_event):
        """Try inserting same seat twice sequentially (after first held) — must 409."""
        seat = f"X-{uuid.uuid4().hex[:4]}"
        payload = {"event_id": seatmap_event["event_id"], "seats": [seat]}
        r1 = requests.post(f"{API}/bookings/hold", json=payload, headers=_h(attendee_token), timeout=20)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{API}/bookings/hold", json=payload, headers=_h(attendee_token), timeout=20)
        assert r2.status_code == 409


# ------------------- Stripe checkout end-to-end (iter1 regression) -------------------
class TestCheckoutResilient:
    def test_checkout_session_and_status_no_500(self, attendee_token, events):
        tier_evs = [e for e in events if not e.get("has_seatmap") and e.get("tiers")]
        ev = tier_evs[0]
        hp = {"event_id": ev["event_id"], "tier_name": ev["tiers"][0]["name"], "quantity": 1}
        h = requests.post(f"{API}/bookings/hold", json=hp, headers=_h(attendee_token), timeout=20)
        assert h.status_code == 200, h.text
        bid = h.json()["booking_id"]
        cs = requests.post(
            f"{API}/checkout/session",
            json={"booking_id": bid, "origin_url": BASE_URL},
            headers=_h(attendee_token),
            timeout=30,
        )
        assert cs.status_code == 200, cs.text
        sid = cs.json()["session_id"]
        st = requests.get(f"{API}/checkout/status/{sid}", headers=_h(attendee_token), timeout=30)
        # Must NOT 500 even if Stripe test-mode fails
        assert st.status_code == 200, f"Expected 200, got {st.status_code}: {st.text}"
        assert "payment_status" in st.json()
