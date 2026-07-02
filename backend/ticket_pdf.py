"""Server-side ticket PDF builder.

Mirrors the layout produced by `/app/frontend/src/lib/ticketPdf.js` so that
the PDF the buyer downloads from their account matches the one attached to
the booking confirmation email — same QR-top-left layout, same dimensions
(A5 landscape, 210 × 148 mm).

Why fpdf2 instead of weasyprint/reportlab?
  - Tiny dep tree, no system libraries.
  - Simple imperative API — easy to keep visually 1:1 with jsPDF.
  - Supports inline base64 PNG images via BytesIO (perfect for QR data URLs).
"""
from __future__ import annotations

import base64
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Static Allsale wordmark shipped with the frontend. Absolute path so this
# works regardless of the CWD the backend was launched from.
_ALLSALE_LOGO_PATH = Path("/app/frontend/public/allsale-logo.png")

# Cheap in-memory cache so we don't hammer a CDN every time a batch of
# tickets emails goes out. Keyed by URL; value is (pdf-safe-bytes, ext).
_EVENT_IMG_CACHE: dict[str, tuple[Optional[bytes], str]] = {}


def _fetch_event_image(url: Optional[str]) -> tuple[Optional[io.BytesIO], str]:
    """Download the organizer's event image (flyer/banner) for embedding.

    Returns (BytesIO or None, extension). Silently falls back to None on
    any error — the ticket still renders without the flyer.
    """
    if not url or not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        return None, ""
    if url in _EVENT_IMG_CACHE:
        cached, ext = _EVENT_IMG_CACHE[url]
        return (io.BytesIO(cached) if cached else None), ext
    try:
        req = Request(url, headers={"User-Agent": "Allsale-Ticket-PDF/1.0"})
        with urlopen(req, timeout=5) as resp:  # noqa: S310
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read(2 * 1024 * 1024)  # cap 2 MB — flyers are usually <500 KB
        if "png" in ctype:
            ext = "png"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = "jpg"
        else:
            # fpdf2 only takes PNG/JPEG. Try to sniff by magic bytes.
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                ext = "png"
            elif data[:3] == b"\xff\xd8\xff":
                ext = "jpg"
            else:
                _EVENT_IMG_CACHE[url] = (None, "")
                return None, ""
        _EVENT_IMG_CACHE[url] = (data, ext)
        return io.BytesIO(data), ext
    except Exception as exc:  # noqa: BLE001
        logger.info(f"[ticket_pdf] event image fetch failed for {url[:80]}: {exc}")
        _EVENT_IMG_CACHE[url] = (None, "")
        return None, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %-d, %Y")
    except Exception:
        return iso


def _fmt_time(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%-I:%M %p")
    except Exception:
        return ""


def _qr_bytes(qr_data_url: Optional[str]) -> Optional[io.BytesIO]:
    """Decode a `data:image/png;base64,...` URL into a BytesIO PNG."""
    if not qr_data_url or not isinstance(qr_data_url, str):
        return None
    m = re.match(r"^data:image/(png|jpeg);base64,(.+)$", qr_data_url, re.DOTALL)
    if not m:
        return None
    try:
        return io.BytesIO(base64.b64decode(m.group(2)))
    except Exception:
        return None


def _filename(title: Optional[str], booking_id: Optional[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "ticket").lower()).strip("-")[:40] or "ticket"
    bid = (booking_id or "")[:8]
    return f"{slug}-{bid}.pdf"


def _latin1(text: Any) -> str:
    """Strip characters Helvetica's Latin-1 encoding can't render.

    fpdf2's built-in fonts only support Latin-1. Without this any emoji or
    smart-quote in a user-typed event title crashes the PDF build. We do a
    best-effort downgrade (smart quotes → straight quotes, em-dash → '-',
    everything else → '?').
    """
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "\u2013": "-",  # en-dash
        "\u2014": "-",  # em-dash
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u00b7": "|",  # middle dot
        "\u00d7": "x",  # multiplication sign
        "\u2026": "...",
    }
    for src, dst in replacements.items():
        s = s.replace(src, dst)
    return s.encode("latin-1", errors="replace").decode("latin-1")


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def build_ticket_pdf(booking: Dict[str, Any]) -> Tuple[bytes, str]:
    """Return (pdf_bytes, filename) for the given booking dict.

    Expected keys: event_title, event_date, venue/event_venue, city/event_city,
    tier_name, seats[], quantity, booking_id, qr_code, amount, currency.
    Missing fields render as `—` or "Free".
    """
    title = _latin1(booking.get("event_title") or "Event")
    event_date = booking.get("event_date") or booking.get("date")
    venue = _latin1(booking.get("venue") or booking.get("event_venue") or "")
    city = _latin1(booking.get("city") or booking.get("event_city") or "")
    tier_name = _latin1(booking.get("tier_name") or "General")
    seats = [_latin1(s) for s in (booking.get("seats") or [])]
    quantity = booking.get("quantity") or 1
    booking_id = _latin1(booking.get("booking_id") or "")
    amount = booking.get("amount")
    currency = (booking.get("currency") or "NZD").upper()

    # A5 landscape — 210 × 148 mm. Same as the frontend helper.
    pdf = FPDF(orientation="L", unit="mm", format="A5")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    page_w, page_h = 210, 148
    margin = 10

    # Brand band along the top — orange to match the app accent.
    pdf.set_fill_color(255, 107, 53)
    pdf.rect(0, 0, page_w, 4, "F")

    # ---- Header row: Allsale logo (left) + event flyer thumb (right) ----
    header_y = margin
    header_h = 12
    if _ALLSALE_LOGO_PATH.exists():
        try:
            # Wordmark is 1254×841 → ~1.49 aspect. Draw at height 10 mm,
            # which keeps width under ~15 mm and never crowds the QR below.
            pdf.image(str(_ALLSALE_LOGO_PATH), x=margin, y=header_y, h=header_h)
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[ticket_pdf] Allsale logo embed failed: {exc}")

    # Event flyer / banner thumb — a small square in the top-right corner
    # so the buyer visually recognises the ticket at a glance. Pulled from
    # booking.event_image (falls back to banner_url / image_url).
    flyer_url = (
        booking.get("event_image")
        or booking.get("banner_url")
        or booking.get("image_url")
    )
    flyer_io, flyer_ext = _fetch_event_image(flyer_url)
    if flyer_io is not None:
        try:
            flyer_size = 20
            flyer_x = page_w - margin - flyer_size
            flyer_y = header_y
            # fpdf2 auto-detects PNG/JPEG from the BytesIO but a bad content
            # type on the CDN can still trip it — swallow silently.
            pdf.image(flyer_io, x=flyer_x, y=flyer_y, w=flyer_size, h=flyer_size)
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[ticket_pdf] flyer image embed failed: {exc}")

    # ---- QR code, anchored below the header on the left ----
    qr_size = 50
    qr_x = margin
    qr_y = header_y + header_h + 6
    qr_io = _qr_bytes(booking.get("qr_code"))
    if qr_io is not None:
        try:
            pdf.image(qr_io, x=qr_x, y=qr_y, w=qr_size, h=qr_size)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[ticket_pdf] QR embed failed: {e}")
            pdf.set_draw_color(220, 220, 220)
            pdf.rect(qr_x, qr_y, qr_size, qr_size)
    else:
        pdf.set_draw_color(220, 220, 220)
        pdf.rect(qr_x, qr_y, qr_size, qr_size)
        pdf.set_xy(qr_x, qr_y + qr_size / 2 - 3)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(qr_size, 5, "QR unavailable", align="C")

    pdf.set_xy(qr_x, qr_y + qr_size + 2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(qr_size, 5, "Scan at the door", align="C")

    # ---- Right column ----
    right_x = qr_x + qr_size + 12
    right_w = page_w - right_x - margin

    # (The "ALLSALE EVENTS | E-TICKET" caption row lived here previously —
    # dropped in favour of the Allsale wordmark logo now shown in the header.)

    pdf.set_xy(right_x, qr_y + 2)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 20, 20)
    # multi_cell wraps long event titles; cap to 2 lines via manual truncation.
    safe_title = title[:120]
    pdf.multi_cell(right_w, 8, safe_title, align="L")

    pdf.set_xy(right_x, qr_y + 22)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    date_str = _fmt_date(event_date)
    time_str = _fmt_time(event_date)
    pdf.cell(right_w, 5, f"{date_str}{'  |  ' + time_str if time_str else ''}")

    pdf.set_xy(right_x, qr_y + 28)
    pdf.set_text_color(60, 60, 60)
    venue_str = ", ".join(p for p in (venue, city) if p) or "-"
    pdf.cell(right_w, 5, venue_str)

    # Divider
    pdf.set_draw_color(220, 220, 220)
    pdf.line(right_x, qr_y + 36, page_w - margin, qr_y + 36)

    # 2x2 info grid
    col_w = right_w / 2
    r1y = qr_y + 42
    r2y = qr_y + 54

    def _cell(label: str, value: str, x: float, y: float) -> None:
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(col_w, 3, label.upper())
        pdf.set_xy(x, y + 4)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(col_w, 5, value[:60])

    _cell("Type", tier_name, right_x, r1y)
    seats_or_qty = ", ".join(seats) if seats else f"x {quantity}"
    _cell("Seats" if seats else "Quantity", seats_or_qty, right_x + col_w, r1y)
    _cell("Booking ID", booking_id or "-", right_x, r2y)
    if isinstance(amount, (int, float)):
        total = "Free" if amount == 0 else f"{currency} {amount:.2f}"
        _cell("Total paid", total, right_x + col_w, r2y)

    # Footer
    pdf.set_draw_color(230, 230, 230)
    pdf.line(margin, page_h - 18, page_w - margin, page_h - 18)
    pdf.set_xy(margin, page_h - 14)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(
        page_w - margin * 2,
        5,
        "Present this QR at the venue door. Tickets are non-transferable unless transferred via your Allsale account.",
    )
    pdf.set_xy(margin, page_h - 9)
    pdf.cell(page_w - margin * 2, 5, "support@allsale.events  |  allsale.events")

    # fpdf2 returns a bytearray which Resend's base64 encoder accepts after
    # converting to bytes.
    pdf_bytes = bytes(pdf.output())
    return pdf_bytes, _filename(title, booking_id)
