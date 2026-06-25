"""Backend tests for admin-managed creator promo codes (iteration 22).

Covers:
  * POST /api/admin/events/{event_id}/creator-codes — create + duplicate + 400 + 404 + 403
  * GET  /api/admin/events/{event_id}/creator-codes — list with stats
  * DELETE /api/admin/events/{event_id}/creator-codes/{code_id} — deactivate
  * GET  /api/admin/creator-codes/users-search — autocomplete + validation
  * POST /api/discount-codes/validate — public validation finds admin-created code
  * Helper presence + unique index on creator_earnings (idempotency)
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PW = "admin123"
ORG_EMAIL = "orgtester@allsale.events"
ORG_PW = "orgtest123"
EVENT_ID = "evt_656b89734cd7"

# Track for cleanup
_created_code_ids: list[tuple[str, str]] = []  # (event_id, code_id)


def _login(email: str, pw: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token returned: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def org_token():
    return _login(ORG_EMAIL, ORG_PW)


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def org_h(org_token):
    return {"Authorization": f"Bearer {org_token}"}


@pytest.fixture(scope="module")
def unique_code():
    # 8 hex chars uppercase => valid CODE_RE
    return f"TST{uuid.uuid4().hex[:6].upper()}"


# ---------------------------------------------------------------------------
# Creation flow
# ---------------------------------------------------------------------------

def test_create_creator_code_success(admin_h, unique_code):
    body = {
        "code": unique_code,
        "creator_email": ORG_EMAIL,
        "kind": "percent",
        "value": 15,
        "commission_percent": 5,
        "max_uses": 50,
    }
    r = requests.post(f"{API}/admin/events/{EVENT_ID}/creator-codes", json=body, headers=admin_h, timeout=20)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    doc = r.json()
    assert doc["code"] == unique_code
    assert doc["kind"] == "percent"
    assert doc["value"] == 15
    assert doc["commission_percent"] == 5
    assert doc["max_uses"] == 50
    assert doc["active"] is True
    assert doc.get("creator_id"), f"creator_id missing: {doc}"
    assert doc["creator_email"] == ORG_EMAIL
    assert doc["event_id"] == EVENT_ID
    assert doc.get("code_id", "").startswith("dc_")
    _created_code_ids.append((EVENT_ID, doc["code_id"]))


def test_duplicate_creator_code_returns_409(admin_h, unique_code):
    body = {
        "code": unique_code,
        "creator_email": ORG_EMAIL,
        "kind": "percent",
        "value": 10,
    }
    r = requests.post(f"{API}/admin/events/{EVENT_ID}/creator-codes", json=body, headers=admin_h, timeout=20)
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"


@pytest.mark.parametrize("bad_code", ["ab", "a", "!!!", "AB!", "-AB"])
def test_invalid_code_format_returns_400(admin_h, bad_code):
    body = {"code": bad_code, "creator_email": ORG_EMAIL, "kind": "percent", "value": 10}
    r = requests.post(f"{API}/admin/events/{EVENT_ID}/creator-codes", json=body, headers=admin_h, timeout=15)
    assert r.status_code == 400, f"Expected 400 for {bad_code!r}, got {r.status_code}: {r.text}"


def test_missing_creator_returns_404(admin_h):
    body = {
        "code": f"NOC{uuid.uuid4().hex[:6].upper()}",
        "creator_email": "nobody@nowhere.test",
        "kind": "percent",
        "value": 10,
    }
    r = requests.post(f"{API}/admin/events/{EVENT_ID}/creator-codes", json=body, headers=admin_h, timeout=15)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_invalid_event_returns_404(admin_h):
    body = {
        "code": f"EVT{uuid.uuid4().hex[:6].upper()}",
        "creator_email": ORG_EMAIL,
        "kind": "percent",
        "value": 10,
    }
    r = requests.post(f"{API}/admin/events/evt_doesnotexist/creator-codes", json=body, headers=admin_h, timeout=15)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Non-admin 403
# ---------------------------------------------------------------------------

def test_non_admin_403_on_create(org_h):
    body = {"code": f"NOA{uuid.uuid4().hex[:6].upper()}", "creator_email": ORG_EMAIL, "kind": "percent", "value": 10}
    r = requests.post(f"{API}/admin/events/{EVENT_ID}/creator-codes", json=body, headers=org_h, timeout=15)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def test_non_admin_403_on_list(org_h):
    r = requests.get(f"{API}/admin/events/{EVENT_ID}/creator-codes", headers=org_h, timeout=15)
    assert r.status_code == 403


def test_non_admin_403_on_delete(org_h):
    r = requests.delete(f"{API}/admin/events/{EVENT_ID}/creator-codes/dc_doesntmatter", headers=org_h, timeout=15)
    assert r.status_code == 403


def test_non_admin_403_on_users_search(org_h):
    r = requests.get(f"{API}/admin/creator-codes/users-search?q=orgtester", headers=org_h, timeout=15)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_includes_created_code_with_stats(admin_h, unique_code):
    r = requests.get(f"{API}/admin/events/{EVENT_ID}/creator-codes", headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    found = next((c for c in body["items"] if c["code"] == unique_code), None)
    assert found, f"Newly created code not in list. Got codes: {[c['code'] for c in body['items']]}"
    # Stats fields with sane defaults for a fresh code.
    for k in ("paid_bookings", "revenue", "commission_credited", "commission_unpaid"):
        assert k in found, f"Missing stats field {k} in {found}"
    assert found["paid_bookings"] == 0
    assert found["revenue"] == 0
    assert found["commission_credited"] == 0
    assert found["commission_unpaid"] == 0


# ---------------------------------------------------------------------------
# Public validation finds admin-created code
# ---------------------------------------------------------------------------

def test_public_validate_finds_admin_created_code(unique_code):
    payload = {
        "code": unique_code,
        "event_id": EVENT_ID,
        "subtotal": 100.0,
        "quantity": 1,
    }
    r = requests.post(f"{API}/discount-codes/validate", json=payload, timeout=15)
    assert r.status_code == 200, f"Validation failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["code"] == unique_code
    assert data["kind"] == "percent"
    assert data["value"] == 15
    assert data["discount_amount"] == 15.0  # 15% of 100
    assert data["final_amount"] == 85.0


# ---------------------------------------------------------------------------
# Users autocomplete
# ---------------------------------------------------------------------------

def test_users_search_finds_orgtester(admin_h):
    r = requests.get(f"{API}/admin/creator-codes/users-search?q=orgtester", headers=admin_h, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    assert any(u.get("email") == ORG_EMAIL for u in items), f"orgtester not found in: {items}"


def test_users_search_min_length(admin_h):
    # min_length=2 → q="a" must be rejected (422 from FastAPI validation)
    r = requests.get(f"{API}/admin/creator-codes/users-search?q=a", headers=admin_h, timeout=15)
    assert r.status_code in (400, 422), f"Expected 400/422 for short q, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Deactivate + post-deactivate validation fails
# ---------------------------------------------------------------------------

def test_deactivate_creator_code_and_validation_fails(admin_h, unique_code):
    # Need to know code_id — pull from list
    r = requests.get(f"{API}/admin/events/{EVENT_ID}/creator-codes", headers=admin_h, timeout=15)
    items = r.json()["items"]
    target = next(c for c in items if c["code"] == unique_code)
    code_id = target["code_id"]

    r = requests.delete(f"{API}/admin/events/{EVENT_ID}/creator-codes/{code_id}", headers=admin_h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("deactivated") == code_id

    # Subsequent validation: must fail (404 inactive)
    payload = {"code": unique_code, "event_id": EVENT_ID, "subtotal": 100.0, "quantity": 1}
    r2 = requests.post(f"{API}/discount-codes/validate", json=payload, timeout=15)
    assert r2.status_code == 404, f"Validation should fail after deactivate, got {r2.status_code} {r2.text}"


def test_deactivate_missing_returns_404(admin_h):
    r = requests.delete(f"{API}/admin/events/{EVENT_ID}/creator-codes/dc_doesnotexist", headers=admin_h, timeout=15)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Helper presence + DB index idempotency
# ---------------------------------------------------------------------------

def test_record_creator_earning_helper_exists():
    from routers.creator_codes import record_creator_earning_for_booking
    assert callable(record_creator_earning_for_booking)


@pytest.mark.asyncio
async def test_creator_earnings_unique_index_present():
    import os as _os
    from motor.motor_asyncio import AsyncIOMotorClient

    # Read backend's .env (tests run from a different cwd)
    try:
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
    except Exception:
        pass
    mongo_url = _os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = _os.environ.get("DB_NAME") or "test_database"
    client = AsyncIOMotorClient(mongo_url)
    try:
        idx = await client[db_name].creator_earnings.index_information()
        assert "creator_booking_unique" in idx, f"Unique index missing. Found: {list(idx.keys())}"
        spec = idx["creator_booking_unique"]
        assert spec.get("unique") is True
        # Key list should be [(creator_id, 1), (booking_id, 1)]
        keys = spec.get("key", [])
        assert ("creator_id", 1) in keys
        assert ("booking_id", 1) in keys
    finally:
        client.close()
