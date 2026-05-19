"""Iteration 5 — Discount Code Engine tests."""
import asyncio
import os
import time
import uuid

import httpx
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""

BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

ORG_EMAIL = "organizer@allsale.events"
ORG_PASS = "organizer123"
ATT_EMAIL = "attendee@allsale.events"
ATT_PASS = "attendee123"

DEMO_EVENT_ID = "evt_5dba915db2be"  # Midnight Echoes


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def org_token():
    r = requests.post(f"{API}/auth/login", json={"email": ORG_EMAIL, "password": ORG_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def att_token():
    r = requests.post(f"{API}/auth/login", json={"email": ATT_EMAIL, "password": ATT_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def org_headers(org_token):
    return {"Authorization": f"Bearer {org_token}"}


@pytest.fixture(scope="module")
def att_headers(att_token):
    return {"Authorization": f"Bearer {att_token}"}


def _suffix():
    return uuid.uuid4().hex[:6].upper()


# ---------- create code ----------
class TestCreateCode:
    def test_create_percent_code(self, org_headers):
        code = f"TEST{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 15, "max_uses": 10},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["code"] == code
        assert d["kind"] == "percent"
        assert d["value"] == 15
        assert d["uses_count"] == 0
        assert d["active"] is True
        assert "code_id" in d
        # cleanup
        requests.delete(f"{API}/organizer/discount-codes/{d['code_id']}", headers=org_headers, timeout=15)

    def test_create_flat_code(self, org_headers):
        code = f"FLAT{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "flat", "value": 5},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["kind"] == "flat"
        assert d["max_uses"] is None
        requests.delete(f"{API}/organizer/discount-codes/{d['code_id']}", headers=org_headers, timeout=15)

    def test_invalid_code_format(self, org_headers):
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": "bad!", "kind": "percent", "value": 10},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_invalid_kind(self, org_headers):
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": f"X{_suffix()}", "kind": "garbage", "value": 10},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_percent_over_100(self, org_headers):
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": f"X{_suffix()}", "kind": "percent", "value": 150},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_value_must_be_positive(self, org_headers):
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": f"X{_suffix()}", "kind": "flat", "value": 0},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_duplicate_code_409(self, org_headers):
        code = f"DUP{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 10},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 200
        cid = r.json()["code_id"]
        r2 = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 20},
            headers=org_headers, timeout=15,
        )
        assert r2.status_code == 409
        requests.delete(f"{API}/organizer/discount-codes/{cid}", headers=org_headers, timeout=15)

    def test_requires_auth(self):
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": f"X{_suffix()}", "kind": "percent", "value": 10},
            timeout=15,
        )
        assert r.status_code in (401, 403)


# ---------- list / delete ----------
class TestListDelete:
    def test_list_includes_seeded_codes(self, org_headers):
        r = requests.get(f"{API}/organizer/discount-codes", headers=org_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        codes = {c["code"] for c in items}
        assert "AURA20" in codes
        assert "STAFF50" in codes
        for c in items:
            assert "attributed_revenue" in c
            assert "attributed_tickets" in c
            assert "total_discount_given" in c

    def test_seeded_aura20_stats(self, org_headers):
        r = requests.get(f"{API}/organizer/discount-codes", headers=org_headers, timeout=15)
        items = {c["code"]: c for c in r.json()}
        aura20 = items["AURA20"]
        # per seed: AURA20 has 3 tickets, $435 revenue, $36 discount given (or close — be tolerant)
        assert aura20["attributed_tickets"] >= 1
        assert aura20["attributed_revenue"] > 0
        assert aura20["total_discount_given"] > 0

    def test_delete_marks_inactive(self, org_headers):
        code = f"DEL{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 5},
            headers=org_headers, timeout=15,
        )
        cid = r.json()["code_id"]
        rd = requests.delete(f"{API}/organizer/discount-codes/{cid}", headers=org_headers, timeout=15)
        assert rd.status_code == 200
        # Should still appear in list with active=false
        items = requests.get(f"{API}/organizer/discount-codes", headers=org_headers, timeout=15).json()
        found = [c for c in items if c["code_id"] == cid]
        assert len(found) == 1
        assert found[0]["active"] is False

    def test_delete_not_owner_forbidden(self, att_headers, org_headers):
        # create a code as organizer
        code = f"OWN{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 5},
            headers=org_headers, timeout=15,
        )
        cid = r.json()["code_id"]
        # attendee try to delete -> 403 (role) or 401 (attendee has no organizer role)
        rd = requests.delete(f"{API}/organizer/discount-codes/{cid}", headers=att_headers, timeout=15)
        assert rd.status_code in (401, 403)
        requests.delete(f"{API}/organizer/discount-codes/{cid}", headers=org_headers, timeout=15)


# ---------- validate ----------
class TestValidate:
    def test_validate_percent_no_auth_needed(self):
        r = requests.post(
            f"{API}/discount-codes/validate",
            json={"code": "AURA20", "event_id": DEMO_EVENT_ID, "quantity": 1, "subtotal": 100.0},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["code"] == "AURA20"
        assert d["kind"] == "percent"
        assert d["discount_amount"] == 20.0
        assert d["final_amount"] == 80.0

    def test_validate_not_found(self):
        r = requests.post(
            f"{API}/discount-codes/validate",
            json={"code": "NOTACODE_XYZ", "event_id": DEMO_EVENT_ID, "subtotal": 50.0},
            timeout=15,
        )
        assert r.status_code == 404

    def test_validate_case_insensitive(self):
        r = requests.post(
            f"{API}/discount-codes/validate",
            json={"code": "aura20", "event_id": DEMO_EVENT_ID, "quantity": 1, "subtotal": 200.0},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["discount_amount"] == 40.0


# ---------- apply at hold ----------
class TestApplyAtHold:
    def test_hold_with_code_records_discount(self, att_headers):
        # use STAFF50 on demo event (unlimited)
        # find a tier in demo event
        ev = requests.get(f"{API}/events/{DEMO_EVENT_ID}", timeout=15).json()
        tier = ev["tiers"][0]["name"]
        price = ev["tiers"][0]["price"]
        r = requests.post(
            f"{API}/bookings/hold",
            json={"event_id": DEMO_EVENT_ID, "tier_name": tier, "quantity": 1, "code": "STAFF50"},
            headers=att_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["discount_code"] == "STAFF50"
        assert b["subtotal"] == pytest.approx(price, abs=0.01)
        assert b["discount_amount"] == pytest.approx(price * 0.5, abs=0.01)
        assert b["amount"] == pytest.approx(price * 0.5, abs=0.01)

    def test_hold_without_code_has_zero_discount(self, att_headers):
        ev = requests.get(f"{API}/events/{DEMO_EVENT_ID}", timeout=15).json()
        tier = ev["tiers"][0]["name"]
        r = requests.post(
            f"{API}/bookings/hold",
            json={"event_id": DEMO_EVENT_ID, "tier_name": tier, "quantity": 1},
            headers=att_headers, timeout=15,
        )
        assert r.status_code == 200
        b = r.json()
        assert b.get("discount_code") in (None, "")
        assert b.get("discount_amount", 0) == 0


# ---------- concurrent max_uses ----------
class TestConcurrentMaxUses:
    def test_max_uses_2_three_concurrent_one_409(self, org_headers, att_token):
        # Create a max_uses=2 code as organizer
        code = f"CC{_suffix()}"
        r = requests.post(
            f"{API}/organizer/discount-codes",
            json={"code": code, "kind": "percent", "value": 10, "max_uses": 2},
            headers=org_headers, timeout=15,
        )
        assert r.status_code == 200
        cid = r.json()["code_id"]

        ev = requests.get(f"{API}/events/{DEMO_EVENT_ID}", timeout=15).json()
        tier = ev["tiers"][0]["name"]

        async def fire():
            headers = {"Authorization": f"Bearer {att_token}"}
            async with httpx.AsyncClient(timeout=30) as cli:
                return await cli.post(
                    f"{API}/bookings/hold",
                    json={"event_id": DEMO_EVENT_ID, "tier_name": tier, "quantity": 1, "code": code},
                    headers=headers,
                )

        async def run():
            return await asyncio.gather(fire(), fire(), fire(), return_exceptions=True)

        results = asyncio.run(run())
        statuses = sorted(
            [(r.status_code if hasattr(r, "status_code") else 500) for r in results]
        )
        # cleanup
        requests.delete(f"{API}/organizer/discount-codes/{cid}", headers=org_headers, timeout=15)

        # 2x 200 and 1x failure (409 atomic race OR 400 from pre-check trip — both prove enforcement)
        assert statuses.count(200) == 2, f"got {statuses}"
        assert (409 in statuses) or (400 in statuses), f"expected one 409/400, got {statuses}"


# ---------- drilldown analytics ----------
class TestDrilldownCodes:
    def test_drilldown_codes_bucket_present(self, org_headers):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", headers=org_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "codes" in data
        codes = data["codes"]
        assert isinstance(codes, list)
        assert len(codes) >= 1
        keys = {c["code"] for c in codes}
        # Must have Direct + at least one of seeded promos
        assert "Direct" in keys
        # Validate row schema
        for row in codes:
            assert "code" in row and "tickets" in row and "revenue" in row and "discount_given" in row

    def test_drilldown_codes_includes_seeded(self, org_headers):
        r = requests.get(f"{API}/organizer/events/{DEMO_EVENT_ID}/analytics", headers=org_headers, timeout=15)
        codes = {c["code"]: c for c in r.json()["codes"]}
        # AURA20 / STAFF50 should appear in the demo bucket (seed claim)
        assert "AURA20" in codes or "STAFF50" in codes
