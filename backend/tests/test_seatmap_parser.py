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


def test_offset_keyword_indents_row_and_records_row_offsets():
    """`offset 2` on a row should push its labels 2 columns right without
    affecting the row's seat LABELS (they stay 1-10). Aisles fill the gap."""
    text = """A: 1-12
C-E: offset 2, 1-10"""
    r = parse_text_layout(text)
    assert r["cols"] == 12  # row A is widest
    assert r["row_offsets"] == {"C": 2, "D": 2, "E": 2}
    # Row C: cols 1, 2 are pad aisles. Cols 3-12 are seats (labeled 1-10).
    c_aisles = sorted(a for a in r["aisles"] if a.startswith("C-"))
    assert "C-1" in c_aisles
    assert "C-2" in c_aisles
    # Cols 3-12 should be bookable seats, not aisles
    for col in range(3, 13):
        assert f"C-{col}" not in c_aisles


def test_offset_with_categories_shifts_category_seats_too():
    """Category seats in an offset row should also be column-shifted."""
    text = "A: offset 3, 1-5 disabled"
    r = parse_text_layout(text)
    # disabled labels 1-5 → grid cols 4-8 (1+3 through 5+3)
    assert "A-4" in r["seat_categories"]["disabled"]
    assert "A-8" in r["seat_categories"]["disabled"]
    assert "A-1" not in r["seat_categories"]["disabled"]
    # Cols 1-3 are pad aisles
    assert "A-1" in r["aisles"]
    assert "A-2" in r["aisles"]
    assert "A-3" in r["aisles"]
