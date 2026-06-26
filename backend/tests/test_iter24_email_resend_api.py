"""Iteration 24 — HTTP-level validation of the email-bytes-attachment fix.

Asserts that POST /api/admin/email/resend-booking against an existing PAID
booking now produces an `email_logs` row with status='sent' (not 'failed')
and no rows with reason 'Object of type bytes is not JSON serializable'
since the fix landed.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # Fall back to frontend/.env (testing usage)
    load_dotenv(BACKEND_DIR.parent / "frontend" / ".env")
    BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASSWORD = "admin123"
TARGET_BOOKING = "bk_partner_test_001"
BYTES_BUG_REASON = "Object of type bytes is not JSON serializable"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    body = r.json()
    token = body.get("token") or body.get("access_token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def mongo_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if not asyncio.get_event_loop().is_closed() else asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_target_booking_exists_and_is_paid(mongo_db):
    booking = _run(mongo_db.bookings.find_one({"booking_id": TARGET_BOOKING}, {"_id": 0}))
    assert booking is not None, f"seed booking {TARGET_BOOKING} missing"
    assert booking.get("status") == "paid"
    assert booking.get("user_email")


def test_admin_resend_booking_returns_200(admin_session: requests.Session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/email/resend-booking",
        json={"booking_id": TARGET_BOOKING},
        timeout=30,
    )
    assert r.status_code == 200, f"resend failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("booking_id") == TARGET_BOOKING
    assert body.get("to")


def test_email_log_row_was_sent_with_resend_id(admin_session, mongo_db):
    """Resend the email then verify the latest email_logs row for this
    booking_confirmation has status='sent' and non-empty resend_id.
    """
    # Respect Resend's 2 req/s limit (previous test fired one resend).
    time.sleep(1.5)

    # Retry around transient rate-limits — they're NOT the bug we're testing.
    last_body = None
    for attempt in range(3):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/email/resend-booking",
            json={"booking_id": TARGET_BOOKING},
            timeout=30,
        )
        assert r.status_code == 200, f"resend failed: {r.status_code} {r.text}"
        last_body = r.json()
        # Allow log row to flush
        time.sleep(0.8)
        latest = _run(
            mongo_db.email_logs.find_one(
                {"template": "booking_confirmation", "to": "buyer@test.com"},
                sort=[("created_at", -1)],
            )
        )
        if latest and latest.get("status") == "sent" and latest.get("resend_id"):
            assert isinstance(latest["resend_id"], str) and len(latest["resend_id"]) > 0
            # The KEY assertion: NOT the bytes-serialisation reason
            assert latest.get("reason") != BYTES_BUG_REASON
            return
        # If failed with rate-limit, back off and retry
        reason = (latest or {}).get("reason", "")
        if "Too many requests" in reason or "rate" in reason.lower():
            time.sleep(3 * (attempt + 1))
            continue
        # Other failure modes — surface immediately
        pytest.fail(
            f"booking_confirmation latest log not sent — status={latest.get('status') if latest else None} "
            f"reason={reason}"
        )

    pytest.fail(f"could not get a 'sent' booking_confirmation row after 3 retries; last latest={latest}")


def test_no_new_bytes_serialization_failures(admin_session, mongo_db):
    """Critical: trigger several resends; ensure ZERO new rows carry the
    bytes-serialisation failure reason after the fix is in place.

    (Historical pre-fix rows from before the deploy are allowed — we snapshot
    the count, run new resends, and assert the count did NOT grow.)
    """
    before = _run(
        mongo_db.email_logs.count_documents({"reason": {"$regex": BYTES_BUG_REASON}})
    )

    # Hammer the endpoint a few times across the available paid bookings
    # to exercise the attachment path (with rate-limit backoff between calls).
    paid_ids = _run(
        mongo_db.bookings.find({"status": "paid"}, {"_id": 0, "booking_id": 1, "user_email": 1})
        .limit(3)
        .to_list(3)
    )
    paid_ids = [b["booking_id"] for b in paid_ids if b.get("user_email")]
    assert paid_ids, "no paid bookings with user_email in DB"

    for bid in paid_ids:
        r = admin_session.post(
            f"{BASE_URL}/api/admin/email/resend-booking",
            json={"booking_id": bid},
            timeout=30,
        )
        assert r.status_code == 200, f"resend for {bid}: {r.status_code} {r.text}"
        time.sleep(1.2)  # Resend free tier rate-limits at 2 req/s — be safe

    after = _run(
        mongo_db.email_logs.count_documents({"reason": {"$regex": BYTES_BUG_REASON}})
    )
    assert after == before, (
        f"bytes-serialisation failure count grew from {before} → {after} after resends — fix not effective"
    )

    # And every freshly-written row for these bookings should be either
    # 'sent' or rate-limited — NEVER the bytes-serialisation reason.
    for bid in paid_ids:
        latest = _run(
            mongo_db.email_logs.find_one(
                {"template": "booking_confirmation", "booking_id": bid},
                sort=[("created_at", -1)],
            )
        ) or _run(
            mongo_db.email_logs.find_one(
                {"template": "booking_confirmation"}, sort=[("created_at", -1)]
            )
        )
        if latest is None:
            continue
        reason = latest.get("reason") or ""
        assert BYTES_BUG_REASON not in reason, (
            f"latest booking_confirmation for {bid} hit the bytes-bug — reason={reason}"
        )
        # Either successfully sent, or transiently rate-limited (acceptable)
        if latest.get("status") != "sent":
            assert "Too many requests" in reason or "rate" in reason.lower(), (
                f"unexpected failure for {bid}: status={latest.get('status')} reason={reason}"
            )


def test_resend_endpoint_rejects_unknown_booking(admin_session: requests.Session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/email/resend-booking",
        json={"booking_id": "bk_does_not_exist_xyz"},
        timeout=15,
    )
    assert r.status_code == 404


def test_admin_send_test_email_works(admin_session: requests.Session):
    """Regression: the lightweight /admin/email/send-test path (no
    attachments) should keep working."""
    # Respect Resend's 2 req/s rate limit (other tests sent recently).
    time.sleep(1.5)
    r = admin_session.post(
        f"{BASE_URL}/api/admin/email/send-test",
        json={"to": "buyer@test.com", "subject": "iter24 diag"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Either ok=true with sent id, or a rate-limit reason (transient).
    if not body.get("ok"):
        reason = (body.get("reason") or "").lower()
        if "too many requests" in reason or "rate" in reason:
            pytest.skip(f"transient Resend rate-limit: {body}")
    assert body.get("ok") is True, f"send-test failed: {body}"
