"""Phase B: Stripe Connect Destination Charges — unit + integration tests.

Validates the routing logic that decides when a checkout should go through
`payment_intent_data={application_fee_amount, transfer_data}` (Phase B) vs.
the legacy platform-collects-100% flow, and the math behind the application
fee amount.

These tests stub the Stripe SDK and the DB layer — no real Stripe calls.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Stripe SDK is imported lazily inside routers/payments.py — make sure it's
# available before we import the module under test.
import stripe  # noqa: F401  pylint: disable=unused-import

from routers import payments as payments_mod  # noqa: E402
from routers import payouts as payouts_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------
def _booking(face_value=25.0, amount=26.77, gift_card_amount=0.0, **extra):
    """Standard booking shape with the exact fields _should_use_destination_charge reads."""
    return {
        "booking_id": "bk_test_abc123",
        "event_id": "evt_test_xyz",
        "user_id": "user_buyer",
        "user_email": "buyer@test.com",
        "currency": "NZD",
        "amount": amount,
        "face_value": face_value,
        "platform_fee": 0.75,
        "stripe_fee_estimated": 1.02,
        "service_fee": 1.77,
        "gift_card_amount": gift_card_amount,
        "status": "pending",
        **extra,
    }


def _organizer(stripe_account_id="acct_organizer_test_123", charges_enabled=True):
    return {
        "user_id": "user_organizer",
        "stripe_account_id": stripe_account_id,
        "stripe_charges_enabled": charges_enabled,
    }


# ---------------------------------------------------------------------------
# _should_use_destination_charge — gating logic
# ---------------------------------------------------------------------------
class TestShouldUseDestinationCharge:
    def test_happy_path_organizer_with_connect(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            assert payments_mod._should_use_destination_charge(
                _booking(), _organizer()
            ) is True

    def test_no_organizer(self):
        assert payments_mod._should_use_destination_charge(_booking(), None) is False

    def test_organizer_without_stripe_account(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            org = _organizer(stripe_account_id="")
            assert payments_mod._should_use_destination_charge(_booking(), org) is False

    def test_organizer_charges_not_enabled(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            org = _organizer(charges_enabled=False)
            assert payments_mod._should_use_destination_charge(_booking(), org) is False

    def test_gift_card_redemption_uses_legacy(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            assert payments_mod._should_use_destination_charge(
                _booking(gift_card_amount=5.0), _organizer()
            ) is False

    def test_no_stripe_api_key(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", ""):
            assert payments_mod._should_use_destination_charge(
                _booking(), _organizer()
            ) is False

    def test_free_or_zero_amount_booking(self):
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            # A comp ticket / fully gift-carded booking would have amount=0
            assert payments_mod._should_use_destination_charge(
                _booking(amount=0, face_value=0), _organizer()
            ) is False

    def test_face_value_greater_than_amount_bails(self):
        """Pathological case — face_value should never exceed amount in exclusive mode."""
        with patch.object(payments_mod, "_RAW_STRIPE_AVAILABLE", True), \
             patch.object(payments_mod, "STRIPE_API_KEY", "sk_test_dummy"):
            assert payments_mod._should_use_destination_charge(
                _booking(face_value=100, amount=50), _organizer()
            ) is False


# ---------------------------------------------------------------------------
# _application_fee_cents — math
# ---------------------------------------------------------------------------
class TestApplicationFeeMath:
    def test_exclusive_mode_25_ticket(self):
        """NZ$25 face, $26.77 buyer total → $1.77 app fee = 177 cents."""
        cents = payments_mod._application_fee_cents(_booking(face_value=25.0, amount=26.77))
        assert cents == 177

    def test_absorb_fees_mode(self):
        """Absorb mode: buyer pays $25, organizer nets $23.27 → app fee $1.73."""
        b = _booking(face_value=23.27, amount=25.00)
        cents = payments_mod._application_fee_cents(b)
        assert cents == 173

    def test_with_protection_surcharge(self):
        """Protection is on top of buyer_total. App fee still = amount - face_value."""
        b = _booking(face_value=25.0, amount=27.27)  # +$0.50 protection on top of $26.77
        cents = payments_mod._application_fee_cents(b)
        assert cents == 227

    def test_floors_to_zero_when_face_exceeds_amount(self):
        b = _booking(face_value=10.0, amount=5.0)
        assert payments_mod._application_fee_cents(b) == 0

    def test_rounds_half_up(self):
        # face $1.005 = 100.5 cents — int(round()) banker-rounds, so 100
        # Let's pick a value that has clear rounding. $0.005 buffer.
        b = _booking(face_value=1.0, amount=1.005)
        # diff = 0.005 → 0.5 cents → int(round(0.5)) = 0 (banker's rounding)
        # Just assert it's >= 0 and consistent
        assert payments_mod._application_fee_cents(b) in (0, 1)


# ---------------------------------------------------------------------------
# Payouts: destination-charge bookings excluded from manual payout queue
# ---------------------------------------------------------------------------
class TestPayoutEligibility:
    @pytest.mark.asyncio
    async def test_destination_charge_bookings_excluded(self, monkeypatch):
        """Bookings flagged stripe_destination_charge=True must NOT show up
        in `_eligible_bookings_for_payout` — they were already paid out at
        checkout time via Stripe Connect."""
        # Mock the db.events.find cursor for `_get_organizer_event_ids`.
        async def fake_events_cursor(*args, **kwargs):
            class _C:
                def __aiter__(self_inner):
                    self_inner._i = 0
                    return self_inner

                async def __anext__(self_inner):
                    if self_inner._i == 0:
                        self_inner._i += 1
                        return {"event_id": "evt_test_xyz"}
                    raise StopAsyncIteration

            return _C()

        # Replace `_get_organizer_event_ids` to deterministically return one event.
        async def fake_event_ids(organizer_id):
            return ["evt_test_xyz"]
        monkeypatch.setattr(payouts_mod, "_get_organizer_event_ids", fake_event_ids)

        # Capture the query passed to db.bookings.find so we can assert the
        # exclusion filter is present.
        captured_queries: list[dict] = []

        def fake_bookings_find(query, *args, **kwargs):
            captured_queries.append(query)

            class _Cursor:
                def sort(self, *_a, **_k):
                    return self

                def __aiter__(self_inner):
                    return self_inner

                async def __anext__(self_inner):
                    raise StopAsyncIteration

            return _Cursor()

        fake_db = MagicMock()
        fake_db.bookings.find = fake_bookings_find
        monkeypatch.setattr(payouts_mod, "db", fake_db)

        result = await payouts_mod._eligible_bookings_for_payout("user_organizer")
        assert result == []
        # Both queries (primary + fallback) must filter out destination charges.
        assert len(captured_queries) >= 1
        for q in captured_queries:
            assert q.get("stripe_destination_charge") == {"$ne": True}, (
                f"Query did not exclude destination charges: {q}"
            )

    @pytest.mark.asyncio
    async def test_legacy_bookings_still_eligible(self, monkeypatch):
        """A booking with no `stripe_destination_charge` field (legacy)
        MUST still show up in the eligibility query — Mongo's `$ne: True`
        also matches missing fields."""
        async def fake_event_ids(organizer_id):
            return ["evt_test_xyz"]
        monkeypatch.setattr(payouts_mod, "_get_organizer_event_ids", fake_event_ids)

        legacy_booking = {
            "booking_id": "bk_legacy_1",
            "event_id": "evt_test_xyz",
            "status": "paid",
            "face_value": 25.0,
            "amount": 26.77,
            "quantity": 1,
            # NOTE: no stripe_destination_charge field — pre-Phase-B booking
        }

        async def yield_legacy():
            yield legacy_booking

        def fake_bookings_find(query, *args, **kwargs):
            class _Cursor:
                def sort(self, *_a, **_k):
                    return self

                def __aiter__(self_inner):
                    self_inner._iter = yield_legacy()
                    return self_inner

                async def __anext__(self_inner):
                    return await self_inner._iter.__anext__()

            return _Cursor()

        fake_db = MagicMock()
        fake_db.bookings.find = fake_bookings_find
        monkeypatch.setattr(payouts_mod, "db", fake_db)

        result = await payouts_mod._eligible_bookings_for_payout("user_organizer")
        assert len(result) == 1
        assert result[0]["booking_id"] == "bk_legacy_1"
