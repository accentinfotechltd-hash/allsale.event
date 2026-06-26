"""Fee math — buyer-pays-fees model.

The buyer is charged enough to cover:
  1. The organizer's ticket face value (their gross revenue, paid out 5 days after the event).
  2. Allsale's platform fee (default 5% of face value).
  3. Stripe's processing fee (default 2.7% + $0.30) applied on the WHOLE charge.

We gross-up the buyer total so that *after* Stripe takes their cut, the remainder
covers face_value + platform_fee exactly.

Formula:
  buyer_total = (face_value + platform_fee + stripe_flat) / (1 - stripe_pct)
  stripe_fee  = buyer_total - (face_value + platform_fee)
  service_fee = platform_fee + stripe_fee  ← the single number the buyer sees

Env knobs (read at import time):
  PLATFORM_FEE_BPS  default 500   ( = 5%)
  STRIPE_FEE_BPS    default 270   ( = 2.7%, NZ domestic card)
  STRIPE_FEE_FLAT   default 0.30  (fixed per-transaction, in the event's currency)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key) or default)
    except Exception:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key) or default)
    except Exception:
        return default


PLATFORM_FEE_BPS = _env_int("PLATFORM_FEE_BPS", 500)     # 5%
STRIPE_FEE_BPS = _env_int("STRIPE_FEE_BPS", 270)         # 2.7%
STRIPE_FEE_FLAT = _env_float("STRIPE_FEE_FLAT", 0.30)    # $0.30


@dataclass(frozen=True)
class FeeBreakdown:
    face_value: float       # organizer's gross (paid out, minus platform fee)
    platform_fee: float     # Allsale's cut (5% of face_value by default)
    stripe_fee: float       # estimated Stripe fee on buyer_total
    service_fee: float      # platform_fee + stripe_fee — the single line the buyer sees
    buyer_total: float      # what we actually charge Stripe
    currency: str

    def as_dict(self) -> dict:
        return {
            "face_value": round(self.face_value, 2),
            "platform_fee": round(self.platform_fee, 2),
            "stripe_fee": round(self.stripe_fee, 2),
            "service_fee": round(self.service_fee, 2),
            "buyer_total": round(self.buyer_total, 2),
            "currency": self.currency,
            "platform_fee_bps": PLATFORM_FEE_BPS,
            "stripe_fee_bps": STRIPE_FEE_BPS,
            "stripe_fee_flat": STRIPE_FEE_FLAT,
        }


def compute_fees(
    face_value: float,
    currency: str = "NZD",
    platform_pct: float | None = None,
    stripe_flat: float | None = None,
    absorb_fees: bool = False,
) -> FeeBreakdown:
    """Compute the buyer charge + fee breakdown for `face_value`.

    Two modes, controlled per-event by `event.absorb_fees`:

    *Exclusive* (`absorb_fees=False`, current default) — the buyer-pays-fees
    model. We gross up `face_value` so that after Stripe takes their cut the
    remainder still covers face_value + platform_fee. Buyer sees the breakup.

    *Inclusive* (`absorb_fees=True`) — the organizer-absorbs-fees model. The
    organizer's "ticket price" IS what the buyer pays (no `+ fees` line at
    checkout); the platform fee + Stripe fee come out of the organizer's
    payout. The returned `face_value` field reflects the organizer's actual
    net (i.e. what hits their connected account), not the input arg.

    Returns 0s across the board if face_value <= 0 (e.g. comp tickets) so
    we never charge Stripe for a free transaction.

    `platform_pct` and `stripe_flat` are runtime overrides. Callers reading
    the admin's `platform_settings` from MongoDB should pass them in so the
    admin UI is the single source of truth for fee math (see bookings.py).
    Both fall back to env-var defaults when not provided.
    """
    if face_value <= 0:
        return FeeBreakdown(0, 0, 0, 0, 0, (currency or "NZD").upper())

    plat_pct = (PLATFORM_FEE_BPS / 10000.0) if platform_pct is None else float(platform_pct) / 100.0
    flat = STRIPE_FEE_FLAT if stripe_flat is None else float(stripe_flat)
    stripe_pct = STRIPE_FEE_BPS / 10000.0

    if absorb_fees:
        # Inclusive: buyer pays exactly the displayed `face_value`. Allsale's
        # cut is computed off the displayed price; Stripe's cut is computed
        # off the buyer total (which equals the displayed price in this mode).
        buyer_total = face_value
        platform = face_value * plat_pct
        stripe_fee = face_value * stripe_pct + flat
        # `face_value` returned to the caller is the organizer's NET — i.e.
        # what reaches their balance after platform + Stripe take their cut.
        organizer_net = max(0.0, face_value - platform - stripe_fee)
        service_fee = platform + stripe_fee  # hidden from buyer in this mode
        return FeeBreakdown(
            face_value=organizer_net,
            platform_fee=platform,
            stripe_fee=stripe_fee,
            service_fee=service_fee,
            buyer_total=buyer_total,
            currency=(currency or "NZD").upper(),
        )

    # Exclusive (default): gross up `face_value` so the buyer covers all fees.
    platform = face_value * plat_pct
    # Avoid div-by-zero (would only happen if STRIPE_FEE_BPS=10000, i.e. 100%).
    denom = max(1e-6, 1 - stripe_pct)
    buyer_total = (face_value + platform + flat) / denom
    stripe_fee = buyer_total - (face_value + platform)
    service_fee = platform + stripe_fee
    return FeeBreakdown(
        face_value=face_value,
        platform_fee=platform,
        stripe_fee=stripe_fee,
        service_fee=service_fee,
        buyer_total=buyer_total,
        currency=(currency or "NZD").upper(),
    )
