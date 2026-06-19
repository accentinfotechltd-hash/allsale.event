/**
 * Ticket PDF builder.
 *
 * Generates a print-ready A5 landscape PDF with the QR code anchored to the
 * top-left corner (per user request), event/booking details on the right and
 * a help footer at the bottom. Uses jsPDF — no headless browser or backend
 * needed; everything runs in the user's tab.
 *
 * Why client-side over server-side rendering?
 *  - Zero backend coupling: the QR + booking payload already live in the page.
 *  - Instant feedback — no upload/wait round-trip.
 *  - Same data the customer sees → no risk of stale info.
 */
import { jsPDF } from "jspdf";

const A5_LANDSCAPE_MM = { w: 210, h: 148 };

function safeText(v, fallback = "—") {
  if (v === null || v === undefined) return fallback;
  return String(v);
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * @param {object} booking
 * @param {string} booking.event_title
 * @param {string} [booking.event_date]
 * @param {string} [booking.event_venue]
 * @param {string} [booking.event_city]
 * @param {string} [booking.tier_name]
 * @param {string[]} [booking.seats]
 * @param {number} [booking.quantity]
 * @param {string} [booking.booking_id]
 * @param {string} [booking.qr_code]   — data URL (image/png base64)
 * @param {number} [booking.amount]
 * @param {string} [booking.currency]
 */
export function downloadTicketPdf(booking) {
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a5" });
  const { w, h } = A5_LANDSCAPE_MM;
  const margin = 10;

  // Brand band along the very top — orange accent matches Allsale theme.
  doc.setFillColor(255, 107, 53);
  doc.rect(0, 0, w, 4, "F");

  // QR code — TOP LEFT, ~55mm square so it scans cleanly even after a phone
  // photo. We assume `qr_code` is a base64 PNG data URL. Fall back to a
  // labelled empty box if it's missing (avoids a crash on legacy bookings).
  const qrSize = 55;
  const qrX = margin;
  const qrY = margin + 4;
  if (booking.qr_code && booking.qr_code.startsWith("data:image")) {
    try {
      doc.addImage(booking.qr_code, "PNG", qrX, qrY, qrSize, qrSize);
    } catch {
      doc.setDrawColor(220);
      doc.rect(qrX, qrY, qrSize, qrSize);
      doc.setFontSize(9);
      doc.text("QR unavailable", qrX + 4, qrY + qrSize / 2);
    }
  } else {
    doc.setDrawColor(220);
    doc.rect(qrX, qrY, qrSize, qrSize);
    doc.setFontSize(9);
    doc.text("QR unavailable", qrX + 4, qrY + qrSize / 2);
  }
  // Scan label
  doc.setFontSize(8);
  doc.setTextColor(120);
  doc.text("Scan at the door", qrX + qrSize / 2, qrY + qrSize + 5, { align: "center" });

  // RIGHT SIDE — event details
  const rightX = qrX + qrSize + 12;

  // "ALLSALE EVENTS" tag
  doc.setFontSize(8);
  doc.setTextColor(255, 107, 53);
  doc.text("ALLSALE EVENTS  ·  E-TICKET", rightX, qrY + 4);

  // Title
  doc.setFontSize(20);
  doc.setTextColor(20);
  const titleLines = doc.splitTextToSize(safeText(booking.event_title, "Event"), w - rightX - margin);
  doc.text(titleLines.slice(0, 2), rightX, qrY + 14);

  // Date + venue
  doc.setFontSize(10);
  doc.setTextColor(80);
  const datePart = fmtDate(booking.event_date);
  const timePart = fmtTime(booking.event_date);
  doc.text(`${datePart}${timePart ? "  ·  " + timePart : ""}`, rightX, qrY + 28);

  doc.setFontSize(10);
  doc.setTextColor(60);
  const venue = [booking.event_venue, booking.event_city].filter(Boolean).join(", ") || "—";
  doc.text(venue, rightX, qrY + 34);

  // Divider
  doc.setDrawColor(220);
  doc.line(rightX, qrY + 39, w - margin, qrY + 39);

  // 4-cell info grid: Type / Seats or Qty / Booking ID / Total
  const colW = (w - rightX - margin) / 2;
  const r1y = qrY + 46;
  const r2y = qrY + 58;
  const drawCell = (label, value, x, y) => {
    doc.setFontSize(7);
    doc.setTextColor(150);
    doc.text(label.toUpperCase(), x, y);
    doc.setFontSize(11);
    doc.setTextColor(20);
    const lines = doc.splitTextToSize(safeText(value), colW - 4);
    doc.text(lines.slice(0, 2), x, y + 5);
  };
  drawCell("Type", booking.tier_name || "General", rightX, r1y);
  const seatsOrQty = booking.seats && booking.seats.length
    ? booking.seats.join(", ")
    : `× ${booking.quantity ?? 1}`;
  drawCell(booking.seats?.length ? "Seats" : "Quantity", seatsOrQty, rightX + colW, r1y);
  drawCell("Booking ID", booking.booking_id || "—", rightX, r2y);
  if (typeof booking.amount === "number") {
    const total = booking.amount === 0 ? "Free" : `${booking.currency || "NZD"} ${booking.amount.toFixed(2)}`;
    drawCell("Total paid", total, rightX + colW, r2y);
  }

  // Footer — bottom of the page
  doc.setDrawColor(230);
  doc.line(margin, h - 18, w - margin, h - 18);
  doc.setFontSize(8);
  doc.setTextColor(140);
  doc.text(
    "Present this QR at the venue door. Tickets are non-transferable unless transferred via your Allsale account.",
    margin,
    h - 12,
  );
  doc.text("support@allsale.events  ·  allsale.events", margin, h - 7);

  const filenameBase = (booking.event_title || "ticket")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40) || "ticket";
  doc.save(`${filenameBase}-${(booking.booking_id || "").slice(0, 8)}.pdf`);
}
