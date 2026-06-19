"""Door-sign PDF builder — one A4 portrait page per theatre row that ushers
stick at the start of each aisle.

Layout per page (portrait, A4):
  • Event title (small, bottom-left)
  • Date (small, bottom-right)
  • The row letter rendered ENORMOUSLY in the middle, anchored top
  • The full seat sequence ("1  2  3  ·  4  5  6  ·  7  8  9  10")
    with `·` for aisles, custom labels honoured
  • Footer: "Allsale Events"

Reuses the latin1 sanitiser + Helvetica from `ticket_pdf.py` for consistency.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fpdf import FPDF

from ticket_pdf import _latin1, _fmt_date

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def build_door_sign_pdf(event: Dict[str, Any]) -> Tuple[bytes, str]:
    """Build a multi-page PDF — one page per row of the seatmap.

    Returns (pdf_bytes, filename). The event dict must include seat_rows,
    seat_cols and may include aisles, seatmap_numbering_rtl, seatmap_row_offsets,
    seatmap_custom_labels.
    """
    rows = int(event.get("seat_rows") or 0)
    cols = int(event.get("seat_cols") or 0)
    aisles = set(event.get("aisles") or [])
    custom_labels = event.get("seatmap_custom_labels") or {}
    row_offsets = event.get("seatmap_row_offsets") or {}
    numbering_rtl = bool(event.get("seatmap_numbering_rtl"))
    title = _latin1(event.get("title") or "Event")
    date_str = _fmt_date(event.get("date"))

    if rows <= 0 or cols <= 0:
        raise ValueError("Event has no seatmap to print door signs for")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    page_w, page_h = 210, 297
    margin = 12

    for r in range(rows):
        row_letter = LETTERS[r]
        row_offset = int(row_offsets.get(row_letter, 0) or 0)
        pdf.add_page()

        # Top orange band — matches the brand and is highly visible across a room.
        pdf.set_fill_color(255, 107, 53)
        pdf.rect(0, 0, page_w, 6, "F")

        # Tiny brand mark
        pdf.set_xy(margin, 11)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(255, 107, 53)
        pdf.cell(page_w - 2 * margin, 5, "ALLSALE EVENTS  |  DOOR SIGN")

        # Event title
        pdf.set_xy(margin, 18)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(page_w - 2 * margin, 7, title[:90], align="L")

        # Date
        pdf.set_xy(margin, 32)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(page_w - 2 * margin, 5, date_str)

        # HUGE row letter — anchored in the upper third
        pdf.set_xy(0, 80)
        pdf.set_font("Helvetica", "B", 240)
        pdf.set_text_color(255, 107, 53)
        pdf.cell(page_w, 100, f"ROW {row_letter}", align="C")

        # "Seats in this row" label
        pdf.set_xy(margin, 195)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(page_w - 2 * margin, 5, "SEATS IN THIS ROW (HOUSE LEFT  =>  HOUSE RIGHT)")

        # Sequence — render seats in visual order so the printed strip matches
        # exactly what the usher sees when they look down the row.
        tokens: List[str] = []
        for c in range(cols):
            seat_number = cols - c if numbering_rtl else c + 1
            sid = f"{row_letter}-{seat_number}"
            if sid in aisles:
                tokens.append("·")  # aisle gap — rendered as a dot
            else:
                custom = custom_labels.get(sid)
                if custom:
                    tokens.append(_latin1(custom))
                else:
                    display = seat_number - row_offset
                    tokens.append(str(display) if display > 0 else str(seat_number))

        # Render the seat sequence as wrapped chips. Use a smaller font so 30+
        # seats fit on one line; multi_cell handles overflow to a new line.
        pdf.set_xy(margin, 205)
        pdf.set_font("Helvetica", "", 18)
        pdf.set_text_color(20, 20, 20)
        joined = "   ".join(tokens)
        pdf.multi_cell(page_w - 2 * margin, 9, joined, align="C")

        # Footer
        pdf.set_xy(margin, page_h - 14)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            page_w - 2 * margin,
            5,
            f"Page {r + 1} of {rows}  |  Stick at the head of row {row_letter}",
            align="C",
        )

    import re
    slug = re.sub(r"[^a-z0-9]+", "-", (event.get("title") or "event").lower()).strip("-")[:40] or "event"
    filename = f"door-signs-{slug}.pdf"
    return bytes(pdf.output()), filename
