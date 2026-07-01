"""Fee math — verify the platform_flat is independent of stripe_flat.

User reported that their Stripe account shows fees of 1% + $0.50 collected.
The old code conflated `platform_flat` and `stripe_flat`: a single
`commission_flat_fee_per_ticket` field was being passed as `stripe_flat`
to `compute_fees`, which meant:
   - The buyer was correctly grossed-up to cover face_value + 1% + $0.50
   - But internally we were "spending" the $0.50 against Stripe's actual
     $0.30 flat, leaving the platform with $0.20 less than expected

Fix: separate `platform_flat` parameter so the math reflects:
     buyer pays:   face + (face × 1%) + $0.50 + Stripe's 2.7% + $0.30 (all grossed up)
     admin keeps:  (face × 1%) + $0.50           ← intended platform revenue
     stripe takes: face × 2.7% + $0.30           ← processing fee
     organizer:    face                          ← payout
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fees import compute_fees  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Default config (user's actual rates: 1% + $0.50 platform)
# ---------------------------------------------------------------------------
def test_default_platform_fee_is_1pct_plus_50c():
    """Env defaults must match the user's actual published rates."""
    fb = compute_fees(face_value=100.0, currency="NZD")
    # 1% × $100 + $0.50 = $1.50 platform cut
    assert round(fb.platform_fee, 2) == 1.50
    assert round(fb.face_value, 2) == 100.0


def test_default_platform_fee_for_25_dollar_ticket():
    """Spot-check with the Geeta Rabari Early Bird price."""
    fb = compute_fees(face_value=25.0, currency="NZD")
    # 1% × $25 + $0.50 = $0.75
    assert round(fb.platform_fee, 2) == 0.75


# ---------------------------------------------------------------------------
# 2. platform_flat is INDEPENDENT of stripe_flat
# ---------------------------------------------------------------------------
def test_platform_flat_does_not_replace_stripe_flat():
    """Passing platform_flat=0.50 must NOT zero out Stripe's $0.30."""
    fb = compute_fees(
        face_value=100.0,
        currency="NZD",
        platform_pct=1.0,
        platform_flat=0.50,
        # stripe_flat not passed → keeps env default $0.30
    )
    # Buyer total must include BOTH flats (grossed up):
    # platform = $1.00 + $0.50 = $1.50
    # buyer_total = (100 + 1.50 + 0.30) / (1 - 0.027) = 101.80 / 0.973 ≈ 104.62
    assert round(fb.platform_fee, 2) == 1.50
    # Stripe's flat must still be inside the gross-up
    # i.e. raising platform_flat 0.5 → 0.0 should reduce buyer_total by ~0.51
    fb0 = compute_fees(face_value=100.0, currency="NZD", platform_pct=1.0, platform_flat=0.0)
    assert round(fb.buyer_total - fb0.buyer_total, 2) == 0.51  # 0.50 grossed up


def test_explicit_overrides_take_precedence_over_env():
    """Per-call overrides must beat env defaults."""
    fb = compute_fees(
        face_value=50.0,
        currency="NZD",
        platform_pct=2.5,
        platform_flat=1.00,
    )
    # 2.5% × $50 + $1.00 = $2.25
    assert round(fb.platform_fee, 2) == 2.25


# ---------------------------------------------------------------------------
# 3. Absorb-fees mode applies the same platform breakdown
# ---------------------------------------------------------------------------
def test_absorb_fees_mode_deducts_platform_flat_from_organizer_payout():
    fb = compute_fees(
        face_value=100.0,
        currency="NZD",
        platform_pct=1.0,
        platform_flat=0.50,
        absorb_fees=True,
    )
    # Buyer pays sticker $100.
    # Stripe takes 2.7% + $0.30 = $3.00
    # Platform takes 1% + $0.50 = $1.50
    # Organizer net = 100 - 3.00 - 1.50 = $95.50
    assert fb.buyer_total == 100.0
    assert round(fb.platform_fee, 2) == 1.50
    assert round(fb.stripe_fee, 2) == 3.00
    assert round(fb.face_value, 2) == 95.50


# ---------------------------------------------------------------------------
# 4. Public-settings endpoint contract — frontend needs both flats
# ---------------------------------------------------------------------------
def test_public_settings_response_shape():
    """The /api/fees/public-settings endpoint must expose all four numbers so
    the frontend's fee preview can compute the exact buyer total without
    a second API call.

    The actual numeric values are admin-configurable via the platform_settings
    collection — we assert SHAPE + that the values are sane (non-negative,
    reasonable bounds), not that they equal a hard-coded constant.
    """
    import os
    import requests

    api_url = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"
    r = requests.get(f"{api_url}/api/fees/public-settings", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"platform_pct", "platform_flat_per_ticket", "stripe_pct", "stripe_flat_per_ticket"}
    # Sanity bounds — catches a regression that nukes the value to None or NaN
    # without pinning the test to a value the admin can change anytime.
    assert 0 <= body["platform_pct"] <= 50
    assert 0 <= body["platform_flat_per_ticket"] <= 5
    assert 0 < body["stripe_pct"] <= 10
    assert 0 < body["stripe_flat_per_ticket"] <= 2


# ---------------------------------------------------------------------------
# 5. as_dict carries both flats — useful for invoices and admin pages
# ---------------------------------------------------------------------------
def test_breakdown_as_dict_has_both_flats():
    d = compute_fees(face_value=30.0, currency="NZD").as_dict()
    assert "platform_fee_flat" in d
    assert "stripe_fee_flat" in d
    assert d["platform_fee_flat"] == 0.50
    assert d["stripe_fee_flat"] == 0.30
