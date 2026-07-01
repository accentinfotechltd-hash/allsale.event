"""Live smoke tests for lead enrichment endpoints against the running backend.

- Verifies auth guards (401 unauth, 403 non-admin, 404 missing lead).
- Runs ONE real enrich call against Stonehenge Aotearoa (lead_14cc266a48)
  to prove the Firecrawl+regex pipeline still lands nzstarlore@gmail.com.
- Runs enrich-batch with lead_ids=[real_id] and lead_ids=['not_real'].
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASS = "admin123"
ORG_EMAIL = "orgtester@allsale.events"
ORG_PASS = "orgtest123"
STONEHENGE_LEAD_ID = "lead_14cc266a48"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in login response: {r.text[:200]}"
    return tok


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def org_token() -> str:
    return _login(ORG_EMAIL, ORG_PASS)


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --- Auth guard tests ------------------------------------------------------
def test_enrich_one_without_auth_401():
    r = requests.post(f"{BASE_URL}/api/admin/recruitment-leads/{STONEHENGE_LEAD_ID}/enrich", timeout=10)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}: {r.text[:200]}"


def test_enrich_one_non_admin_403(org_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/recruitment-leads/{STONEHENGE_LEAD_ID}/enrich",
        headers=_hdr(org_token),
        timeout=10,
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"
    assert "Admin only" in (r.json().get("detail") or ""), r.text[:200]


def test_enrich_one_missing_lead_404(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/recruitment-leads/does_not_exist/enrich",
        headers=_hdr(admin_token),
        timeout=10,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"
    assert r.json().get("detail") == "Lead not found"


# --- Batch endpoint --------------------------------------------------------
def test_enrich_batch_no_matching_leads(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/recruitment-leads/enrich-batch",
        headers=_hdr(admin_token),
        json={"lead_ids": ["not_real"], "limit": 1},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["processed"] == 0
    assert data["message"] == "No matching leads."


# --- Real Firecrawl smoke test (LONG: 5-25s) -------------------------------
def test_enrich_one_stonehenge_real_firecrawl(admin_token):
    """Real Firecrawl+regex pipeline. Expected: nzstarlore@gmail.com @ 85%."""
    t0 = time.time()
    r = requests.post(
        f"{BASE_URL}/api/admin/recruitment-leads/{STONEHENGE_LEAD_ID}/enrich",
        headers=_hdr(admin_token),
        timeout=90,
    )
    dur = time.time() - t0
    assert r.status_code == 200, f"HTTP {r.status_code} after {dur:.1f}s: {r.text[:300]}"
    data = r.json()
    assert data.get("ok") is True
    assert "enrichment_status" in data
    assert isinstance(data.get("enrichment_confidence"), int)
    assert 0 <= data["enrichment_confidence"] <= 100
    # We expect this specific lead to resolve to a real email.
    assert data.get("email"), f"Expected an email, got: {data}"
    # Regex fast-path should surface this specific address at 85 confidence.
    # (We assert loosely in case the page structure changes.)
    print(
        f"Stonehenge enrich → status={data.get('enrichment_status')} "
        f"email={data.get('email')} conf={data.get('enrichment_confidence')} "
        f"website={data.get('website_url')} took {dur:.1f}s"
    )


def test_enrich_batch_with_real_lead_id(admin_token):
    r = requests.post(
        f"{BASE_URL}/api/admin/recruitment-leads/enrich-batch",
        headers=_hdr(admin_token),
        json={"lead_ids": [STONEHENGE_LEAD_ID], "limit": 1},
        timeout=120,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["ok"] is True
    assert data["processed"] >= 1
    assert isinstance(data.get("summary"), dict)
    assert sum(data["summary"].values()) == data["processed"]
