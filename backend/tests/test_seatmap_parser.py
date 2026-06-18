"""Seatmap text-layout parser — deterministic, fast, offline."""
from __future__ import annotations
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers.seatmap_ai import parse_text_layout  # noqa: E402


def test_parses_cinema_layout_with_all_categories():
    text = """Row A: 1-15, disabled 1-5, house 6-11, disabled 12-15
B: 1-2 aisle, 3-12
C: 1-10
D: 1-10
E: 1-10
F: 1-10 disabled
G: 1-10 disabled
H: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled"""
    r = parse_text_layout(text)
    assert r["rows"] == 8
    assert r["cols"] == 15
    assert r["confidence"] >= 0.9
    # Row A 1-5 disabled
    assert "A-1" in r["seat_categories"]["disabled"]
    assert "A-5" in r["seat_categories"]["disabled"]
    # Row A 6-11 house
    assert "A-6" in r["seat_categories"]["house"]
    assert "A-11" in r["seat_categories"]["house"]
    # Wheelchair seats
    assert "H-5" in r["seat_categories"]["wheelchair"]
    assert "H-9" in r["seat_categories"]["wheelchair"]
    # Row B missing 13-15 → aisles
    assert "B-13" in r["aisles"]
    assert "B-14" in r["aisles"]
    assert "B-15" in r["aisles"]
    # Row H aisles at 6-8
    assert "H-6" in r["aisles"]
    assert "H-7" in r["aisles"]
    assert "H-8" in r["aisles"]


def test_handles_row_range_syntax():
    text = "Row C-E: 1-10 normal"
    r = parse_text_layout(text)
    assert r["rows"] == 3
    assert r["cols"] == 10
    # No category, no aisles
    assert r["seat_categories"]["disabled"] == []
    assert r["aisles"] == []


def test_returns_empty_grid_on_unparseable_input():
    r = parse_text_layout("this is not a seat map")
    assert r["rows"] == 0
    assert r["cols"] == 0
    assert r["confidence"] == 0.0


def test_aisle_keyword_marks_aisle_not_seat():
    text = "Row A: 1-2 aisle, 3-5"
    r = parse_text_layout(text)
    assert "A-1" in r["aisles"]
    assert "A-2" in r["aisles"]
    # 3-5 are bookable seats (no category specified)
    assert "A-3" not in r["aisles"]
    assert r["cols"] == 5
