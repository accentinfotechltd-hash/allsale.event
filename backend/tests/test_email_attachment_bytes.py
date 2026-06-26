"""Regression test for booking-confirmation email PDF attachment.

Bug: Resend SDK v2.x rejects raw `bytes` in attachment `content` with
`Object of type bytes is not JSON serializable`. The booking-confirmation
flow attaches a freshly-built PDF ticket as `bytes`, which silently killed
every e-ticket email.

Fix: `emails._normalize_attachments()` base64-encodes bytes before they
reach Resend. This test pins that behaviour end-to-end.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from emails import _normalize_attachments, send_template  # noqa: E402


# ---------------------------------------------------------------------------
# Unit: normaliser handles the three valid `content` shapes + drops junk
# ---------------------------------------------------------------------------
def test_normalize_bytes_to_base64_string():
    out = _normalize_attachments([{"content": b"hello world", "filename": "t.txt"}])
    assert out[0]["filename"] == "t.txt"
    assert isinstance(out[0]["content"], str)
    assert base64.b64decode(out[0]["content"]) == b"hello world"


def test_normalize_bytearray_to_base64_string():
    out = _normalize_attachments([{"content": bytearray(b"abc"), "filename": "x"}])
    assert isinstance(out[0]["content"], str)
    assert base64.b64decode(out[0]["content"]) == b"abc"


def test_normalize_passthrough_for_base64_string():
    encoded = base64.b64encode(b"already encoded").decode("ascii")
    out = _normalize_attachments([{"content": encoded, "filename": "t.pdf"}])
    assert out[0]["content"] == encoded


def test_normalize_passthrough_for_list_of_ints():
    out = _normalize_attachments([{"content": [1, 2, 3], "filename": "t.bin"}])
    assert out[0]["content"] == [1, 2, 3]


def test_normalize_drops_unsupported_content():
    out = _normalize_attachments([{"content": {"weird": True}, "filename": "bad"}])
    assert "content" not in out[0]
    assert out[0]["filename"] == "bad"


def test_normalize_output_is_json_serialisable():
    """The whole point: Resend SDK JSON-encodes params, so output MUST encode."""
    out = _normalize_attachments([
        {"content": b"\x00\x01PDF_BINARY\xff", "filename": "ticket.pdf"},
        {"content": "YWJj", "filename": "already.txt"},
    ])
    # Should not raise.
    json.dumps(out)


# ---------------------------------------------------------------------------
# Integration: send_template feeds a sane payload to Resend.Emails.send
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_template_serialises_bytes_attachment(monkeypatch):
    """Verify Resend SDK receives base64 string, never raw bytes."""
    monkeypatch.setattr("emails.RESEND_API_KEY", "re_fake_key_for_test")

    captured: dict = {}

    def _fake_send(params):
        captured["params"] = params
        # This is the failure mode we're guarding against.
        json.dumps(params)  # will raise if bytes leak through
        return {"id": "fake_id_xyz"}

    with patch("resend.Emails.send", side_effect=_fake_send):
        res = await send_template(
            "booking_confirmation",
            "buyer@test.com",
            {
                "user_name": "Alice", "booking_id": "bkg_x", "event_id": "evt_1",
                "event_title": "Hamilton", "event_date": "2026-03-12 19:00",
                "venue": "X", "city": "Y", "seats": ["A-1"],
                "quantity": 1, "amount": 50.0,
            },
            db=None,
            attachments=[{"content": b"%PDF-1.4 binary_content", "filename": "ticket.pdf"}],
        )

    assert res["status"] == "sent"
    atts = captured["params"]["attachments"]
    assert len(atts) == 1
    assert atts[0]["filename"] == "ticket.pdf"
    assert isinstance(atts[0]["content"], str)
    assert base64.b64decode(atts[0]["content"]) == b"%PDF-1.4 binary_content"


# ---------------------------------------------------------------------------
# Integration: real PDF generator output flows through unchanged
# ---------------------------------------------------------------------------
def test_real_ticket_pdf_passes_through_normaliser():
    """Pin the exact path used by `_send_booking_confirmation_email`."""
    from ticket_pdf import build_ticket_pdf
    pdf_bytes, filename = build_ticket_pdf({
        "user_name": "Test Buyer",
        "user_email": "buyer@example.com",
        "booking_id": "bkg_test",
        "event_id": "evt_test",
        "event_title": "Regression Test Show",
        "event_date": "2026-03-12T19:00:00Z",
        "event_venue": "Test Venue",
        "event_city": "Auckland",
        "seats": ["A-1", "A-2"],
        "tier_name": "GA",
        "quantity": 2,
        "amount": 100.0,
        "currency": "NZD",
        "qr_code": None,
    })
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")

    normalised = _normalize_attachments([{"content": pdf_bytes, "filename": filename}])
    # Must JSON-serialise (this is the exact thing Resend SDK does internally).
    json.dumps(normalised)
    assert isinstance(normalised[0]["content"], str)
    assert base64.b64decode(normalised[0]["content"]).startswith(b"%PDF")
