"""Per-category seat pricing — VIP/Premium charge premium prices, House comps free."""
from __future__ import annotations
import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from core import seat_price_for  # noqa: E402


def _event(**extra):
    base = {
        "seat_price": 40.0,
        "seatmap_categories": {
            "vip": ["A-1", "A-2"],
            "premium": ["A-3"],
            "house": ["A-4"],
            "wheelchair": ["B-1"],
            "disabled": ["B-2"],
        },
    }
    base.update(extra)
    return base


def test_category_price_override_wins_over_default():
    e = _event(seatmap_category_prices={"vip": 80.0, "premium": 60.0, "wheelchair": 30.0})
    assert seat_price_for(e, "A-1") == 80.0  # VIP
    assert seat_price_for(e, "A-3") == 60.0  # Premium
    assert seat_price_for(e, "B-1") == 30.0  # Wheelchair


def test_house_defaults_to_zero_when_no_price_set():
    e = _event(seatmap_category_prices={"vip": 80.0})
    assert seat_price_for(e, "A-4") == 0.0  # house seat = comp


def test_uncategorized_seats_use_event_default():
    e = _event(seatmap_category_prices={"vip": 80.0})
    assert seat_price_for(e, "Z-1") == 40.0  # no category → default


def test_categorized_seat_without_price_falls_through_to_default():
    # "disabled" is in the categories map, but no price configured.
    # Should fall back to event-level seat_price (NOT zero — only house gets that).
    e = _event(seatmap_category_prices={"vip": 80.0})
    assert seat_price_for(e, "B-2") == 40.0


def test_invalid_category_price_falls_through():
    e = _event(seatmap_category_prices={"vip": "not-a-number"})
    # Invalid value → falls through to event default
    assert seat_price_for(e, "A-1") == 40.0
