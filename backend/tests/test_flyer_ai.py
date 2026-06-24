"""Backend tests for AI flyer text generator (POST /api/events/{event_id}/flyer/generate-text).

Covers:
  - Happy path (admin/owner) returns 200 with non-empty headline/tagline/cta
  - Auth: unauthenticated => 401; non-owner non-admin => 403
  - Robustness: 10x successive calls — at least 9 must return 200 with valid fields
  - Quality: enforced field length limits (headline<=60, tagline<=140, cta<=30)
  - No raw LiteLLM/OpenAI error string leaks back to caller
  - (Optional, run separately) Graceful fallback with invalid EMERGENT_LLM_KEY
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
EVENT_ID = "evt_656b89734cd7"

ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASSWORD = "admin123"
ORG_EMAIL = "orgtester@allsale.events"
ORG_PASSWORD = "orgtest123"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api_client, email, password):
    r = api_client.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token in login response: {data}"
    return token


@pytest.fixture(scope="module")
def admin_token(api_client):
    return _login(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def org_token(api_client):
    return _login(api_client, ORG_EMAIL, ORG_PASSWORD)


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Helpers ----------

def _assert_valid_payload(data):
    assert isinstance(data, dict), f"expected dict, got {type(data)}"
    for f in ("headline", "tagline", "cta"):
        assert f in data, f"missing field {f} in {data}"
        assert isinstance(data[f], str), f"{f} not str: {type(data[f])}"
        assert data[f].strip(), f"{f} is empty"
    assert len(data["headline"]) <= 60, f"headline too long: {len(data['headline'])}"
    assert len(data["tagline"]) <= 140, f"tagline too long: {len(data['tagline'])}"
    assert len(data["cta"]) <= 30, f"cta too long: {len(data['cta'])}"
    # No raw LLM error should ever bubble up
    blob = (data.get("headline", "") + " " + data.get("tagline", "") + " " + data.get("cta", "")).lower()
    for bad in ("litellm", "authenticationerror", "openaiexception", "invalid api key"):
        assert bad not in blob, f"raw provider error leaked into response: {data}"


# ---------- Tests ----------

# Auth tests
def test_unauthenticated_returns_401(api_client):
    r = api_client.post(f"{BASE_URL}/api/events/{EVENT_ID}/flyer/generate-text")
    assert r.status_code in (401, 403), f"expected 401/403 for unauth, got {r.status_code} {r.text[:200]}"


def test_non_owner_non_admin_returns_403(api_client, org_token):
    """orgtester is NOT the owner of evt_656b89734cd7 (owned by demo-organizer) and not admin."""
    r = api_client.post(
        f"{BASE_URL}/api/events/{EVENT_ID}/flyer/generate-text",
        headers=_auth_headers(org_token),
    )
    # orgtester might not own this event; we expect 403
    assert r.status_code == 403, f"expected 403 for non-owner, got {r.status_code} {r.text[:200]}"


# Happy path
def test_admin_happy_path_returns_valid_payload(api_client, admin_token):
    r = api_client.post(
        f"{BASE_URL}/api/events/{EVENT_ID}/flyer/generate-text",
        headers=_auth_headers(admin_token),
        timeout=60,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text[:300]}"
    data = r.json()
    _assert_valid_payload(data)
    # And should NOT bubble the old error string
    assert "litellm" not in r.text.lower()


# Robustness 10x
def test_robustness_10x_at_least_9_succeed(api_client, admin_token):
    successes = 0
    failures = []
    for i in range(10):
        try:
            r = api_client.post(
                f"{BASE_URL}/api/events/{EVENT_ID}/flyer/generate-text",
                headers=_auth_headers(admin_token),
                timeout=90,
            )
            if r.status_code == 200:
                data = r.json()
                _assert_valid_payload(data)
                # Verify no leaked provider error in body
                assert "litellm" not in r.text.lower()
                assert "authenticationerror" not in r.text.lower()
                successes += 1
            else:
                failures.append((i, r.status_code, r.text[:200]))
        except Exception as exc:
            failures.append((i, "exc", str(exc)[:200]))
    print(f"\nROBUSTNESS: {successes}/10 succeeded. Failures: {failures}")
    assert successes >= 9, f"only {successes}/10 succeeded. failures={failures}"


# Quality (re-check on a fresh call, fields normalized)
def test_quality_fields_normalized(api_client, admin_token):
    r = api_client.post(
        f"{BASE_URL}/api/events/{EVENT_ID}/flyer/generate-text",
        headers=_auth_headers(admin_token),
        timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    _assert_valid_payload(data)
    # headline should be uppercase-friendly per system prompt: at least mostly uppercase OR template uppercased
    # The router uppercases fallback titles; AI is told ALL CAPS is optional. Just verify length cap held.
    assert len(data["headline"]) <= 60


def test_emergent_llm_key_format(api_client):
    """Sanity: key in env is sk-emergent-* (we can't read backend env from here, so this is informational only)."""
    # Just print; nothing to assert against the running server.
    key = os.environ.get("EMERGENT_LLM_KEY", "")
    print(f"Local EMERGENT_LLM_KEY visibility: {bool(key)} startswith_sk_emergent={key.startswith('sk-emergent-') if key else 'n/a'}")
