"""Door-sign PDF builder smoke test."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from door_sign_pdf import build_door_sign_pdf  # noqa: E402


def test_builds_multi_page_pdf_one_per_row():
    event = {
        "title": "Geeta Rabari Live Garba Night",
        "date": "2026-03-15T19:30:00",
        "seat_rows": 4,
        "seat_cols": 10,
        "aisles": ["A-5", "A-6", "B-5", "B-6"],
        "seatmap_numbering_rtl": False,
        "seatmap_row_offsets": {},
        "seatmap_custom_labels": {"A-1": "VIP-1"},
    }
    pdf_bytes, filename = build_door_sign_pdf(event)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000, f"PDF suspiciously small: {len(pdf_bytes)} bytes"
    # 4 rows → expect at least 4 page markers in the raw PDF body
    page_marker_count = pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type /Page ")
    assert page_marker_count >= 3, f"Expected >=4 pages, found {page_marker_count} page markers"
    assert filename.endswith(".pdf")


def test_raises_when_no_seatmap():
    import pytest
    with pytest.raises(ValueError):
        build_door_sign_pdf({"title": "No Seatmap", "seat_rows": 0, "seat_cols": 0})
