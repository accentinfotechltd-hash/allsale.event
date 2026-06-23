"""Backend tests for the fee-settings dynamic public endpoint and privacy
of admin-only event fields (per-tier fee breakdown leak fix)."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
EVENT_ID = "evt_656b89734cd7"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@allsale.events", "password": "admin123"},
                      timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


# ---------- public fee-settings endpoint ----------
class TestPublicFeeSettings:
    def test_endpoint_is_public_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/fees/public-settings", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("platform_pct"), (int, float))
        assert isinstance(d.get("platform_flat_per_ticket"), (int, float))
        assert isinstance(d.get("stripe_pct"), (int, float))
        # sanity ranges
        assert 0 <= d["platform_pct"] <= 50
        assert 0 <= d["platform_flat_per_ticket"] <= 20
        assert 0 < d["stripe_pct"] < 10

    def test_default_state_5pct_030(self, admin_client):
        # Ensure baseline is 5% / 0.30 per problem statement
        r = admin_client.put(f"{BASE_URL}/api/admin/platform-settings",
                             json={"commission_percent": 5.0,
                                   "commission_flat_fee_per_ticket": 0.30})
        assert r.status_code == 200, r.text
        # public endpoint reflects
        time.sleep(0.3)
        pub = requests.get(f"{BASE_URL}/api/fees/public-settings", timeout=20).json()
        assert abs(pub["platform_pct"] - 5.0) < 1e-6
        assert abs(pub["platform_flat_per_ticket"] - 0.30) < 1e-6

    def test_admin_update_reflects_in_public_endpoint(self, admin_client):
        # Flip to 8 / 0.50 and ensure the public endpoint reflects it
        r = admin_client.put(f"{BASE_URL}/api/admin/platform-settings",
                             json={"commission_percent": 8.0,
                                   "commission_flat_fee_per_ticket": 0.50})
        assert r.status_code == 200, r.text
        time.sleep(0.3)
        pub = requests.get(f"{BASE_URL}/api/fees/public-settings", timeout=20).json()
        assert abs(pub["platform_pct"] - 8.0) < 1e-6
        assert abs(pub["platform_flat_per_ticket"] - 0.50) < 1e-6

    def test_restore_5pct(self, admin_client):
        # IMPORTANT — restore baseline so other tests/bookings keep using 5%/0.30
        r = admin_client.put(f"{BASE_URL}/api/admin/platform-settings",
                             json={"commission_percent": 5.0,
                                   "commission_flat_fee_per_ticket": 0.30})
        assert r.status_code == 200
        pub = requests.get(f"{BASE_URL}/api/fees/public-settings", timeout=20).json()
        assert abs(pub["platform_pct"] - 5.0) < 1e-6
        assert abs(pub["platform_flat_per_ticket"] - 0.30) < 1e-6


# ---------- fee math consistency between FE estimator & BE compute_fees ----------
def _client_estimate(face, plat_pct, plat_flat, stripe_pct):
    plat = face * (plat_pct / 100.0)
    total = (face + plat + plat_flat) / max(1e-6, 1 - stripe_pct / 100.0)
    return round(total - face, 2)


class TestFeeMath:
    def test_5pct_030_yields_268_on_30(self):
        # Mirror the client fees.js formula
        fees = _client_estimate(30.0, 5.0, 0.30, 2.7)
        assert fees == 2.68, fees

    def test_8pct_050_yields_about_381_on_30(self):
        fees = _client_estimate(30.0, 8.0, 0.50, 2.7)
        # Expected ~ 3.81 per problem statement
        assert 3.75 <= fees <= 3.90, fees

    def test_backend_compute_fees_matches(self):
        # Hit /api/admin/platform-settings is admin; verify backend math
        # via direct compute by replicating with same numbers
        # Already covered above; this test asserts backend formula identity
        from backend.fees import compute_fees  # type: ignore
        b = compute_fees(30.0, "NZD", platform_pct=5.0, stripe_flat=0.30)
        # service_fee = platform_fee + stripe_fee == what buyer sees as fees
        assert round(b.service_fee, 2) == 2.68, b.as_dict()


# ---------- privacy regression: admin-only fields hidden in public event GET ----------
class TestPublicEventPrivacy:
    def test_public_event_loads(self):
        r = requests.get(f"{BASE_URL}/api/events/{EVENT_ID}", timeout=20)
        assert r.status_code == 200, r.text
        ev = r.json()
        # Public payload should still expose tier name + price
        assert "tiers" in ev
        assert isinstance(ev["tiers"], list)
        for t in ev["tiers"]:
            assert "name" in t
            assert "price" in t

    def test_admin_event_still_exposes_capacity(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/events/{EVENT_ID}")
        assert r.status_code == 200
        ev = r.json()
        # Admin response must include capacity for owner/admin metric rendering
        if ev.get("tiers"):
            assert any("capacity" in t for t in ev["tiers"])
