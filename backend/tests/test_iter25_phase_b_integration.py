"""Phase B integration tests — Stripe Connect Destination Charges end-to-end.

Live HTTP tests against the running backend + sync pymongo for DB setup/teardown.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    front_env = Path("/app/frontend/.env")
    if front_env.exists():
        for line in front_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

assert BASE_URL, "REACT_APP_BACKEND_URL not set"

ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASSWORD = "admin123"
ORG_EMAIL = "orgtester@allsale.events"
ORG_PASSWORD = "orgtest123"
ORG_EVENT_ID = "evt_9237e281ca2b"
ORG_USER_ID = "user_2492358084d3"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def org_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ORG_EMAIL, "password": ORG_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"organizer login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def db_conn():
    """Direct Mongo (sync pymongo) for setup/teardown."""
    from pymongo import MongoClient

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME missing"
    client = MongoClient(mongo_url)
    return client[db_name]


# --------------------------------------------------------------------------
# 1. Smoke
# --------------------------------------------------------------------------
class TestSmoke:
    def test_payments_mode_public(self):
        r = requests.get(f"{BASE_URL}/api/payments/mode", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("configured") is True
        assert data["mode"] in {"test", "live", "test (restricted)", "live (restricted)"}

    def test_payments_health_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/payments/health",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["configured"] is True
        assert data["mode"] in {"test", "live", "test (restricted)", "live (restricted)"}
        assert "key_prefix" in data and len(data["key_prefix"]) <= 12

    def test_payments_health_blocks_non_admin(self, org_token):
        r = requests.get(
            f"{BASE_URL}/api/payments/health",
            headers={"Authorization": f"Bearer {org_token}"},
            timeout=10,
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# 2. Public fee settings exposes admin-configured rates (sane bounds)
# --------------------------------------------------------------------------
class TestPublicFeeSettings:
    def test_fees_public_settings_shape_and_bounds(self):
        """Admin can adjust platform_pct / platform_flat anytime via
        /admin/platform-settings, so the test asserts SHAPE + sane bounds
        rather than pinning to a particular number that goes stale."""
        r = requests.get(f"{BASE_URL}/api/fees/public-settings", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert 0 <= float(data["platform_pct"]) <= 50, data
        assert 0 <= float(data["platform_flat_per_ticket"]) <= 5, data
        assert "stripe_pct" in data and float(data["stripe_pct"]) > 0


# --------------------------------------------------------------------------
# 3. Legacy organizer checkout (no Connect) — must NOT flag destination charge
# --------------------------------------------------------------------------
class TestLegacyCheckout:
    def test_legacy_checkout_no_destination_charge_flag(self, org_token, db_conn):
        org = db_conn.users.find_one({"user_id": ORG_USER_ID}, {"_id": 0})
        assert org is not None, "Test organizer missing"
        # Scrub any stale connect creds from a previous failed run
        db_conn.users.update_one(
            {"user_id": ORG_USER_ID},
            {"$unset": {"stripe_account_id": "", "stripe_charges_enabled": ""}},
        )

        event = db_conn.events.find_one({"event_id": ORG_EVENT_ID}, {"_id": 0})
        assert event is not None, f"Test event {ORG_EVENT_ID} missing"
        paid_tier = next(
            (t for t in (event.get("tiers") or []) if float(t.get("price") or 0) > 0),
            None,
        )
        assert paid_tier, "Need a paid tier on test event"

        headers = {"Authorization": f"Bearer {org_token}"}
        rh = requests.post(
            f"{BASE_URL}/api/bookings/hold",
            json={"event_id": ORG_EVENT_ID, "tier_name": paid_tier["name"], "quantity": 1},
            headers=headers, timeout=15,
        )
        assert rh.status_code == 200, f"hold failed: {rh.status_code} {rh.text}"
        booking_id = rh.json().get("booking_id")
        assert booking_id

        rc = requests.post(
            f"{BASE_URL}/api/checkout/session",
            json={"booking_id": booking_id, "origin_url": "https://test.local"},
            headers=headers, timeout=30,
        )
        assert rc.status_code == 200, f"checkout failed: {rc.status_code} {rc.text}"
        cdata = rc.json()
        assert cdata.get("url"), f"no checkout url returned: {cdata}"
        assert cdata.get("session_id")

        booking_doc = db_conn.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        assert booking_doc is not None
        assert booking_doc.get("stripe_destination_charge") is not True, (
            f"Legacy organizer booking incorrectly flagged: {booking_doc}"
        )
        assert not booking_doc.get("stripe_connect_account_id")


# --------------------------------------------------------------------------
# 4. Destination-charge fallback: stamp fake acct_id → graceful legacy fallback
# --------------------------------------------------------------------------
class TestDestinationChargeFallback:
    def test_fake_acct_id_falls_back_to_legacy(self, org_token, db_conn):
        fake_acct = f"acct_TESTDESTCHARGE_{uuid.uuid4().hex[:8]}"
        db_conn.users.update_one(
            {"user_id": ORG_USER_ID},
            {"$set": {
                "stripe_account_id": fake_acct,
                "stripe_charges_enabled": True,
            }},
        )

        try:
            headers = {"Authorization": f"Bearer {org_token}"}
            event = db_conn.events.find_one({"event_id": ORG_EVENT_ID}, {"_id": 0})
            paid_tier = next(
                (t for t in (event.get("tiers") or []) if float(t.get("price") or 0) > 0),
                None,
            )
            assert paid_tier

            rh = requests.post(
                f"{BASE_URL}/api/bookings/hold",
                json={
                    "event_id": ORG_EVENT_ID,
                    "tier_name": paid_tier["name"],
                    "quantity": 1,
                },
                headers=headers, timeout=15,
            )
            assert rh.status_code == 200, rh.text
            booking_id = rh.json()["booking_id"]

            rc = requests.post(
                f"{BASE_URL}/api/checkout/session",
                json={"booking_id": booking_id, "origin_url": "https://test.local"},
                headers=headers, timeout=30,
            )
            assert rc.status_code == 200, (
                f"Expected graceful fallback, got {rc.status_code}: {rc.text}"
            )
            cdata = rc.json()
            assert cdata.get("url"), f"No Stripe URL after fallback: {cdata}"
            assert cdata.get("session_id")

            # Booking must NOT be flagged as destination_charge (it fell back)
            booking_doc = db_conn.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
            assert booking_doc.get("stripe_destination_charge") is not True, (
                f"Fallback should NOT flag destination_charge: {booking_doc}"
            )
        finally:
            db_conn.users.update_one(
                {"user_id": ORG_USER_ID},
                {"$unset": {
                    "stripe_account_id": "",
                    "stripe_charges_enabled": "",
                }},
            )


# --------------------------------------------------------------------------
# 5. Payouts balance excludes destination-charge bookings
# --------------------------------------------------------------------------
class TestPayoutsBalanceExclusion:
    def test_destination_charge_booking_excluded_from_balance(self, org_token, db_conn):
        org_event_ids = [
            ev["event_id"]
            for ev in db_conn.events.find(
                {"organizer_id": ORG_USER_ID}, {"_id": 0, "event_id": 1},
            )
        ]
        assert org_event_ids, "No events for test organizer"

        target = db_conn.bookings.find_one(
            {"event_id": {"$in": org_event_ids}, "status": "paid"},
            {"_id": 0},
        )
        seeded = False
        if not target:
            # Seed a synthetic TEST_ paid booking so we can exercise the
            # exclusion path. Cleaned up in `finally`.
            seeded = True
            bid = f"TEST_bk_iter25_{uuid.uuid4().hex[:8]}"
            db_conn.bookings.insert_one({
                "booking_id": bid,
                "event_id": org_event_ids[0],
                "user_id": "TEST_buyer",
                "user_email": "TEST_buyer@example.com",
                "status": "paid",
                "amount": 26.77,
                "face_value": 25.0,
                "platform_fee": 0.75,
                "stripe_fee_estimated": 1.02,
                "quantity": 1,
                "currency": "NZD",
                "paid_at": "2026-01-01T00:00:00+00:00",
            })
            target = db_conn.bookings.find_one({"booking_id": bid}, {"_id": 0})
            assert target

        bid = target["booking_id"]
        original_flag = target.get("stripe_destination_charge")

        # Baseline: capture gross/tickets/bookings_count pre-flag
        r0 = requests.get(
            f"{BASE_URL}/api/organizer/payouts/balance",
            headers={"Authorization": f"Bearer {org_token}"},
            timeout=15,
        )
        assert r0.status_code == 200, r0.text
        avail0 = r0.json().get("available") or {}
        baseline_gross = float(avail0.get("gross") or 0)
        baseline_bookings = int(avail0.get("bookings") or 0)
        booking_face = float(target.get("face_value") or target.get("amount") or 0)

        try:
            db_conn.bookings.update_one(
                {"booking_id": bid},
                {"$set": {"stripe_destination_charge": True}},
            )
            time.sleep(0.5)

            r = requests.get(
                f"{BASE_URL}/api/organizer/payouts/balance",
                headers={"Authorization": f"Bearer {org_token}"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            avail = r.json().get("available") or {}
            after_gross = float(avail.get("gross") or 0)
            after_bookings = int(avail.get("bookings") or 0)

            # bookings count must drop by exactly 1
            assert after_bookings == baseline_bookings - 1, (
                f"Bookings count should drop by 1 after flagging — "
                f"baseline={baseline_bookings} after={after_bookings}"
            )
            # gross must drop by approximately face_value of the booking
            assert after_gross == pytest.approx(baseline_gross - booking_face, abs=0.05), (
                f"Gross should drop by face_value={booking_face} — "
                f"baseline={baseline_gross} after={after_gross}"
            )
        finally:
            if seeded:
                db_conn.bookings.delete_one({"booking_id": bid})
            elif original_flag is None:
                db_conn.bookings.update_one(
                    {"booking_id": bid},
                    {"$unset": {"stripe_destination_charge": ""}},
                )
            else:
                db_conn.bookings.update_one(
                    {"booking_id": bid},
                    {"$set": {"stripe_destination_charge": original_flag}},
                )


# --------------------------------------------------------------------------
# 6. Admin revenue endpoint still returns per-booking breakdown
# --------------------------------------------------------------------------
class TestAdminRevenue:
    def test_admin_revenue_breakdown(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/revenue?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "totals" in data
        totals = data["totals"]
        for key in ("gross", "stripe_fees", "platform_fees", "organizer_share", "count"):
            assert key in totals, f"missing totals.{key}: {totals}"

        # Per-booking breakdown — must include the 3 cost components
        # (Phase A uses `organizer_share` instead of `face_value` in the row)
        for row in data["items"][:3]:
            for k in ("platform_fee", "stripe_fee", "organizer_share", "gross"):
                assert k in row, f"row missing {k}: {row}"


# --------------------------------------------------------------------------
# 7. Platform settings DB doc — admin-driven, just assert sane shape
# --------------------------------------------------------------------------
class TestPlatformSettingsDoc:
    def test_platform_settings_db_has_user_rates(self, db_conn):
        doc = db_conn.platform_settings.find_one({"key": "commission"}, {"_id": 0})
        if doc is None:
            pytest.skip("platform_settings.commission doc not present — env fallback active")
        # Admin can set any rate via /admin/platform-settings — assert SHAPE
        # + sane bounds, not specific values that go stale.
        pct = float(doc.get("commission_percent") or 0)
        flat = float(doc.get("commission_flat_fee_per_ticket") or 0)
        assert 0 <= pct <= 50, f"unreasonable commission_percent: {pct} in {doc}"
        assert 0 <= flat <= 5, f"unreasonable commission_flat: {flat} in {doc}"
