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
from typing import Any, Callable, Dict, List, Optional
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
# Reply-To address: where replies to ticket / confirmation / support emails
# land. We send FROM our verified domain (required by Resend / spam filters)
# but customers' "Reply" button hits this human-monitored mailbox — typically
# a Gmail address the support team checks daily.
REPLY_TO_EMAIL = os.environ.get("REPLY_TO_EMAIL") or ""
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


def _t_team_invitation(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent when an organizer adds someone to their event team.

    Different copy depending on whether the recipient already has an account.
    """
    role_label = {
        "co_organizer": "Co-organizer (full access)",
        "manager": "Manager (edit + analytics + check-in)",
        "door_staff": "Door staff (check-in only)",
    }.get(ctx.get("role"), ctx.get("role", "Team member"))
    scope_label = "all your events" if ctx.get("scope") == "organization" else ctx.get("event_title", "the event")
    new_user = bool(ctx.get("new_user"))
    cta_label = "Create my account" if new_user else "Open my dashboard"
    cta_url = f"{APP_PUBLIC_URL}/signup?email={ctx.get('email','')}" if new_user else f"{APP_PUBLIC_URL}/organizer"

    if new_user:
        note_html = f'<p style="color:{TEXT_MUTED};">You will need to create an account with this email first.</p>'
    else:
        note_html = f'<p style="color:{TEXT_MUTED};">Just sign in and head to your Organizer dashboard.</p>'

    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('name','there')} — <strong>{ctx.get('inviter_name','an organizer')}</strong> has added you as a <strong style="color:{BRAND_COLOR};">{role_label}</strong> on Allsale Events.</p>
    <p style="color:{TEXT};">You now have access to <strong>{scope_label}</strong>.</p>
    {note_html}
    """
    subject = f"You're on the team for {scope_label}"
    html = _layout("Team invitation", "Allsale Events", body, cta_label, cta_url)
    text = _text_fallback([
        f"{ctx.get('inviter_name','An organizer')} added you as {role_label} on Allsale Events.",
        f"Access: {scope_label}",
        f"Sign in / sign up: {cta_url}",
    ])
    return subject, html, text


TEMPLATES: Dict[str, Callable[[Dict[str, Any]], tuple[str, str, str]]] = {
    "booking_confirmation": _t_booking_confirmation,
    "hold_expired": _t_hold_expired,
    "refund_issued": _t_refund_issued,
    "organizer_event_approved": _t_organizer_event_approved,
    "organizer_payout_issued": _t_organizer_payout_issued,
    "organizer_contact_message": lambda ctx: _t_organizer_contact_message(ctx),
    "waitlist_spot_opened": _t_waitlist_spot_opened,
    "team_invitation": _t_team_invitation,
    "event_reminder_24h": lambda ctx: _t_event_reminder_24h(ctx),
    "weekly_digest": lambda ctx: _t_weekly_digest(ctx),
    "new_event_announcement": lambda ctx: _t_new_event_announcement(ctx),
    "admin_blast": lambda ctx: _t_admin_blast(ctx),
    "admin_new_event_submitted": lambda ctx: _t_admin_new_event_submitted(ctx),
    "organizer_stripe_setup_nudge": lambda ctx: _t_organizer_stripe_setup_nudge(ctx),
    "follower_new_event": lambda ctx: _t_follower_new_event(ctx),
    "follower_weekly_digest": lambda ctx: _t_follower_weekly_digest(ctx),
    "ticket_transfer_offer": lambda ctx: _t_ticket_transfer_offer(ctx),
    "admin_webhook_silent_failure": lambda ctx: _t_admin_webhook_silent_failure(ctx),
    "organizer_welcome_1_signup": lambda ctx: _t_organizer_welcome_1_signup(ctx),
    "organizer_welcome_2_publish": lambda ctx: _t_organizer_welcome_2_publish(ctx),
    "organizer_welcome_3_first_sale": lambda ctx: _t_organizer_welcome_3_first_sale(ctx),
    "organizer_welcome_4_reactivate": lambda ctx: _t_organizer_welcome_4_reactivate(ctx),
    "gift_card_delivered": lambda ctx: _t_gift_card_delivered(ctx),
    "boost_recap": lambda ctx: _t_boost_recap(ctx),
    "event_recap": lambda ctx: _t_event_recap(ctx),
    "admin_created_account": lambda ctx: _t_admin_created_account(ctx),
    "admin_created_event_for_you": lambda ctx: _t_admin_created_event_for_you(ctx),
    "admin_new_user_signup": lambda ctx: _t_admin_new_user_signup(ctx),
    "admin_new_booking": lambda ctx: _t_admin_new_booking(ctx),
    "admin_new_enquiry": lambda ctx: _t_admin_new_enquiry(ctx),
    "organizer_new_sale": lambda ctx: _t_organizer_new_sale(ctx),
    "admin_message_to_organizer": lambda ctx: _t_admin_message_to_organizer(ctx),
    "organizer_message_to_admin": lambda ctx: _t_organizer_message_to_admin(ctx),
    "blog_new_post": lambda ctx: _t_blog_new_post(ctx),
    "marketing_partner_statement": lambda ctx: _t_marketing_partner_statement(ctx),
    "marketing_partner_invitation": lambda ctx: _t_marketing_partner_invitation(ctx),
}


def _t_marketing_partner_invitation(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Welcome email when admin grants partner portal access.

    ctx fields:
      - partner_name (required)
      - login_email (required)
      - temp_password (required) — admin-set; we tell the partner to change it
      - commission_pct (required, float)
      - is_new_account (bool) — controls copy ("we created an account" vs "we linked your existing account")
    """
    login_url = f"{APP_PUBLIC_URL}/login?next=/partner"
    portal_url = f"{APP_PUBLIC_URL}/partner"
    is_new = bool(ctx.get("is_new_account", True))
    pct = ctx.get("commission_pct") or 0

    intro = (
        f"We've set up a partner account for you with the email <strong>{ctx['login_email']}</strong>."
        if is_new
        else f"We've linked your existing Allsale account (<strong>{ctx['login_email']}</strong>) to your partner profile."
    )

    creds_block = (
        f"""
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin:18px 0;">
          <tr>
            <td style="padding:16px;border:1px solid {BORDER};border-radius:10px;background:rgba(15,42,58,0.04);">
              <div style="font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.18em;margin-bottom:4px;">Sign in</div>
              <div style="font-size:14px;color:{TEXT};margin-bottom:8px;">
                <strong>Email:</strong> {ctx['login_email']}<br />
                <strong>Temporary password:</strong>
                <code style="background:#fff;border:1px solid {BORDER};padding:2px 6px;border-radius:4px;font-size:13px;">{ctx['temp_password']}</code>
              </div>
              <div style="font-size:12px;color:{TEXT_MUTED};">
                Please change your password the first time you log in — Settings → Account.
              </div>
            </td>
          </tr>
        </table>
        """
        if is_new
        else ""
    )

    body = f"""
    <p style="color:{TEXT_MUTED};font-size:12px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 6px;">
      Allsale Events · Partner program
    </p>
    <h2 style="color:{TEXT};font-family:Georgia,serif;font-size:24px;margin:0 0 14px;line-height:1.2;">
      Welcome to the program, {ctx['partner_name']}.
    </h2>
    <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0 0 14px;">
      {intro}
      You'll earn <strong style="color:{TEXT};">{pct}%</strong> of platform commission on every paid booking
      from the organizers we attach to you — recurring forever, paid out in batches.
    </p>
    {creds_block}
    <p style="color:{TEXT_MUTED};font-size:14px;line-height:1.6;margin:0 0 14px;">
      Your partner portal lives at
      <a href="{portal_url}" style="color:#F08A2A;text-decoration:underline;">{portal_url}</a>.
      You'll see your lifetime earnings, unpaid balance, attached organizers, and an
      auto-updating ledger of every commissionable booking.
    </p>
    <p style="color:{TEXT_MUTED};font-size:14px;line-height:1.6;margin:0;">
      Any questions? Just reply to this email — we read every message.
    </p>
    """
    subject = f"Welcome to the Allsale partner program — sign-in details inside"
    html = _layout(
        f"Welcome, {ctx['partner_name']}",
        f"You earn {pct}% on every paid booking.",
        body,
        "Open your partner portal",
        login_url,
    )
    text_lines = [
        f"Welcome to the Allsale partner program, {ctx['partner_name']}.",
        f"You earn {pct}% of platform commission on every paid booking from attached organizers.",
        "",
        f"Sign in: {login_url}",
        f"Email: {ctx['login_email']}",
    ]
    if is_new:
        text_lines.append(f"Temporary password: {ctx['temp_password']} (please change it on first login)")
    text_lines += ["", f"Your portal: {portal_url}", "", "Reply to this email with any questions."]
    text = _text_fallback(text_lines)
    return subject, html, text


def _t_marketing_partner_statement(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Monthly P&L statement for a marketing lead partner.

    ctx fields:
      - partner_name (required)
      - period_label (e.g. "June 2026")
      - currency (default "NZD")
      - lifetime_earnings, period_earnings, unpaid_balance, organizer_count
      - earnings (list of {date, event_title, earning_amount, status})
    """
    currency = ctx.get("currency") or "NZD"

    def _fmt(n):
        try:
            return f"{currency} {float(n):,.2f}"
        except Exception:
            return f"{currency} 0.00"

    rows_html = "".join(
        f"<tr>"
        f'<td style="padding:8px 6px;border-bottom:1px solid {BORDER};font-size:13px;color:{TEXT_MUTED};">{e.get("date","")}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid {BORDER};font-size:13px;color:{TEXT};">{e.get("event_title","")}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid {BORDER};font-size:13px;color:{TEXT};text-align:right;">{_fmt(e.get("earning_amount"))}</td>'
        f'<td style="padding:8px 6px;border-bottom:1px solid {BORDER};font-size:11px;color:{TEXT_MUTED};text-transform:capitalize;">{e.get("status","")}</td>'
        f"</tr>"
        for e in (ctx.get("earnings") or [])[:20]
    ) or (
        f'<tr><td colspan="4" style="padding:16px;text-align:center;color:{TEXT_MUTED};">'
        f"No commissionable bookings in this period.</td></tr>"
    )

    body = f"""
    <p style="color:{TEXT_MUTED};font-size:12px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 6px;">
      Allsale Events · Partner statement · {ctx.get('period_label', '')}
    </p>
    <h2 style="color:{TEXT};font-family:Georgia,serif;font-size:24px;margin:0 0 18px;line-height:1.2;">
      Hi {ctx['partner_name']}, here's your latest statement.
    </h2>

    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin:0 0 22px;">
      <tr>
        <td style="padding:14px;border:1px solid {BORDER};border-radius:8px;width:33%;vertical-align:top;">
          <div style="font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.16em;margin-bottom:4px;">This period</div>
          <div style="font-size:18px;color:{TEXT};font-weight:600;">{_fmt(ctx.get('period_earnings'))}</div>
        </td>
        <td style="width:8px;"></td>
        <td style="padding:14px;border:1px solid {BORDER};border-radius:8px;width:33%;vertical-align:top;">
          <div style="font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.16em;margin-bottom:4px;">Unpaid balance</div>
          <div style="font-size:18px;color:#F08A2A;font-weight:600;">{_fmt(ctx.get('unpaid_balance'))}</div>
        </td>
        <td style="width:8px;"></td>
        <td style="padding:14px;border:1px solid {BORDER};border-radius:8px;width:33%;vertical-align:top;">
          <div style="font-size:10px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.16em;margin-bottom:4px;">Lifetime</div>
          <div style="font-size:18px;color:{TEXT};font-weight:600;">{_fmt(ctx.get('lifetime_earnings'))}</div>
        </td>
      </tr>
    </table>

    <h3 style="color:{TEXT};font-family:Georgia,serif;font-size:16px;margin:0 0 8px;">Recent earnings</h3>
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;margin:0 0 16px;">
      <thead>
        <tr>
          <th style="text-align:left;padding:6px;font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Date</th>
          <th style="text-align:left;padding:6px;font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Event</th>
          <th style="text-align:right;padding:6px;font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Earning</th>
          <th style="text-align:left;padding:6px;font-size:11px;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Status</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>

    <p style="color:{TEXT_MUTED};font-size:13px;margin:18px 0 0;">
      You have <strong>{ctx.get('organizer_count', 0)}</strong> attached organizer{'s' if (ctx.get('organizer_count') or 0) != 1 else ''}.
      Reply to this email if anything looks off and we'll sort it.
    </p>
    """
    subject = f"Your Allsale partner statement — {ctx.get('period_label', '')}"
    html = _layout(
        f"Statement {ctx.get('period_label','')}",
        f"Unpaid balance: {_fmt(ctx.get('unpaid_balance'))}",
        body,
        "Talk to Allsale",
        f"mailto:partners@allsale.events?subject=Partner%20statement%20{ctx.get('partner_name','')}",
    )
    text = _text_fallback([
        f"Partner statement — {ctx.get('period_label', '')}",
        f"This period: {_fmt(ctx.get('period_earnings'))}",
        f"Unpaid balance: {_fmt(ctx.get('unpaid_balance'))}",
        f"Lifetime: {_fmt(ctx.get('lifetime_earnings'))}",
        f"Attached organizers: {ctx.get('organizer_count', 0)}",
    ])
    return subject, html, text


def _t_blog_new_post(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Newsletter fan-out: announce a freshly-published blog post to subscribers.

    ctx fields:
      - subscriber_email (required) — for the unsubscribe link
      - post_title, post_excerpt, post_slug (required)
      - cover_url (optional)
      - reading_time_minutes (optional int)
    """
    post_url = f"{APP_PUBLIC_URL}/blog/{ctx['post_slug']}"
    unsub_url = f"{APP_PUBLIC_URL}/blog/unsubscribe?email={ctx.get('subscriber_email', '')}"
    cover_html = ""
    if ctx.get("cover_url"):
        cover_html = (
            f'<img src="{ctx["cover_url"]}" alt="" '
            f'style="width:100%;max-width:520px;border-radius:12px;display:block;'
            f'margin:0 0 20px;border:1px solid {BORDER};" />'
        )
    body = f"""
    {cover_html}
    <p style="color:{TEXT_MUTED};font-size:12px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 8px;">
      The Allsale Journal · New story
    </p>
    <h2 style="color:{TEXT};font-family:Georgia,serif;font-size:26px;line-height:1.2;margin:0 0 12px;">
      {ctx['post_title']}
    </h2>
    <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0 0 20px;">
      {ctx.get('post_excerpt') or 'Click through to read the full story.'}
    </p>
    """
    subject = f"New on the Journal — {ctx['post_title']}"
    html = _layout(
        ctx["post_title"],
        (ctx.get("post_excerpt") or "")[:140],
        body,
        "Read the full story",
        post_url,
    )
    # Append a clear unsubscribe link below the CTA (Gmail one-click requires it).
    unsub_block = (
        f'<div style="text-align:center;padding:16px 0 0;">'
        f'<a href="{unsub_url}" style="color:{TEXT_MUTED};font-size:11px;text-decoration:underline;">'
        f'Unsubscribe from the Journal</a></div>'
    )
    html = html.replace("</body>", f"{unsub_block}</body>")
    text = _text_fallback([
        f"New story on the Allsale Journal: {ctx['post_title']}",
        ctx.get('post_excerpt') or '',
        f"Read it here: {post_url}",
        "",
        f"Unsubscribe: {unsub_url}",
    ])
    return subject, html, text


def _t_organizer_new_sale(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent to the organizer on EVERY booking (not just the first).

    Distinct from the welcome-funnel `organizer_welcome_3_first_sale` which
    only fires once. This one is for ongoing sales notifications so organizers
    feel the dopamine of every ticket sold.
    """
    name = ctx.get("organizer_name", "there")
    title = ctx.get("event_title", "your event")
    buyer = ctx.get("buyer_name", "Someone")
    buyer_email = ctx.get("buyer_email", "")
    qty = ctx.get("quantity", 1)
    amount = ctx.get("amount", 0)
    currency = ctx.get("currency", "NZD")
    tier = ctx.get("tier_name", "")
    body = f"""
    <p style="color:{TEXT};">Hi {name}, you just sold <strong>{qty} ticket{'s' if qty != 1 else ''}</strong> to <strong>{title}</strong>.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">BUYER</td><td style="text-align:right;color:{TEXT};font-size:13px;">{buyer}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EMAIL</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:12px;padding-top:8px;">{buyer_email}</td></tr>
      {f'<tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">TIER</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{tier}</td></tr>' if tier else ''}
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">QUANTITY</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{qty}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">PAID</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{currency} {float(amount):.2f}</td></tr>
    </table>
    """
    subject = f"🎟️ {qty} ticket{'s' if qty != 1 else ''} sold for {title}"
    html = _layout("Ticket sold", "View attendee list", body, "Open organizer dashboard", f"{APP_PUBLIC_URL}/organizer")
    text = _text_fallback([
        f"Hi {name}, you sold {qty} ticket(s) to {title}.",
        f"Buyer: {buyer} ({buyer_email})",
        f"Tier: {tier}" if tier else "",
        f"Amount: {currency} {float(amount):.2f}",
        f"Dashboard: {APP_PUBLIC_URL}/organizer",
    ])
    return subject, html, text


def _t_admin_new_booking(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Heads-up to admins on every paid booking."""
    admin_name = ctx.get("admin_name", "Admin")
    title = ctx.get("event_title", "an event")
    organizer = ctx.get("organizer_name", "an organizer")
    buyer = ctx.get("buyer_name", "Someone")
    buyer_email = ctx.get("buyer_email", "")
    qty = ctx.get("quantity", 1)
    amount = ctx.get("amount", 0)
    currency = ctx.get("currency", "NZD")
    body = f"""
    <p style="color:{TEXT};">Hi {admin_name}, a new booking just landed.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};font-size:13px;">{title}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">ORGANIZER</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{organizer}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">BUYER</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{buyer}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EMAIL</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:12px;padding-top:8px;">{buyer_email}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">QUANTITY</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{qty}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">AMOUNT</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{currency} {float(amount):.2f}</td></tr>
    </table>
    """
    subject = f"💰 Booking: {qty} × {title} — {currency} {float(amount):.2f}"
    html = _layout("New booking", "Heads up — fresh sale", body, "Open admin dashboard", f"{APP_PUBLIC_URL}/admin")
    text = _text_fallback([
        f"New booking: {qty} × {title}",
        f"Organizer: {organizer}",
        f"Buyer: {buyer} ({buyer_email})",
        f"Amount: {currency} {float(amount):.2f}",
        f"Admin: {APP_PUBLIC_URL}/admin",
    ])
    return subject, html, text


def _t_admin_new_enquiry(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Notifies admin whenever someone uses the contact-organizer form."""
    admin_name = ctx.get("admin_name", "Admin")
    from_name = ctx.get("from_name", "Someone")
    from_email = ctx.get("from_email", "")
    subject_line = ctx.get("subject", "(no subject)")
    event_title = ctx.get("event_title") or "—"
    organizer_name = ctx.get("organizer_name", "an organizer")
    preview = (ctx.get("message_preview") or "")[:300]
    body = f"""
    <p style="color:{TEXT};">Hi {admin_name}, a new enquiry was sent to <strong>{organizer_name}</strong>.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">FROM</td><td style="text-align:right;color:{TEXT};font-size:13px;">{from_name}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EMAIL</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:12px;padding-top:8px;">{from_email}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EVENT</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{event_title}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">SUBJECT</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{subject_line}</td></tr>
    </table>
    <div style="margin-top:14px;padding:14px 16px;border-left:3px solid {BRAND_COLOR};background:{BG};border-radius:8px;color:{TEXT};white-space:pre-wrap;">{preview}</div>
    """
    subject = f"📨 Enquiry: {subject_line} ({event_title})"
    html = _layout("New enquiry", "Customer reached out", body, "Open admin → Messages", f"{APP_PUBLIC_URL}/admin")
    text = _text_fallback([
        f"New enquiry to organizer {organizer_name}:",
        f"From: {from_name} <{from_email}>",
        f"Event: {event_title}",
        f"Subject: {subject_line}",
        f"Message: {preview}",
    ])
    return subject, html, text


def _t_admin_new_user_signup(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent to every admin whenever a new user registers (password or Google OAuth)."""
    admin_name = ctx.get("admin_name", "Admin")
    user_name = ctx.get("user_name", "A user")
    user_email = ctx.get("user_email", "")
    role = ctx.get("role", "attendee")
    provider = ctx.get("auth_provider", "password")
    provider_label = "Google" if provider == "google" else "Email / password"
    body = f"""
    <p style="color:{TEXT};">Hi {admin_name}, a new user just registered on Allsale Events.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">NAME</td><td style="text-align:right;color:{TEXT};font-size:13px;">{user_name}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EMAIL</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:13px;padding-top:8px;">{user_email}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">ROLE</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{role.upper()}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">SIGNUP METHOD</td><td style="text-align:right;color:{TEXT};font-size:13px;padding-top:8px;">{provider_label}</td></tr>
    </table>
    """
    subject = f"New {role} signup: {user_name}"
    html = _layout("New user signup", "Heads up — fresh registration", body, "Open admin → Users", f"{APP_PUBLIC_URL}/admin?tab=users")
    text = _text_fallback([
        f"New user signed up: {user_name} ({user_email})",
        f"Role: {role}",
        f"Method: {provider_label}",
        f"Manage: {APP_PUBLIC_URL}/admin?tab=users",
    ])
    return subject, html, text


def _t_admin_created_account(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent when an admin manually creates a user account (organizer onboarding,
    co-admin seeding, etc.). Includes the temp password so the user can log in
    immediately — they'll change it from their profile."""
    name = ctx.get("user_name", "there")
    email = ctx.get("user_email", "")
    pwd = ctx.get("temp_password", "")
    role = ctx.get("role", "attendee")
    admin = ctx.get("admin_name", "An admin")
    body = f"""
    <p style="color:{TEXT};">Hi {name}, {admin} created an Allsale Events account for you.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EMAIL</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:13px;">{email}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">TEMPORARY PASSWORD</td><td style="text-align:right;color:{TEXT};font-family:Menlo,monospace;font-size:13px;padding-top:8px;">{pwd}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">ROLE</td><td style="text-align:right;color:{BRAND_COLOR};font-weight:700;padding-top:8px;">{role.upper()}</td></tr>
    </table>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Log in with the credentials above, then change your password under Profile → Security.</p>
    """
    subject = "Your Allsale Events account is ready"
    html = _layout("Welcome to Allsale Events", "An admin created your account", body, "Log in to Allsale", f"{APP_PUBLIC_URL}/login")
    text = _text_fallback([
        f"Hi {name}, {admin} created an Allsale Events account for you.",
        f"Email: {email}",
        f"Temporary password: {pwd}",
        f"Role: {role}",
        f"Log in: {APP_PUBLIC_URL}/login",
        "Change your password under Profile → Security after first login.",
    ])
    return subject, html, text


def _t_admin_created_event_for_you(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent to an organizer when an admin sets up an event on their behalf."""
    name = ctx.get("organizer_name", "there")
    title = ctx.get("event_title", "your event")
    admin = ctx.get("admin_name", "An admin")
    venue = ctx.get("venue", "")
    body = f"""
    <p style="color:{TEXT};">Hi {name}, {admin} set up an event on your behalf:</p>
    <p style="color:{TEXT};font-size:18px;margin:4px 0;"><strong>{title}</strong></p>
    {f'<p style="color:{TEXT_MUTED};margin:0 0 12px 0;">{venue}</p>' if venue else ''}
    <p style="color:{TEXT_MUTED};">The event is live and selling. Review the details, ticket tiers and seat map — you can edit anything from your organizer dashboard.</p>
    """
    subject = f"An admin set up '{title}' for you"
    html = _layout("An admin created an event for you", "Review and customize it", body, "Open event in dashboard", ctx.get("edit_url", f"{APP_PUBLIC_URL}/organizer"))
    text = _text_fallback([
        f"Hi {name}, {admin} set up '{title}' for you on Allsale Events.",
        f"Venue: {venue}" if venue else "",
        f"Manage: {ctx.get('edit_url', APP_PUBLIC_URL + '/organizer')}",
        f"Public page: {ctx.get('event_url', '')}",
    ])
    return subject, html, text


def _t_admin_message_to_organizer(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent when an admin posts a new message to an organizer's admin-chat thread."""
    name = ctx.get("organizer_name", "there")
    preview = (ctx.get("preview") or "")[:240]
    admin = ctx.get("admin_name", "Allsale support")
    body = f"""
    <p style="color:{TEXT};">Hi {name}, you have a new message from {admin}:</p>
    <div style="margin-top:10px;padding:14px 16px;border-left:3px solid {BRAND_COLOR};background:{BG};border-radius:8px;color:{TEXT};white-space:pre-wrap;">{preview}</div>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Reply directly from your organizer dashboard — your reply lands instantly in our admin inbox.</p>
    """
    subject = f"New message from {admin}"
    html = _layout("You have a new message", "From Allsale support", body, "Reply on dashboard", f"{APP_PUBLIC_URL}/organizer/inbox")
    text = _text_fallback([
        f"New message from {admin}:",
        preview,
        f"Reply: {APP_PUBLIC_URL}/organizer/inbox",
    ])
    return subject, html, text


def _t_organizer_message_to_admin(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Notifies admins when an organizer posts a new message to their thread."""
    admin_name = ctx.get("admin_name", "Admin")
    organizer = ctx.get("organizer_name", "An organizer")
    organizer_id = ctx.get("organizer_id", "")
    preview = (ctx.get("preview") or "")[:240]
    body = f"""
    <p style="color:{TEXT};">Hi {admin_name}, <strong>{organizer}</strong> sent a new message:</p>
    <div style="margin-top:10px;padding:14px 16px;border-left:3px solid {BRAND_COLOR};background:{BG};border-radius:8px;color:{TEXT};white-space:pre-wrap;">{preview}</div>
    """
    subject = f"Organizer message: {organizer}"
    html = _layout("New organizer message", "Open in admin chat", body, "Open in admin chat", f"{APP_PUBLIC_URL}/admin?tab=org-chat&organizer={organizer_id}")
    text = _text_fallback([
        f"{organizer} sent a new message:",
        preview,
        f"Open: {APP_PUBLIC_URL}/admin?tab=org-chat&organizer={organizer_id}",
    ])
    return subject, html, text


def _t_event_recap(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent ~1 hour after an event ends. Quick post-mortem the organizer
    can scan in 10 seconds: tickets sold, gross, scan rate, top promo,
    repeat-customer count."""
    name = ctx.get("organizer_name", "there")
    title = ctx.get("event_title", "your event")
    tickets = ctx.get("tickets") or 0
    gross = ctx.get("gross") or 0
    currency = ctx.get("currency", "NZD")
    scan_rate = ctx.get("scan_rate")
    top_promo = ctx.get("top_promo")
    top_promo_count = ctx.get("top_promo_count") or 0
    repeat = ctx.get("repeat_customers") or 0
    scan_str = f"{scan_rate}%" if scan_rate is not None else "—"
    promo_line = (
        f"Top promo: <strong>{top_promo}</strong> ({top_promo_count} redemption{'s' if top_promo_count != 1 else ''})"
        if top_promo
        else "No promo codes used."
    )
    subject = f"How '{title}' sold — your event recap"
    html = f"""
    <h2 style="font-family:Georgia,serif;color:#FF6B35;margin:0 0 4px 0;">Your event recap</h2>
    <p style="margin:0 0 16px 0;color:#444;">Hi {name},</p>
    <p style="margin:0 0 16px 0;color:#444;">
      <strong>{title}</strong> is in the books. Here's how it went:
    </p>
    <table cellpadding="12" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;margin:0 0 16px 0;">
      <tr>
        <td style="background:#FFF4ED;border-radius:8px;width:33%;text-align:center;">
          <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:2px;">Tickets sold</div>
          <div style="font-size:26px;font-weight:700;color:#FF6B35;font-family:Georgia,serif;">{tickets}</div>
        </td>
        <td style="width:6px;"></td>
        <td style="background:#FFF4ED;border-radius:8px;width:33%;text-align:center;">
          <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:2px;">Gross</div>
          <div style="font-size:26px;font-weight:700;color:#FF6B35;font-family:Georgia,serif;">{currency} {gross:,.2f}</div>
        </td>
        <td style="width:6px;"></td>
        <td style="background:#FFF4ED;border-radius:8px;width:33%;text-align:center;">
          <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:2px;">Scan rate</div>
          <div style="font-size:26px;font-weight:700;color:#FF6B35;font-family:Georgia,serif;">{scan_str}</div>
        </td>
      </tr>
    </table>
    <p style="margin:0 0 8px 0;color:#444;">{promo_line}</p>
    <p style="margin:0 0 16px 0;color:#444;">{repeat} returning customer{'s' if repeat != 1 else ''} attended this event.</p>
    <p style="margin:0 0 16px 0;color:#444;">
      Running another show? <a href="https://allsale.events/organizer/new" style="color:#FF6B35;font-weight:600;">List a new event →</a>
    </p>
    <p style="margin:24px 0 0 0;font-size:11px;color:#999;">Allsale Events · support@allsale.events</p>
    """
    text = (
        f"Hi {name},\n\n"
        f"{title} is in the books. Recap:\n\n"
        f"  Tickets sold: {tickets}\n"
        f"  Gross: {currency} {gross:,.2f}\n"
        f"  Scan rate: {scan_str}\n"
        f"  {'Top promo: ' + str(top_promo) + ' (' + str(top_promo_count) + ' redemptions)' if top_promo else 'No promo codes used.'}\n"
        f"  Returning customers: {repeat}\n\n"
        f"Run another? https://allsale.events/organizer/new\n\n"
        f"— Allsale Events"
    )
    return subject, html, text


def _t_boost_recap(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent ~1 hour after a Boost expires — shows the organizer the lift
    their boosted listing actually drove (views + bookings vs the equivalent
    pre-boost window) and nudges them to repeat the buy on their next event.
    """
    name = ctx.get("organizer_name", "there")
    event_title = ctx.get("event_title", "your event")
    tier = ctx.get("boost_tier") or ("paid" if ctx.get("boost_kind") == "paid" else "free")
    views = ctx.get("during_views")
    bookings = ctx.get("during_bookings")
    view_lift = ctx.get("view_lift_pct")
    booking_lift = ctx.get("booking_lift_pct")

    def fmt_lift(v):
        if v is None:
            return "—"
        return f"{'+' if v >= 0 else ''}{v}%"

    views_str = "—" if views is None else str(views)
    bookings_str = "—" if bookings is None else str(bookings)
    subject = f"Your Boost just ended — here's how '{event_title}' performed"
    html = f"""
    <h2 style="font-family:Georgia,serif;color:#FF6B35;margin:0 0 4px 0;">Boost recap</h2>
    <p style="margin:0 0 16px 0;color:#444;">Hi {name},</p>
    <p style="margin:0 0 16px 0;color:#444;">
      Your <strong>{tier}</strong> boost on <strong>{event_title}</strong> just ended.
      Here's what it did:
    </p>
    <table cellpadding="12" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;margin:0 0 16px 0;">
      <tr>
        <td style="background:#FFF4ED;border-radius:8px;width:50%;text-align:center;">
          <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:2px;">Views</div>
          <div style="font-size:28px;font-weight:700;color:#FF6B35;font-family:Georgia,serif;">{views_str}</div>
          <div style="font-size:12px;color:#444;">{fmt_lift(view_lift)} vs before</div>
        </td>
        <td style="width:8px;"></td>
        <td style="background:#FFF4ED;border-radius:8px;width:50%;text-align:center;">
          <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:2px;">Bookings</div>
          <div style="font-size:28px;font-weight:700;color:#FF6B35;font-family:Georgia,serif;">{bookings_str}</div>
          <div style="font-size:12px;color:#444;">{fmt_lift(booking_lift)} vs before</div>
        </td>
      </tr>
    </table>
    <p style="margin:0 0 16px 0;color:#444;">
      Want another boost on your next event?
      <a href="https://allsale.events/organizer" style="color:#FF6B35;font-weight:600;">Open your dashboard →</a>
    </p>
    <p style="margin:24px 0 0 0;font-size:11px;color:#999;">Allsale Events · support@allsale.events</p>
    """
    text = (
        f"Hi {name},\n\n"
        f"Your {tier} Boost on {event_title} just ended.\n\n"
        f"Views: {views_str} ({fmt_lift(view_lift)} vs before)\n"
        f"Bookings: {bookings_str} ({fmt_lift(booking_lift)} vs before)\n\n"
        f"Want another Boost? https://allsale.events/organizer\n\n"
        f"— Allsale Events"
    )
    return subject, html, text


def _t_gift_card_delivered(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Recipient gets the gift card code + a personal note from the purchaser."""
    import html as _html
    recipient = (ctx.get("recipient_name") or "there")[:80]
    purchaser = (ctx.get("purchaser_name") or "Someone")[:80]
    amount = ctx.get("amount", "0.00")
    currency = ctx.get("currency", "NZD")
    code = (ctx.get("code") or "").strip()
    note = (ctx.get("personal_note") or "").strip()
    redeem_url = ctx.get("redeem_url") or f"{APP_PUBLIC_URL}/events"
    note_block = (
        f'<p style="margin-top:14px;padding:14px;border-radius:10px;background:#1c1c20;color:{TEXT};font-style:italic;">"{_html.escape(note)}"<br/><span style="color:{TEXT_MUTED};font-style:normal;">— {_html.escape(purchaser)}</span></p>'
        if note else ""
    )
    body = f"""
    <p style="color:{TEXT};">Kia ora {_html.escape(recipient)} — <strong>{_html.escape(purchaser)}</strong> just sent you an Allsale Events gift card 🎁</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;text-align:center;">
      <tr><td style="font-size:12px;letter-spacing:2px;color:{TEXT_MUTED};">GIFT CARD VALUE</td></tr>
      <tr><td style="font-size:28px;font-weight:700;color:{BRAND_COLOR};padding-top:6px;">{currency} {amount}</td></tr>
      <tr><td style="font-size:12px;color:{TEXT_MUTED};padding-top:14px;">CODE</td></tr>
      <tr><td style="font-family:Menlo,Monaco,monospace;font-size:18px;color:{TEXT};letter-spacing:2px;padding-top:4px;">{_html.escape(code)}</td></tr>
    </table>
    {note_block}
    <p style="margin-top:18px;color:{TEXT_MUTED};">Apply it at checkout on any event — partial use is fine, the remaining balance stays on your card.</p>
    """
    subject = f"You've got a {currency} {amount} Allsale gift card 🎁"
    html = _layout(subject, f"From {purchaser}", body, "Browse events", redeem_url)
    text = _text_fallback([
        f"You've got a {currency} {amount} Allsale gift card from {purchaser}",
        f"Code: {code}",
        f"Use it: {redeem_url}",
        f"Note: {note}" if note else "",
    ])
    return subject, html, text


def _t_organizer_welcome_1_signup(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email 1 — fired immediately after an organizer account is created."""
    name = (ctx.get("organizer_name") or "there")[:80]
    subj = "Welcome to Allsale 🎟️ — let's get your first event live"
    html = _wrap_html(
        f"""
        <p>Kia ora {_h(name)},</p>
        <p>Welcome to <strong>Allsale Events</strong> — Aotearoa&apos;s ticketing platform where organizers keep 100% of the ticket price.</p>
        <h3 style="font-family:Georgia,serif;font-size:20px;margin-top:24px">3 things to do today</h3>
        <ol style="line-height:1.7">
          <li><strong>Create your first event</strong> — title, date, venue, tiers. Takes ~5 minutes.<br><a href="https://www.allsale.events/organizer/new" style="color:#FF4F00">→ Create event</a></li>
          <li><strong>Connect your Stripe account</strong> so you can get paid (we use Stripe Connect Express — quick onboarding, payouts straight to your bank).<br><a href="https://www.allsale.events/organizer" style="color:#FF4F00">→ Open Payouts</a></li>
          <li><strong>Set your refund policy</strong> — e.g. &ldquo;full refund up to 48h before&rdquo;. Attendees self-serve; you don&apos;t lift a finger.</li>
        </ol>
        <p>Questions? Just reply to this email — it goes straight to our team.</p>
        <p>– The Allsale crew</p>
        """
    )
    text = f"Kia ora {name},\n\nWelcome to Allsale. Create your first event: https://www.allsale.events/organizer/new\nConnect Stripe to get paid: https://www.allsale.events/organizer\n"
    return subj, html, text


def _t_organizer_welcome_2_publish(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email 2 — fired 48h after signup if no event submitted yet."""
    name = (ctx.get("organizer_name") or "there")[:80]
    subj = "Still thinking about your first event? Here's what works ✨"
    html = _wrap_html(
        f"""
        <p>Hey {_h(name)},</p>
        <p>Noticed you haven&apos;t listed your first event yet. No worries — here&apos;s a quick playbook from organizers who&apos;ve sold out on Allsale:</p>
        <ul style="line-height:1.8">
          <li><strong>One sharp photo</strong> beats a wall of copy. Square or 4:5 ratio for the hero image.</li>
          <li><strong>Tiered pricing</strong> (e.g. Early Bird → GA → VIP) creates urgency from day one.</li>
          <li><strong>Auto FIRST50 promo</strong> — every approved event gets a 10% off &ldquo;first 50 buyers&rdquo; code automatically. We&apos;ve seen it convert 3-4× faster on launch day.</li>
          <li><strong>Affiliate codes for influencers</strong> — generate a code in 30 seconds, hand it to a local micro-influencer, watch trackable traffic roll in.</li>
        </ul>
        <p><a href="https://www.allsale.events/organizer/new" style="display:inline-block;background:#FF4F00;color:#fff;padding:12px 24px;border-radius:9999px;text-decoration:none;font-weight:600;margin-top:8px">Create your event →</a></p>
        <p style="color:#999;font-size:12px;margin-top:24px">Need help? Reply to this email and we&apos;ll set it up with you on a 15-min call.</p>
        """
    )
    text = f"Hey {name}, here's how organizers sell out on Allsale.\nCreate event: https://www.allsale.events/organizer/new"
    return subj, html, text


def _t_organizer_welcome_3_first_sale(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email 3 — fired on the FIRST paid booking on any of the organizer's events."""
    name = (ctx.get("organizer_name") or "there")[:80]
    event_title = (ctx.get("event_title") or "your event")[:200]
    amount = ctx.get("amount") or 0
    currency = (ctx.get("currency") or "NZD")[:6].upper()
    subj = f"🎉 You just made your first sale on {_h(event_title)}"
    html = _wrap_html(
        f"""
        <p>Massive moment, {_h(name)} —</p>
        <p>You just sold your first ticket to <strong>{_h(event_title)}</strong> for <strong>{currency} {amount:.2f}</strong>. 🍾</p>
        <p>Here&apos;s what happens next:</p>
        <ul style="line-height:1.7">
          <li>Funds are <strong>held by Stripe for 5 days post-event</strong> (industry-standard chargeback window), then auto-transferred to your bank.</li>
          <li>Track live sales in your dashboard → <a href="https://www.allsale.events/organizer" style="color:#FF4F00">organizer dashboard</a></li>
          <li>Want more sales? <strong>Create an affiliate code</strong> for a local influencer or DJ — they paste your link, you track conversions, pay commission only on actual sales.</li>
        </ul>
        <p>Keep the momentum — share your event on socials, in WhatsApp groups, and use the embed widget to drop a live event list on your own website.</p>
        <p>– The Allsale crew</p>
        """
    )
    text = f"You just made your first sale on {event_title}! Track sales: https://www.allsale.events/organizer"
    return subj, html, text


def _t_organizer_welcome_4_reactivate(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email 4 — fired 14d after an event ends if the organizer hasn't created
    a new one. Encourages a follow-up to drive repeat revenue."""
    name = (ctx.get("organizer_name") or "there")[:80]
    last_event = (ctx.get("last_event_title") or "your last event")[:200]
    subj = "Time to do it again? 👀"
    html = _wrap_html(
        f"""
        <p>Hey {_h(name)},</p>
        <p>It&apos;s been a couple of weeks since <strong>{_h(last_event)}</strong> wrapped. People are already asking when the next one drops 📣</p>
        <p>3 ways to ride the momentum:</p>
        <ol style="line-height:1.7">
          <li><strong>Announce now</strong> — your followers from {_h(last_event)} will see it first (they get an auto-email from Allsale).</li>
          <li><strong>Reuse the seat map</strong> — duplicate your old event in 2 clicks, change the date, done.</li>
          <li><strong>Run a presale</strong> with a promo code only for past attendees — instant warm conversions.</li>
        </ol>
        <p><a href="https://www.allsale.events/organizer/new" style="display:inline-block;background:#FF4F00;color:#fff;padding:12px 24px;border-radius:9999px;text-decoration:none;font-weight:600">Plan your next event →</a></p>
        """
    )
    text = f"Hey {name}, time for your next event? Plan: https://www.allsale.events/organizer/new"
    return subj, html, text


def _t_admin_webhook_silent_failure(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Operational alert: Stripe Connect webhook hasn't delivered in 48h."""
    last_at = (ctx.get("last_delivery_at") or "never")[:30]
    total = ctx.get("total_ever") or 0
    dash = (ctx.get("dashboard_url") or "https://www.allsale.events/admin")
    subj = "⚠️ Allsale: Stripe Connect webhook silent for 48h"
    html = _wrap_html(
        f"""
        <p>Heads-up — your Stripe Connect webhook hasn&apos;t delivered any events in the last 48 hours.</p>
        <p><strong>Status</strong></p>
        <ul>
          <li>Last delivery: <code>{_h(last_at)}</code></li>
          <li>Total deliveries ever: <strong>{total}</strong></li>
          <li>Signing secret env var: <strong>set</strong> (otherwise this alert wouldn&apos;t fire)</li>
        </ul>
        <p><strong>Common causes</strong></p>
        <ol>
          <li>Stripe rotated the signing secret — Railway env <code>STRIPE_CONNECT_WEBHOOK_SECRET</code> is now stale.</li>
          <li>Webhook destination disabled on the Stripe dashboard.</li>
          <li>Railway env var deleted/renamed in a deploy.</li>
          <li>DNS / SSL change broke <code>www.allsale.events/api/webhook/stripe/connect</code>.</li>
        </ol>
        <p>
          <a href="{_h(dash)}" style="display:inline-block;background:#FF4F00;color:#fff;padding:12px 24px;border-radius:9999px;text-decoration:none;font-weight:600">Open Admin → Stripe diagnostics</a>
        </p>
        <p style="color:#999;font-size:12px;margin-top:24px">This alert fires once per day max. To stop: set <code>ADMIN_ALERT_EMAIL=</code> to silence, or fix the webhook so events flow again.</p>
        """
    )
    text = (
        f"Stripe Connect webhook silent for 48h.\n"
        f"Last delivery: {last_at}\nTotal ever: {total}\n"
        f"Investigate: {dash}\n"
    )
    return subj, html, text


def _t_ticket_transfer_offer(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email to the recipient of a ticket transfer with a one-click claim link."""
    sender = (ctx.get("sender_name") or "An Allsale member")[:120]
    title = (ctx.get("event_title") or "an event")[:200]
    venue = (ctx.get("venue") or "")[:200]
    when_iso = ctx.get("event_date_iso") or ""
    when_human = ""
    try:
        if when_iso:
            dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
            when_human = dt.strftime("%a %b %d · %I:%M %p").lstrip("0")
    except Exception:  # noqa: BLE001
        when_human = when_iso
    claim_url = (ctx.get("claim_url") or "https://www.allsale.events")
    note = (ctx.get("note") or "")[:500]
    note_html = (
        f"<p style='border-left:3px solid #FF4F00;padding:6px 12px;background:#fff7f0;color:#444;font-style:italic'>{_h(note)}</p>"
        if note else ""
    )
    subj = f"🎁 {sender} sent you a ticket: {title}"
    html = _wrap_html(
        f"""
        <p><strong>{_h(sender)}</strong> has transferred a ticket to you:</p>
        <h2 style="margin:18px 0 6px;font-family:Georgia,serif;font-size:22px">{_h(title)}</h2>
        <p style="color:#666;font-size:13px;margin:0 0 14px">{_h(when_human)} · {_h(venue)}</p>
        {note_html}
        <p style="margin-top:18px">
          <a href="{_h(claim_url)}" style="display:inline-block;background:#FF4F00;color:#fff;padding:12px 24px;border-radius:9999px;text-decoration:none;font-weight:600">Accept ticket</a>
        </p>
        <p style="color:#999;font-size:12px;margin-top:18px">If the email above doesn't match the address you sign up with, this transfer can't be accepted. Tap the link to sign in or create an account first. The transfer expires in 7 days.</p>
        """
    )
    text = f"{sender} sent you a ticket to {title} ({when_human}, {venue}).\nAccept: {claim_url}"
    return subj, html, text


def _t_follower_new_event(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """One-shot 'new event from an organizer you follow' email.
    Fired on event approval to each follower (notifications_enabled != False).
    """
    follower = (ctx.get("follower_name") or "there")[:80]
    organizer = (ctx.get("organizer_name") or "an organizer you follow")[:120]
    title = (ctx.get("event_title") or "New event")[:200]
    venue = (ctx.get("venue") or "")[:200]
    when_iso = ctx.get("event_date_iso") or ""
    when_human = ""
    try:
        if when_iso:
            dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
            when_human = dt.strftime("%a %b %d · %I:%M %p").lstrip("0")
    except Exception:  # noqa: BLE001
        when_human = when_iso
    event_url = (ctx.get("event_url") or "https://www.allsale.events")
    subj = f"🎟 {organizer} just announced: {title}"
    html = _wrap_html(
        f"""
        <p>Hey {_h(follower)},</p>
        <p><strong>{_h(organizer)}</strong> just published a new event you might want to see —</p>
        <h2 style="margin:24px 0 8px;font-family:Georgia,serif;font-size:24px;line-height:1.2;color:#1a1a1a">{_h(title)}</h2>
        <p style="color:#666;font-size:13px;margin:0 0 16px">
          {_h(when_human)} · {_h(venue)}
        </p>
        <p>
          <a href="{_h(event_url)}" style="display:inline-block;background:#FF4F00;color:#fff;padding:12px 24px;border-radius:9999px;text-decoration:none;font-weight:600">View event</a>
        </p>
        <p style="color:#999;font-size:12px;margin-top:32px">You're getting this because you follow {_h(organizer)}. <a href="{_h(event_url)}" style="color:#999">Unfollow</a> on their page anytime.</p>
        """
    )
    text = (
        f"Hey {follower},\n\n{organizer} just published a new event:\n"
        f"\n  {title}\n  {when_human} — {venue}\n\nView event: {event_url}\n"
    )
    return subj, html, text


def _t_follower_weekly_digest(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sunday weekly digest of new events from all the organizers a user
    follows. Skipped client-side if no new events this week."""
    follower = (ctx.get("follower_name") or "there")[:80]
    items = ctx.get("items") or []  # [{title, organizer_name, when_human, venue, url}]
    if not items:
        # Caller is responsible for not sending an empty digest, but be safe.
        items = []
    items_html = "".join(
        f"""
        <div style="border:1px solid #e8e6dc;border-radius:12px;padding:14px;margin-bottom:10px;background:#fafaf8">
          <div style="font-size:11px;color:#FF4F00;font-weight:600;letter-spacing:0.08em;text-transform:uppercase">{_h(it.get('when_human',''))}</div>
          <div style="font-size:16px;font-weight:600;margin:4px 0 2px">{_h(it.get('title',''))}</div>
          <div style="color:#666;font-size:13px;margin-bottom:8px">By {_h(it.get('organizer_name',''))} · {_h(it.get('venue',''))}</div>
          <a href="{_h(it.get('url',''))}" style="color:#FF4F00;font-weight:600;font-size:13px;text-decoration:none">View event →</a>
        </div>
        """
        for it in items
    )
    subj = f"Your Allsale weekly: {len(items)} new event{'s' if len(items)!=1 else ''} from organizers you follow"
    html = _wrap_html(
        f"""
        <p>Hey {_h(follower)},</p>
        <p>Here's what's new this week from organizers you follow:</p>
        {items_html}
        <p style="color:#999;font-size:12px;margin-top:32px">Manage your follows on your <a href="https://www.allsale.events/me/following" style="color:#999">following page</a>.</p>
        """
    )
    text = (
        f"Hey {follower},\n\nNew this week from organizers you follow:\n\n"
        + "\n".join(f"- {it.get('title')} ({it.get('when_human')}) — {it.get('url')}" for it in items)
        + "\n"
    )
    return subj, html, text


def _t_organizer_contact_message(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Email sent to an organizer when a visitor submits the contact form on
    their public profile or one of their event pages.
    """
    from_name = (ctx.get("from_name") or "Someone")[:120]
    from_email = (ctx.get("from_email") or "")[:200]
    subject_in = (ctx.get("subject") or "Message from your event page")[:160]
    msg_preview = (ctx.get("message_preview") or "")[:600]
    event_title = ctx.get("event_title")
    event_line = (
        f"<tr><td style='font-size:13px;color:{TEXT_MUTED};padding-top:8px;'>ABOUT EVENT</td>"
        f"<td style='text-align:right;color:{TEXT};padding-top:8px;'>{event_title}</td></tr>"
        if event_title else ""
    )

    subject = f"New message: {subject_in}"
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('organizer_name','there')} — you have a new message from a visitor on Allsale Events.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">FROM</td><td style="text-align:right;color:{TEXT};font-weight:600;">{from_name}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">EMAIL</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{from_email}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">SUBJECT</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{subject_in}</td></tr>
      {event_line}
    </table>
    <div style="margin-top:18px;padding:16px;border-radius:12px;background:{BG_CARD};color:{TEXT};white-space:pre-wrap;font-size:15px;line-height:1.5;">{msg_preview}</div>
    <p style="margin-top:18px;font-size:13px;color:{TEXT_MUTED};">Click the button below to reply directly to the sender's email — they'll receive your response in their inbox.</p>
    """
    cta_url = ctx.get("reply_url") or f"mailto:{from_email}"
    html = _layout(
        title=f"Message from {from_name}",
        preheader=msg_preview[:140],
        body_html=body,
        cta_label=f"Reply to {from_name}",
        cta_url=cta_url,
    )
    text = "\n".join([
        f"New message from {from_name} <{from_email}>",
        f"Subject: {subject_in}",
        (f"About event: {event_title}" if event_title else ""),
        "",
        msg_preview,
        "",
        f"Reply: {cta_url}",
    ])
    return subject, html, text


# ---------------------------------------------------------------------------
# Upcoming-event templates (defined below TEMPLATES so the dict can reference them)
# ---------------------------------------------------------------------------
def _t_event_reminder_24h(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """24h-before reminder for an attendee with a paid booking."""
    seats = ", ".join(ctx.get("seats") or []) if ctx.get("seats") else ctx.get("tier_name", "General")
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')} — quick reminder, your event is <strong>tomorrow</strong>.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};font-weight:600;">{ctx['event_title']}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">WHEN</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_when','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">VENUE</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_venue','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">SEATS</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{seats}</td></tr>
    </table>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Your QR ticket is in <a href="{APP_PUBLIC_URL}/profile" style="color:{BRAND_COLOR};">My Tickets</a>. Arrive 15 min early for a smooth entry.</p>
    """
    subject = f"⏰ Tomorrow: {ctx['event_title']}"
    html = _layout("See you tomorrow", "Allsale Events reminder", body, "Open my ticket", f"{APP_PUBLIC_URL}/profile")
    text = _text_fallback([
        f"Reminder: {ctx['event_title']} is tomorrow.",
        f"When: {ctx.get('event_when','')}",
        f"Venue: {ctx.get('event_venue','')}",
        f"Tickets: {APP_PUBLIC_URL}/profile",
    ])
    return subject, html, text


def _t_weekly_digest(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Monday-morning digest with the upcoming week's top events for a single user."""
    items = ctx.get("events") or []
    rows = "".join(
        f"""
        <tr><td style="padding:14px 0;border-bottom:1px solid {BORDER};">
          <div style="font-size:16px;color:{TEXT};font-weight:600;">{e.get('title','')}</div>
          <div style="font-size:13px;color:{TEXT_MUTED};margin-top:2px;">{e.get('venue','')} · {e.get('when','')}</div>
          <a href="{APP_PUBLIC_URL}/events/{e.get('event_id','')}" style="font-size:13px;color:{BRAND_COLOR};text-decoration:none;">View event →</a>
        </td></tr>
        """ for e in items[:6]
    )
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')} — here's what's on this week.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:8px;">{rows}</table>
    <p style="margin-top:18px;font-size:12px;color:{TEXT_MUTED};">You receive this because Marketing notifications are on. Manage in <a href="{APP_PUBLIC_URL}/profile" style="color:{BRAND_COLOR};">your profile</a>.</p>
    """
    subject = f"This week on Allsale Events — {len(items)} picks"
    html = _layout("Your week of live experiences", "Weekly digest", body, "Browse all events", f"{APP_PUBLIC_URL}/events")
    text = _text_fallback(
        ["This week on Allsale Events:"] + [f"- {e.get('title','')} ({e.get('venue','')}, {e.get('when','')}) {APP_PUBLIC_URL}/events/{e.get('event_id','')}" for e in items[:6]],
    )
    return subject, html, text


def _t_new_event_announcement(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Sent when an organizer announces a new event to their audience."""
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')} — <strong>{ctx.get('organizer_name','an organizer')}</strong> just dropped a new event.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};font-weight:600;">{ctx.get('event_title','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">WHEN</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_when','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">VENUE</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_venue','')}</td></tr>
    </table>
    <p style="margin-top:16px;color:{TEXT_MUTED};">Tickets are <strong style="color:{BRAND_COLOR};">live now</strong>. Snap yours before they sell out.</p>
    """
    subject = f"🔥 New from {ctx.get('organizer_name','Allsale')}: {ctx.get('event_title','')}"
    html = _layout("A new event just dropped", "Allsale Events", body, "Get tickets", f"{APP_PUBLIC_URL}/events/{ctx.get('event_id','')}")
    text = _text_fallback([
        f"{ctx.get('organizer_name','An organizer')} just announced {ctx.get('event_title','')}.",
        f"When: {ctx.get('event_when','')}",
        f"Venue: {ctx.get('event_venue','')}",
        f"Book: {APP_PUBLIC_URL}/events/{ctx.get('event_id','')}",
    ])
    return subject, html, text


def _t_admin_blast(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Admin-authored custom message + optional event card."""
    event_block = ""
    if ctx.get("event_id"):
        event_block = f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
          style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
          <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};font-weight:600;">{ctx.get('event_title','')}</td></tr>
          <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">WHEN</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('event_when','')}</td></tr>
        </table>
        """
    body_text = (ctx.get("body") or "").replace("\n", "<br>")
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('user_name','there')},</p>
    <p style="color:{TEXT_MUTED};">{body_text}</p>
    {event_block}
    """
    subject = ctx.get("subject") or "Update from Allsale Events"
    cta_url = f"{APP_PUBLIC_URL}/events/{ctx.get('event_id','')}" if ctx.get("event_id") else f"{APP_PUBLIC_URL}/events"
    html = _layout(subject, "From the Allsale Events team", body, "Browse events", cta_url)
    text = _text_fallback([ctx.get("body") or "", cta_url])
    return subject, html, text


def _t_admin_new_event_submitted(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Notification to admins when an organizer submits a new event."""
    when = ctx.get("event_date_iso") or ""
    try:
        from datetime import datetime as _dt
        when_disp = _dt.fromisoformat(when.replace("Z", "+00:00")).strftime("%a %d %b %Y · %I:%M %p")
    except Exception:
        when_disp = when[:16] if when else "TBA"
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('admin_name','Admin')},</p>
    <p style="color:{TEXT_MUTED};">A new event is waiting for your review.</p>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
      style="margin-top:14px;border:1px solid {BORDER};border-radius:12px;padding:18px;">
      <tr><td style="font-size:13px;color:{TEXT_MUTED};">EVENT</td><td style="text-align:right;color:{TEXT};font-weight:600;">{ctx.get('event_title','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">ORGANIZER</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('organizer_name','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">VENUE</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{ctx.get('venue','')}</td></tr>
      <tr><td style="font-size:13px;color:{TEXT_MUTED};padding-top:8px;">WHEN</td><td style="text-align:right;color:{TEXT};padding-top:8px;">{when_disp}</td></tr>
    </table>
    """
    subject = f"New event needs review: {ctx.get('event_title','Untitled')}"
    html = _layout(subject, "A new submission landed in your moderation queue", body, "Open admin queue", ctx.get("admin_url", APP_PUBLIC_URL + "/admin"))
    text = _text_fallback([
        f"New event submitted: {ctx.get('event_title','')}",
        f"By {ctx.get('organizer_name','')} at {ctx.get('venue','')} — {when_disp}",
        ctx.get("admin_url", APP_PUBLIC_URL + "/admin"),
    ])
    return subject, html, text


def _t_organizer_stripe_setup_nudge(ctx: Dict[str, Any]) -> tuple[str, str, str]:
    """Friendly reminder that the organizer has upcoming events but hasn't
    finished Stripe Connect — their payouts will be delayed otherwise."""
    when = ctx.get("next_event_date") or ""
    try:
        from datetime import datetime as _dt
        when_disp = _dt.fromisoformat(when.replace("Z", "+00:00")).strftime("%a %d %b")
    except Exception:
        when_disp = when[:10] if when else "soon"
    n = int(ctx.get("events_count", 1) or 1)
    plural = "event" if n == 1 else "events"
    body = f"""
    <p style="color:{TEXT};">Hi {ctx.get('organizer_name','organizer')},</p>
    <p style="color:{TEXT_MUTED};">You have <b style="color:{TEXT};">{n} {plural}</b> coming up — including <b style="color:{TEXT};">{ctx.get('next_event_title','your next event')}</b> on {when_disp} — but you haven&apos;t finished setting up Stripe yet.</p>
    <p style="color:{TEXT_MUTED};">Stripe is how we send you your ticket revenue (5 days after each event ends). Without it, your payouts will be held in escrow until you connect.</p>
    <p style="color:{TEXT_MUTED};">It takes about 3 minutes — bank details, ID, that&apos;s it.</p>
    """
    subject = f"Finish Stripe setup so we can pay you for {ctx.get('next_event_title','your event')}"
    html = _layout(subject, "Quick reminder before your event", body, "Finish Stripe setup", ctx.get("dashboard_url", APP_PUBLIC_URL + "/organizer"))
    text = _text_fallback([
        f"Hi {ctx.get('organizer_name','organizer')},",
        f"You have {n} {plural} coming up but Stripe isn't set up yet — payouts will be delayed.",
        f"Finish setup: {ctx.get('dashboard_url', APP_PUBLIC_URL + '/organizer')}",
    ])
    return subject, html, text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def send_template(template: str, to: str, ctx: Dict[str, Any], db=None, attachments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Render and dispatch a template. Always returns a result dict; never raises.

    Logs to `email_logs` collection (if db provided) with status: queued | sent | failed | skipped.

    If a user with this email has set `notification_email`, the message is
    transparently re-routed to that address (the original `to` is recorded
    on the log as `to_requested` for auditability).

    :param attachments: Optional list of dicts with keys `content` (bytes or
        base64 str) and `filename` (str). Forwarded to Resend's attachments
        API verbatim. Used to attach the booking-confirmation ticket PDF.
    """
    log_id = uuid4().hex[:16]
    now_iso = datetime.now(timezone.utc).isoformat()
    requested_to = to
    # Resolve notification_email override (lets users keep their login email
    # while having all automated notifications land in a different inbox —
    # critical for domains whose login email has no real MX records).
    if db is not None and to:
        try:
            owner = await db.users.find_one(
                {"email": to.lower().strip()},
                {"_id": 0, "notification_email": 1},
            )
            if owner and owner.get("notification_email"):
                to = owner["notification_email"]
        except Exception:
            pass
    base = {"log_id": log_id, "template": template, "to": to, "to_requested": requested_to, "created_at": now_iso, "context_summary": _safe_summary(ctx)}

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
    if REPLY_TO_EMAIL:
        # Resend / Gmail render this as the address customers' Reply button
        # targets. Lets us send FROM a verified domain while keeping support
        # in a shared Gmail inbox.
        params["reply_to"] = [REPLY_TO_EMAIL]
    # Forward attachments to Resend. Each attachment dict needs `content` and
    # `filename`. Resend accepts raw bytes (which get auto-base64'd by the
    # `resend` SDK) — so we just pass through whatever the caller hands us.
    if attachments:
        params["attachments"] = attachments

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


def send_template_fireforget(template: str, to: str, ctx: Dict[str, Any], db=None, attachments: Optional[List[Dict[str, Any]]] = None):
    """Schedule send without awaiting. Use when caller shouldn't block on email I/O.

    Returns the asyncio.Task on success or None if the event loop is closed
    (e.g. during pytest teardown). The None branch silences the noisy
    `RuntimeError: cannot schedule new futures after shutdown` traceback that
    used to surface when background-task email sends ran after the loop closed.
    """
    try:
        return asyncio.create_task(send_template(template, to, ctx, db, attachments=attachments))
    except RuntimeError:
        # Loop already closed — happens in test teardown. Drop the send silently.
        return None


def _safe_summary(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Pull only short scalar/string fields from ctx (avoid huge blobs in logs)."""
    out = {}
    for k, v in ctx.items():
        if isinstance(v, (str, int, float, bool)) and len(str(v)) < 200:
            out[k] = v
        elif isinstance(v, list) and len(v) < 10:
            out[k] = v
    return out
