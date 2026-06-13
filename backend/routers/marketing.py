"""Marketing assets — one-page promoter pitch as static HTML.

Served at /api/marketing/pitch.html (no auth). Designed to be either:
  - Printed to PDF from the browser (File → Print → Save as PDF), or
  - Shared as a direct link in DMs / emails.

Organizer can just send this URL to a venue or promoter; it has all the
core selling points in a one-page-print-ready layout.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["marketing"])


_PITCH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Allsale Events — Promoter pitch</title>
<style>
  @page { size: A4; margin: 14mm; }
  :root {
    --accent: #FF4F00;
    --ink: #1a1a1a;
    --dim: #555;
    --bg: #faf8f2;
    --card: #fff;
    --border: #e8e6dc;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    background: var(--bg);
    color: var(--ink);
    line-height: 1.45;
  }
  .page {
    max-width: 780px;
    margin: 0 auto;
    padding: 32px 36px 28px;
  }
  .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 22px; }
  .brand-mark {
    width: 36px; height: 36px; border-radius: 8px;
    background: var(--accent); color: #fff;
    display: grid; place-items: center;
    font-family: Georgia, serif; font-weight: 700; font-size: 20px;
  }
  .brand-name { font-family: Georgia, serif; font-size: 22px; letter-spacing: -0.01em; }
  h1 {
    font-family: Georgia, serif;
    font-size: 40px; line-height: 1.05;
    margin: 0 0 12px;
    letter-spacing: -0.02em;
  }
  h1 em { color: var(--accent); font-style: italic; }
  .sub {
    font-size: 14px; color: var(--dim);
    max-width: 520px; margin-bottom: 22px;
  }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 0 0 22px; }
  .kpi {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 12px 10px;
  }
  .kpi-big { font-family: Georgia, serif; font-size: 26px; color: var(--accent); line-height: 1; }
  .kpi-label { font-size: 11px; font-weight: 600; margin-top: 6px; }
  .kpi-sub { font-size: 10px; color: var(--dim); margin-top: 3px; line-height: 1.35; }

  h2 {
    font-family: Georgia, serif; font-size: 16px;
    margin: 18px 0 8px; letter-spacing: -0.005em;
  }
  .features { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 22px; margin-bottom: 14px; }
  .feature { font-size: 12px; padding: 5px 0; border-bottom: 1px dashed var(--border); display: flex; gap: 8px; }
  .feature strong { color: var(--ink); }
  .feature .desc { color: var(--dim); }
  .feature::before { content: "✓"; color: var(--accent); font-weight: 700; }

  .compare {
    margin: 14px 0 18px;
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    overflow: hidden;
  }
  .compare table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .compare th, .compare td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
  .compare th { background: #f3f0e8; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--dim); }
  .compare td.allsale { background: rgba(255,79,0,0.06); font-weight: 600; }
  .compare tr:last-child td { border-bottom: 0; }

  .quote {
    margin: 14px 0 18px;
    padding: 12px 16px; border-left: 3px solid var(--accent); background: var(--card);
    font-style: italic; font-size: 12px; color: var(--dim);
  }
  .cta {
    margin-top: 18px; padding: 16px 18px; background: var(--ink); color: #fff;
    border-radius: 10px; display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px;
  }
  .cta-text { font-size: 13px; }
  .cta-text strong { display: block; font-family: Georgia, serif; font-size: 18px; margin-bottom: 2px; }
  .cta-btn {
    background: var(--accent); color: #fff; padding: 10px 18px; border-radius: 999px;
    font-weight: 600; text-decoration: none; font-size: 13px; white-space: nowrap;
  }
  .footer { margin-top: 14px; font-size: 10px; color: var(--dim); text-align: center; }
  .print-hint {
    text-align: center; margin: 22px 0 0; font-size: 11px; color: var(--dim);
  }
  @media print {
    body { background: white; }
    .print-hint { display: none; }
  }
</style>
</head>
<body>
<div class="page">

  <div class="brand">
    <div class="brand-mark">A</div>
    <div class="brand-name">Allsale Events</div>
  </div>

  <h1>Sell out faster. <em>Keep&nbsp;every dollar.</em></h1>
  <p class="sub">
    Aotearoa's ticketing platform for independent promoters, venues and event organizers. You set the ticket price. You keep 100% of it. Payouts hit your bank just 5 days after the event.
  </p>

  <div class="kpis">
    <div class="kpi">
      <div class="kpi-big">100%</div>
      <div class="kpi-label">Face value, yours</div>
      <div class="kpi-sub">Price the show. Keep every dollar. No platform cut — ever.</div>
    </div>
    <div class="kpi">
      <div class="kpi-big">5 days</div>
      <div class="kpi-label">Payout after event</div>
      <div class="kpi-sub">Industry-fastest. Direct to your bank via Stripe.</div>
    </div>
    <div class="kpi">
      <div class="kpi-big">$0</div>
      <div class="kpi-label">To list an event</div>
      <div class="kpi-sub">Free seat maps, free QR scanning, free dashboard.</div>
    </div>
    <div class="kpi">
      <div class="kpi-big">70/30</div>
      <div class="kpi-label">Auto revenue splits</div>
      <div class="kpi-sub">Co-promoting? Split one event across multiple Stripe accounts — automatically.</div>
    </div>
  </div>

  <h2>What you get out of the box</h2>
  <div class="features">
    <div class="feature"><span><strong>Drag-build seat maps</strong> <span class="desc">— rows, aisles, blocked seats, bulk range select.</span></span></div>
    <div class="feature"><span><strong>Tiered pricing</strong> <span class="desc">— Early Bird → GA → VIP with capacity caps.</span></span></div>
    <div class="feature"><span><strong>Promo &amp; affiliate codes</strong> <span class="desc">— 30-day cookie tracking + commission rollup.</span></span></div>
    <div class="feature"><span><strong>Auto FIRST50 launch promo</strong> <span class="desc">— every approved event gets a kickstart code.</span></span></div>
    <div class="feature"><span><strong>Self-serve refunds</strong> <span class="desc">— set your own cut-off, attendees handle it.</span></span></div>
    <div class="feature"><span><strong>Ticket transfers</strong> <span class="desc">— recallable, QR rotates, full audit trail.</span></span></div>
    <div class="feature"><span><strong>Waitlists</strong> <span class="desc">— auto-notify when a sold-out seat frees up.</span></span></div>
    <div class="feature"><span><strong>Embeddable widget</strong> <span class="desc">— drop a 2-line script on your own site.</span></span></div>
    <div class="feature"><span><strong>Real-time QR scanning</strong> <span class="desc">— door-staff app, no extra hardware.</span></span></div>
    <div class="feature"><span><strong>Live sales dashboard</strong> <span class="desc">— track every booking as it happens.</span></span></div>
    <div class="feature"><span><strong>Follower base</strong> <span class="desc">— attendees subscribe + get weekly digests.</span></span></div>
    <div class="feature"><span><strong>Email marketing built in</strong> <span class="desc">— message your ticket holders directly.</span></span></div>
  </div>

  <h2>How we compare</h2>
  <div class="compare">
    <table>
      <thead>
        <tr>
          <th></th>
          <th class="allsale">Allsale</th>
          <th>Typical platform</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Platform cut from your ticket price</td><td class="allsale">0%</td><td>10–20%</td></tr>
        <tr><td>Payout window</td><td class="allsale">5 days post-event</td><td>30+ days</td></tr>
        <tr><td>Influencer affiliate codes (built-in)</td><td class="allsale">Free</td><td>Add-on or unavailable</td></tr>
        <tr><td>Multi-organizer revenue splits</td><td class="allsale">Automatic per booking</td><td>Manual spreadsheets</td></tr>
        <tr><td>Custom seat maps + bulk seat-block</td><td class="allsale">Free</td><td>Paid feature</td></tr>
        <tr><td>Embed widget on your own website</td><td class="allsale">Free</td><td>Usually paid</td></tr>
      </tbody>
    </table>
  </div>

  <div class="quote">
    &ldquo;The night is yours. Tickets are limited.&rdquo; — Built in NZ for promoters who care where their money goes.
  </div>

  <div class="cta">
    <div class="cta-text">
      <strong>Bring your next event home.</strong>
      Build, list, and start selling in under 10 minutes. No platform tax. No payout delays. No scalpers.
    </div>
    <a class="cta-btn" href="https://www.allsale.events/signup">Get started →</a>
  </div>

  <div class="footer">
    www.allsale.events · hello@allsale.events
  </div>

  <p class="print-hint">Tip: Press <strong>Ctrl/Cmd + P</strong> → &ldquo;Save as PDF&rdquo; to download this as a one-page handout.</p>
</div>
</body>
</html>
"""


@router.get("/marketing/pitch.html", response_class=HTMLResponse)
async def pitch_html():
    """Public one-page promoter pitch. Print-friendly. Share this URL in DMs."""
    return HTMLResponse(content=_PITCH_HTML, headers={
        "Cache-Control": "public, max-age=3600",
        "Access-Control-Allow-Origin": "*",
    })
