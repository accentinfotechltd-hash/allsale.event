"""Regression: invoice / booking-confirmation emails MUST render in the
event's currency, not a hard-coded USD.

Bug: `emails._money()` previously defaulted to `currency="USD"` and EVERY
call site invoked it as `_money(ctx.get('amount', 0))` without passing the
booking currency. Result: a buyer paying NZ$27.29 received an invoice
showing `$27.29 USD`.

Fix: `_money()` now defaults to NZD with proper per-currency symbols
(NZ$/A$/US$/£/€/etc), all call sites pass `ctx.get('currency')`, and the
booking-confirmation ctx in `payments.py` now includes the currency.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from emails import (  # noqa: E402
    _money,
    _t_booking_confirmation,
    _t_refund_issued,
    _t_organizer_payout_issued,
)


# ---------------------------------------------------------------------------
# 1. _money() helper itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("currency,expected", [
    # Oceania / North America baseline
    ("NZD", "NZ$27.29"),
    ("AUD", "A$27.29"),
    ("USD", "US$27.29"),
    ("FJD", "FJ$27.29"),
    # Europe
    ("GBP", "£27.29"),
    ("EUR", "€27.29"),
    ("CHF", "CHF 27.29"),
    ("PLN", "zł27.29"),
    ("CZK", "Kč27.29"),
    ("TRY", "₺27.29"),
    # Middle East
    ("AED", "AED 27.29"),
    ("QAR", "QAR 27.29"),
    ("KWD", "KWD 27.29"),
    ("ILS", "₪27.29"),
    # Asia
    ("INR", "₹27.29"),
    ("PKR", "₨27.29"),
    ("BDT", "৳27.29"),
    ("VND", "₫27.29"),
    ("TWD", "NT$27.29"),
    # Africa / South America
    ("ZAR", "R27.29"),
    ("NGN", "₦27.29"),
    ("EGP", "E£27.29"),
    ("BRL", "R$27.29"),
    ("ARS", "AR$27.29"),
    ("CLP", "CL$27.29"),
])
def test_money_uses_correct_symbol(currency: str, expected: str):
    assert _money(27.29, currency) == expected


def test_money_defaults_to_nzd_not_usd():
    """The original bug — default was USD."""
    assert _money(27.29) == "NZ$27.29"
    assert _money(27.29, "") == "NZ$27.29"
    assert _money(27.29, None) == "NZ$27.29"


def test_money_unknown_currency_falls_back_to_code_prefix():
    assert _money(50, "XYZ") == "XYZ 50.00"


# ---------------------------------------------------------------------------
# 2. Templates render with the right currency
# ---------------------------------------------------------------------------
_BOOKING_CTX_BASE = {
    "user_name": "Alice", "booking_id": "bkg_x", "event_id": "evt_1",
    "event_title": "Hamilton", "event_date": "2026-03-12",
    "venue": "Richard Rodgers", "city": "NY",
    "seats": ["A-1"], "quantity": 1, "amount": 50.0,
}


@pytest.mark.parametrize("currency,token", [
    ("NZD", "NZ$50.00"),
    ("USD", "US$50.00"),
    ("AUD", "A$50.00"),
    ("GBP", "£50.00"),
])
def test_booking_confirmation_renders_event_currency(currency: str, token: str):
    ctx = {**_BOOKING_CTX_BASE, "currency": currency}
    subject, html, text = _t_booking_confirmation(ctx)
    assert token in html, f"expected {token!r} in HTML for currency={currency}"
    assert token in text, f"expected {token!r} in text fallback for currency={currency}"
    # Ensure no leaked USD when the booking is non-USD
    if currency != "USD":
        assert "US$" not in html, f"USD leaked into {currency} email: {html[:200]}"


def test_booking_confirmation_defaults_to_nzd_when_currency_missing():
    """An older booking with no currency field should still render NZ$, not US$."""
    ctx = {**_BOOKING_CTX_BASE}  # no currency key
    _, html, text = _t_booking_confirmation(ctx)
    assert "NZ$50.00" in html
    assert "NZ$50.00" in text
    assert "US$" not in html
    # Old format that previously polluted invoices.
    assert "$50.00 USD" not in html
    assert "$50.00 USD" not in text


def test_refund_email_renders_event_currency():
    ctx = {
        "user_name": "Bob", "booking_id": "bkg_y",
        "event_title": "Dune", "amount": 30.0, "currency": "AUD",
    }
    subject, html, text = _t_refund_issued(ctx)
    assert "A$30.00" in html
    assert "A$30.00" in text
    assert "$30.00 USD" not in html


def test_payout_email_renders_organizer_currency():
    ctx = {
        "organizer_name": "Carla", "payout_id": "pyt_z",
        "amount": 1240.5, "currency": "NZD",
        "bookings_count": 12, "period": "Feb 2026",
    }
    subject, html, text = _t_organizer_payout_issued(ctx)
    assert "NZ$1,240.50" in subject
    assert "NZ$1,240.50" in html
    assert "NZ$1,240.50" in text
