"""Transactional email service powered by Resend.

Single entry point: `send_template(template, to, ctx, db)` looks up an HTML+text
renderer, dispatches via Resend SDK on a thread (non-blocking), and writes a
record to the `email_logs` collection for auditing.

All templates share a consistent dark theme + hot-coral (#FF4F00) brand layout
with inline styles so they survive Gmail / Outlook / Apple Mail rendering.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

try:
    import resend  # type: ignore
    _RESEND_AVAILABLE = True
except Exception as _resend_import_err:  # pragma: no cover
    resend = None  # type: ignore
    _RESEND_AVAILABLE = False

logger = logging.getLogger("aura.emails")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY") or ""
SENDER_EMAIL = os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL") or "https://allsale.events"
SENDER_NAME = "Allsale Events"

if _RESEND_AVAILABLE and RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


# ---------------------------------------------------------------------------
# Shared layout
# ---------------------------------------------------------------------------
BRAND_COLOR = "#FF4F00"
BG = "#0B0B0E"
BG_CARD = "#15151B"
TEXT = "#F5F5F0"
TEXT_MUTED = "#9A9AA3"
BORDER = "#26262E"


def _layout(title: str, preheader: str, body_html: str, cta_label: Optional[str] = None, cta_url: Optional[str] = None) -> str:
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <tr><td align="left" style="padding:24px 32px 0 32px;">
          <a href="{cta_url}" style="display:inline-block;background:{BRAND_COLOR};color:#000;font-weight:600;
            font-family:Helvetica,Arial,sans-serif;font-size:14px;padding:14px 22px;border-radius:9999px;
            text-decoration:none;letter-spacing:0.3px;">{cta_label}</a>
        </td></tr>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:Helvetica,Arial,sans-serif;color:{TEXT};">
<span style="display:none;font-size:1px;color:transparent;max-height:0;max-width:0;opacity:0;overflow:hidden;">{preheader}</span>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{BG};padding:32px 16px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background:{BG_CARD};border:1px solid {BORDER};border-radius:16px;overflow:hidden;">
      <tr><td style="padding:28px 32px 6px 32px;">
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:22px;letter-spacing:1px;color:{TEXT};">
          Allsale <span style="color:{BRAND_COLOR};">·</span> Events
        </div>
      </td></tr>
      <tr><td style="padding:18px 32px 0 32px;">
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:30px;line-height:1.15;color:{TEXT};margin:6px 0 14px 0;">{title}</div>
      </td></tr>
      <tr><td style="padding:0 32px 8px 32px;font-size:15px;line-height:1.65;color:{TEXT_MUTED};">{body_html}</td></tr>
      {cta_html}
      <tr><td style="padding:36px 32px 28px 32px;font-size:12px;color:{TEXT_MUTED};border-top:1px solid {BORDER};margin-top:24px;">
        You're receiving this because you have an Allsale Events account.<br>
        © {datetime.now().year} Allsale Events · <a href="{APP_PUBLIC_URL}" style="color:{BRAND_COLOR};text-decoration:none;">{APP_PUBLIC_URL.replace('https://','').replace('http://','')}</a>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def _text_fallback(lines: list[str]) -> str:
    return "\n".join(lines) + f"\n\n— Allsale Events\n{APP_PUBLIC_URL}\n"


def _money(amount: float, currency: str = "USD") -> str:
    return f"${amount:,.2f} {currency}"


# ---------------------------------------------------------------------------
# Templates: each returns (subject, html, text)
# ---------------------------------------------------------------------------
def _t_booking_confirmation(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    seats = ", ".join(ctx.get("seats") or []) if ctx.get("seats") else ctx.get("tier_name", "General")
    body = f"""
    <p style="color:{TEXT};">Hey {ctx.get('user_name', 'there')}, your tickets are confirmed.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td>
          <td style="text-align:right;color:{TEXT};font-weight:600;">{ctx['event_title']}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">WHEN</td>
          <td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_date','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">VENUE</td>
          <td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('venue','')}{', ' + ctx['city'] if ctx.get('city') else ''}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">SEATS</td>
          <td style="text-align:right;color:{TEXT};padding-top:8px;">{seats} × {ctx.get('quantity', 1)}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">PAID</td>
          <td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{_money(ctx.get('amount', 0))}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">BOOKING ID</td>
          <td style="text-align:right;color:{TEXT};font-family:Menlo,Monaco,monospace;font-size:12px;padding-top:8px;">{ctx['booking_id']}</td></tr>
    </table>
    <p style="margin-top:18px;color:{TEXT_MUTED};">Your QR ticket lives in your profile — show it at the door for instant entry.</p>
    """
    subject = f"You're in — {ctx['event_title']}"
    html = _layout(subject, f"Booking confirmed · {ctx['booking_id']}", body, "View your ticket", f"{APP_PUBLIC_URL}/profile")
    text = _text_fallback([
        f"You're in — {ctx['event_title']}",
        f"When: {ctx.get('event_date','')}",
        f"Venue: {ctx.get('venue','')}, {ctx.get('city','')}",
        f"Seats: {seats} x {ctx.get('quantity', 1)}",
        f"Paid: {_money(ctx.get('amount', 0))}",
        f"Booking ID: {ctx['booking_id']}",
        f"View ticket: {APP_PUBLIC_URL}/profile",
    ])
    return subject, html, text


def _t_hold_expired(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')} — your seats for
    <strong>{ctx['event_title']}</strong> were released because the 10-minute hold expired.</p>
    <p>No charge was made. You can grab seats again if they're still available.</p>
    """
    subject = f"Your hold expired — {ctx['event_title']}"
    html = _layout("Your hold expired", "Seats released — try again", body, "Book again", f"{APP_PUBLIC_URL}/events/{ctx['event_id']}")
    text = _text_fallback([
        f"Your 10-minute seat hold for {ctx['event_title']} expired and the seats were released.",
        f"You can try again: {APP_PUBLIC_URL}/events/{ctx['event_id']}",
    ])
    return subject, html, text


def _t_refund_issued(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')}, a refund has been issued for your booking.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};">{ctx['event_title']}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">BOOKING ID</td><td style="text-align:right;color:{TEXT};font-family:Menlo,Monaco,monospace;font-size:12px;padding-top:8px;">{ctx['booking_id']}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">REFUND</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{_money(ctx.get('amount', 0))}</td></tr>
    </table>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Funds typically settle in 5–10 business days depending on your bank.</p>
    """
    subject = f"Refund issued — {ctx['event_title']}"
    html = _layout("Refund issued", f"{_money(ctx.get('amount', 0))} refunded", body)
    text = _text_fallback([
        f"Refund issued for {ctx['event_title']}",
        f"Booking: {ctx['booking_id']}",
        f"Amount: {_money(ctx.get('amount', 0))}",
        "Funds typically settle in 5–10 business days.",
    ])
    return subject, html, text


def _t_organizer_event_approved(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    body = f"""
    <p style="color:{TEXT};">Good news, {ctx.get('organizer_name','organizer')} — your event is live on Allsale Events.</p>
    <p style="color:{TEXT};font-size:18px;margin-top:4px;"><strong>{ctx['event_title']}</strong></p>
    <p>It's now discoverable to attendees and ready to start selling tickets.</p>
    """
    subject = f"Approved & live: {ctx['event_title']}"
    html = _layout("Your event is live", "Approved by Allsale Events moderation", body, "View event page", f"{APP_PUBLIC_URL}/events/{ctx['event_id']}")
    text = _text_fallback([
        f"Your event '{ctx['event_title']}' has been approved and is live on Allsale Events.",
        f"View: {APP_PUBLIC_URL}/events/{ctx['event_id']}",
    ])
    return subject, html, text


def _t_organizer_payout_issued(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('organizer_name','organizer')}, a payout has been wired to you.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">AMOUNT</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;">{_money(ctx.get('amount', 0))}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">REFERENCE</td><td style="text-align:right;color:{TEXT};font-family:Menlo,Monaco,monospace;font-size:12px;padding-top:8px;">{ctx.get('payout_id','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">PERIOD</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('period','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">BOOKINGS</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('bookings_count', 0)}</td></tr>
    </table>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Net of platform commission and processing fees. See dashboard for the full breakdown.</p>
    """
    subject = f"Payout sent: {_money(ctx.get('amount', 0))}"
    html = _layout("Payout sent", f"{_money(ctx.get('amount', 0))} on the way", body, "Open payouts dashboard", f"{APP_PUBLIC_URL}/organizer/payouts")
    text = _text_fallback([
        f"Payout sent: {_money(ctx.get('amount', 0))}",
        f"Reference: {ctx.get('payout_id','')}",
        f"Period: {ctx.get('period','')}",
        f"Bookings: {ctx.get('bookings_count', 0)}",
        f"Dashboard: {APP_PUBLIC_URL}/organizer/payouts",
    ])
    return subject, html, text


def _t_waitlist_spot_opened(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')} — a spot just opened for
    <strong>{ctx['event_title']}</strong>.</p>
    <p>You have <strong style="color:{BRAND_COLOR};">15 minutes</strong> to claim it before it rolls to the next person on the waitlist.</p>
    """
    subject = f"⏳ Spot opened — {ctx['event_title']}"
    html = _layout("A spot just opened", "Claim within 15 minutes", body, "Claim my spot", f"{APP_PUBLIC_URL}/events/{ctx['event_id']}?waitlist={ctx.get('waitlist_token','')}")
    text = _text_fallback([
        f"A spot just opened for {ctx['event_title']}.",
        f"Claim within 15 minutes: {APP_PUBLIC_URL}/events/{ctx['event_id']}?waitlist={ctx.get('waitlist_token','')}",
    ])
    return subject, html, text


TEMPLATES: Dict[str, Callable[[Dict[str, Any]], tuple[str, str, str]]] = {
    "booking_confirmation": _t_booking_confirmation,
    "hold_expired": _t_hold_expired,
    "refund_issued": _t_refund_issued,
    "organizer_event_approved": _t_organizer_event_approved,
    "organizer_payout_issued": _t_organizer_payout_issued,
    "waitlist_spot_opened": _t_waitlist_spot_opened,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def send_template(template: str, to: str, ctx: Dict[str, Any], db=None) -> Dict[str, Any]:
    """Render and dispatch a template. Always returns a result dict; never raises.

    Logs to `email_logs` collection (if db provided) with status: queued | sent | failed | skipped.
    """
    log_id = uuid4().hex[:16]
    now_iso = datetime.now(timezone.utc).isoformat()
    base = {"log_id": log_id, "template": template, "to": to, "created_at": now_iso, "context_summary": _safe_summary(ctx)}

    if not _RESEND_AVAILABLE or not RESEND_API_KEY:
        logger.warning(f"[email] resend unavailable or RESEND_API_KEY not set — skipped {template} to {to}")
        if db is not None:
            await db.email_logs.insert_one({**base, "status": "skipped", "reason": "resend_unavailable"})
        return {"status": "skipped", "log_id": log_id, "reason": "resend_unavailable"}

    builder = TEMPLATES.get(template)
    if not builder:
        logger.error(f"[email] unknown template '{template}'")
        if db is not None:
            await db.email_logs.insert_one({**base, "status": "failed", "reason": "unknown_template"})
        return {"status": "failed", "log_id": log_id, "reason": "unknown_template"}

    try:
        subject, html, text = builder(ctx)
    except Exception as e:
        logger.error(f"[email] template render failed for {template}: {e}")
        if db is not None:
            await db.email_logs.insert_one({**base, "status": "failed", "reason": f"render_error: {e}"})
        return {"status": "failed", "log_id": log_id, "reason": str(e)}

    params = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }

    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        email_id = result.get("id") if isinstance(result, dict) else None
        logger.info(f"[email] sent {template} → {to} (id={email_id})")
        if db is not None:
            await db.email_logs.insert_one({**base, "status": "sent", "subject": subject, "resend_id": email_id})
        return {"status": "sent", "log_id": log_id, "resend_id": email_id}
    except Exception as e:
        logger.error(f"[email] send failed {template} → {to}: {e}")
        if db is not None:
            await db.email_logs.insert_one({**base, "status": "failed", "reason": str(e)[:500], "subject": subject})
        return {"status": "failed", "log_id": log_id, "reason": str(e)}


def send_template_fireforget(template: str, to: str, ctx: Dict[str, Any], db=None) -> asyncio.Task:
    """Schedule send without awaiting. Use when caller shouldn't block on email I/O."""
    return asyncio.create_task(send_template(template, to, ctx, db))


def _safe_summary(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Pull only short scalar/string fields from ctx (avoid huge blobs in logs)."""
    out = {}
    for k, v in ctx.items():
        if isinstance(v, (str, int, float, bool)) and len(str(v)) < 200:
            out[k] = v
        elif isinstance(v, list) and len(v) < 10:
            out[k] = v
    return out
