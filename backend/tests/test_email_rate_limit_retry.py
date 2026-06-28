"""Resend 429 retry-with-backoff + booking confirmation fan-out.

Bug fixed: when a buyer paid, the booking-confirmation flow fires 3+
parallel emails (buyer + organizer + admin). Resend's free tier caps
at 2 req/sec → ~30% of admin notifications were silently failing with
"Too many requests. You can only make 2 requests per second."

Fix: `emails._resend_send_with_retry` adds exponential backoff
(400ms → 800ms → 1.6s → 3.2s) on rate-limit errors, while non-rate-limit
errors still raise immediately on the first attempt.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from emails import _resend_send_with_retry, send_template  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Retries on 429 then succeeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_succeeds_after_one_429():
    """Two attempts: first throws 429, second succeeds."""
    calls = {"n": 0}

    def _stub(_params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Too many requests. You can only make 2 requests per second.")
        return {"id": "resend_id_OK"}

    async def _no_sleep(_s):
        return None

    with patch("resend.Emails.send", side_effect=_stub):
        with patch("emails.asyncio.sleep", new=_no_sleep):
            result = await _resend_send_with_retry(
                {"from": "f", "to": ["x@x.com"], "subject": "S", "html": "H", "text": "T"},
                template="admin_new_booking",
                to="x@x.com",
            )
    assert result == {"id": "resend_id_OK"}
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# 2. Gives up after max_attempts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retry_exhausts_after_persistent_429():
    def _stub(_params):
        raise RuntimeError("Too many requests")

    async def _no_sleep(_s):
        return None

    with patch("resend.Emails.send", side_effect=_stub):
        with patch("emails.asyncio.sleep", new=_no_sleep):
            with pytest.raises(RuntimeError, match="Too many requests"):
                await _resend_send_with_retry(
                    {"from": "f", "to": ["x@x.com"], "subject": "S", "html": "H", "text": "T"},
                    template="admin_new_booking",
                    to="x@x.com",
                    max_attempts=3,
                )


# ---------------------------------------------------------------------------
# 3. Non-rate-limit errors fail FAST (no pointless retries)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_rate_limit_errors_do_not_retry():
    """Auth errors / invalid recipients should bubble up on attempt 1."""
    calls = {"n": 0}

    def _stub(_params):
        calls["n"] += 1
        raise RuntimeError("Invalid API key — auth_error")

    with patch("resend.Emails.send", side_effect=_stub):
        with pytest.raises(RuntimeError, match="auth_error"):
            await _resend_send_with_retry(
                {"from": "f", "to": ["x@x.com"], "subject": "S", "html": "H", "text": "T"},
                template="admin_new_booking",
                to="x@x.com",
            )
    assert calls["n"] == 1, "non-rate-limit errors must not trigger retries"


# ---------------------------------------------------------------------------
# 4. send_template logs `sent` (not `failed`) when retry succeeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_template_logs_sent_after_429_retry(monkeypatch):
    """End-to-end: a transient 429 must NOT pollute email_logs as failed."""
    monkeypatch.setattr("emails.RESEND_API_KEY", "re_fake")
    calls = {"n": 0}

    def _stub(_params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Too many requests. 2 per second.")
        return {"id": "id_after_retry"}

    inserts: list = []

    class _FakeColl:
        async def insert_one(self, doc):
            inserts.append(doc)

        async def find_one(self, *a, **kw):
            return None

    class _FakeDB:
        users = _FakeColl()
        email_logs = _FakeColl()

    with patch("resend.Emails.send", side_effect=_stub):
        async def _no_sleep(_s):
            return None
        with patch("emails.asyncio.sleep", new=_no_sleep):
            result = await send_template(
                "admin_new_booking",
                "admin@allsale.events",
                {
                    "admin_name": "Admin",
                    "booking_id": "bkg_42",
                    "event_title": "Y",
                    "buyer_email": "b@x.com",
                    "buyer_name": "Bob",
                    "quantity": 1,
                    "amount": 50,
                    "currency": "NZD",
                    "organizer_name": "Z",
                    "tier_name": "GA",
                },
                db=_FakeDB(),
            )
    assert result["status"] == "sent"
    assert result["resend_id"] == "id_after_retry"
    # Only ONE log row written (the success), not one per attempt.
    assert len(inserts) == 1
    assert inserts[0]["status"] == "sent"
    # booking_id cross-link present so support can trace it.
    assert inserts[0]["booking_id"] == "bkg_42"


# ---------------------------------------------------------------------------
# 5. booking_id is logged on every email tied to a booking
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_email_log_carries_booking_id_for_cross_link(monkeypatch):
    monkeypatch.setattr("emails.RESEND_API_KEY", "re_fake")
    inserts: list = []

    class _Coll:
        async def insert_one(self, doc):
            inserts.append(doc)
        async def find_one(self, *a, **kw):
            return None

    class _DB:
        users = _Coll()
        email_logs = _Coll()

    with patch("resend.Emails.send", return_value={"id": "ok"}):
        await send_template(
            "booking_confirmation",
            "buyer@x.com",
            {
                "user_name": "B", "booking_id": "bk_trace_123", "event_id": "evt_1",
                "event_title": "X", "event_date": "2026-03-12 19:00",
                "venue": "V", "city": "C", "seats": ["A-1"],
                "quantity": 1, "amount": 50.0, "currency": "NZD",
            },
            db=_DB(),
        )
    assert inserts and inserts[0].get("booking_id") == "bk_trace_123"
