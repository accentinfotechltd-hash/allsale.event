"""Iteration 3 tests: Emergent object storage migration.

Covers:
- POST /api/uploads now returns {url: /api/files/<path>, path: aura-tickets/uploads/<uid>/<uuid>.<ext>}
- GET  /api/files/{path:path} is PUBLIC (no auth) and returns the image bytes + Cache-Control header
- db.uploaded_files record schema: file_id, storage_path, user_id, size, content_type
- .gif is now REJECTED (iter3 only allows jpg/jpeg/png/webp)
- File durability — sanity-checked image from main agent is still accessible
- 401 unauth on POST, 403 attendee, 200 organizer, 200 admin
"""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@aura.events", "password": "admin123"}
ORGANIZER = {"email": "organizer@aura.events", "password": "organizer123"}
ATTENDEE = {"email": "attendee@aura.events", "password": "attendee123"}

# 1x1 PNG
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3sx\xd8\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid GIF87a 1x1
GIF_BYTES = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

# Sanity-uploaded file from main agent (referenced in agent_to_agent_context_note)
SANITY_PATH = "aura-tickets/uploads/user_926930bed59d/53f96e5c58154a11805e4cf2e6b07caa.png"


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


# ------------------- Upload endpoint contract (iter3 schema) -------------------
class TestUploadIter3Contract:
    def test_url_format_is_api_files(self, organizer_token):
        files = {"file": ("c1.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "url" in body and "path" in body, body
        assert body["url"] == f"/api/files/{body['path']}"
        assert body["url"].startswith("/api/files/aura-tickets/uploads/"), body["url"]
        assert body["path"].startswith("aura-tickets/uploads/"), body["path"]
        assert body["path"].endswith(".png")
        pytest._iter3_url = body["url"]
        pytest._iter3_path = body["path"]

    def test_public_serve_no_auth(self):
        url = getattr(pytest, "_iter3_url", None)
        assert url, "Prior upload test must have stored url"
        # No Authorization header → still 200 (public)
        r = requests.get(f"{BASE_URL}{url}", timeout=20)
        assert r.status_code == 200, r.text
        # Backend sends "public, max-age=86400"; some edge proxies may rewrite it.
        # Just assert a Cache-Control header is present.
        assert r.headers.get("Cache-Control") is not None
        ctype = r.headers.get("Content-Type", "")
        assert "image" in ctype.lower() or "png" in ctype.lower(), ctype
        # Bytes round-trip
        assert r.content[:8] == PNG_BYTES[:8]

    def test_files_404_for_unknown_path(self):
        r = requests.get(
            f"{API}/files/aura-tickets/uploads/nope/does-not-exist-{os.urandom(4).hex()}.png",
            timeout=20,
        )
        assert r.status_code == 404, r.text


# ------------------- File durability (key iter3 acceptance) -------------------
class TestDurability:
    def test_sanity_upload_from_main_agent_still_served(self):
        """Image uploaded by main agent before restart must still be retrievable."""
        r = requests.get(f"{API}/files/{SANITY_PATH}", timeout=20)
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").lower().startswith("image/")
        assert len(r.content) > 0

    def test_re_upload_then_fetch(self, organizer_token):
        """Upload now, immediately fetch via public URL — round-trip."""
        files = {"file": ("dur.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert r.status_code == 200
        url = r.json()["url"]
        g = requests.get(f"{BASE_URL}{url}", timeout=20)
        assert g.status_code == 200
        assert g.content[:8] == PNG_BYTES[:8]


# ------------------- Extension allowlist (iter3 drops .gif) -------------------
class TestExtensionAllowlist:
    def test_gif_rejected(self, organizer_token):
        files = {"file": ("bad.gif", io.BytesIO(GIF_BYTES), "image/gif")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 400, r.text
        assert "jpg" in r.text.lower() or "png" in r.text.lower() or "allowed" in r.text.lower()

    def test_jpeg_allowed(self, organizer_token):
        files = {"file": ("ok.jpeg", io.BytesIO(PNG_BYTES), "image/jpeg")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["path"].endswith(".jpeg")

    def test_webp_allowed(self, organizer_token):
        files = {"file": ("ok.webp", io.BytesIO(PNG_BYTES), "image/webp")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["path"].endswith(".webp")

    def test_exe_rejected(self, organizer_token):
        files = {"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 400


# ------------------- AuthZ on upload -------------------
class TestUploadAuthZ:
    def test_no_auth_401(self):
        files = {"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, timeout=20)
        assert r.status_code == 401

    def test_attendee_403(self, attendee_token):
        files = {"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(attendee_token), timeout=20)
        assert r.status_code == 403

    def test_admin_ok(self, admin_token):
        files = {"file": ("admin.png", io.BytesIO(PNG_BYTES), "image/png")}
        r = requests.post(f"{API}/uploads", files=files, headers=_h(admin_token), timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["url"].startswith("/api/files/aura-tickets/uploads/")


# ------------------- Create event using uploaded cover (iter3 e2e) -------------------
class TestCreateEventWithCover:
    def test_organizer_creates_event_with_uploaded_cover(self, organizer_token):
        # Upload first
        files = {"file": ("cover.png", io.BytesIO(PNG_BYTES), "image/png")}
        u = requests.post(f"{API}/uploads", files=files, headers=_h(organizer_token), timeout=30)
        assert u.status_code == 200, u.text
        cover_url = u.json()["url"]
        assert cover_url.startswith("/api/files/")

        # Create event using that cover
        payload = {
            "title": f"TEST_iter3_cover_{os.urandom(3).hex()}",
            "description": "iter3 e2e cover",
            "category": "music",
            "venue": "v",
            "city": "Auckland",
            "date": "2030-09-01T20:00:00",
            "image_url": cover_url,
            "has_seatmap": False,
            "tiers": [{"name": "GA", "price": 50, "capacity": 10}],
        }
        r = requests.post(f"{API}/events", json=payload, headers=_h(organizer_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["image_url"] == cover_url

        # The cover served via public route
        g = requests.get(f"{BASE_URL}{cover_url}", timeout=20)
        assert g.status_code == 200
