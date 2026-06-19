"""Quick smoke test for the server-side ticket PDF builder."""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from ticket_pdf import build_ticket_pdf  # noqa: E402


# 1×1 PNG (valid PNG header — fpdf2 will accept and render at the requested size)
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_build_pdf_with_qr_returns_bytes_and_filename():
    booking = {
        "event_title": "Allsale Live Garba Night — Auckland",
        "event_date": "2026-03-15T19:30:00",
        "venue": "Eventfinda Stadium",
        "city": "Auckland",
        "tier_name": "VIP",
        "seats": ["A-1", "A-2"],
        "booking_id": "bk_abcdef1234567890",
        "qr_code": f"data:image/png;base64,{TINY_PNG_B64}",
        "amount": 89.5,
        "currency": "NZD",
    }
    pdf_bytes, filename = build_ticket_pdf(booking)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF"), "PDF header should be %PDF-"
    assert len(pdf_bytes) > 1500, f"PDF suspiciously small: {len(pdf_bytes)} bytes"
    assert filename.endswith(".pdf")
    assert "bk_abcde" in filename or "allsale" in filename


def test_build_pdf_without_qr_falls_back_gracefully():
    booking = {
        "event_title": "Free Comedy Night",
        "event_date": "2026-04-01T20:00:00",
        "venue": "The Civic",
        "city": "Wellington",
        "tier_name": "GA",
        "quantity": 2,
        "booking_id": "bk_xyz",
        "qr_code": None,
        "amount": 0,
        "currency": "NZD",
    }
    pdf_bytes, filename = build_ticket_pdf(booking)
    assert pdf_bytes.startswith(b"%PDF")
    assert filename.endswith(".pdf")


def test_build_pdf_handles_unicode_titles():
    """Emoji + smart quotes shouldn't crash the build (Helvetica is Latin-1)."""
    booking = {
        "event_title": "🎉 Geeta Rabari's Garba — Live! 🎶",
        "event_date": "2026-05-20T19:00:00",
        "venue": "Grand Arena",
        "city": "Mumbai",
        "tier_name": "Front Row",
        "seats": ["A-1"],
        "booking_id": "bk_unicode_test",
        "qr_code": f"data:image/png;base64,{TINY_PNG_B64}",
        "amount": 250.0,
        "currency": "INR",
    }
    pdf_bytes, filename = build_ticket_pdf(booking)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1500
