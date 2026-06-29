# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform with full partner-revenue ecosystem. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel + Railway.

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe, Resend, Google OAuth, GA4, Emergent LLM Key (Gemini 2.5 Pro)

## Partner / Revenue Programs (4)
1. Affiliates (per-event promo codes)
2. Organizer referrals (flat $50 credit)
3. Influencer hub (event promoters)
4. **Marketing Lead Partners** — admin-controlled lead-gen, configurable % of platform commission on every paid booking, recurring forever. Now includes monthly statement emails + self-serve partner portal at `/partner`.

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Admin → Organizer creation + Event on-behalf-of, real-time Admin↔Organizer chat + typing indicators
- Eventfinda layout, image proxy, sidebar poster, ZIP flyer + Poster-First + AI text overlay
- Blog + SEO + newsletter signup + subscriber fan-out + unsubscribe page
- Protection P&L widget + Marketing Lead Partners
- **Admin Hero Strip (NEW)**: 4 stat cards above tabs at `/admin` — Protection net pool, pending claims, lead-partners unpaid, lead-partners active. Click-through to relevant tab.
- **Marketing partner monthly statements (NEW)**:
  - Template `marketing_partner_statement` in `emails.py` with period/unpaid/lifetime boxes + recent earnings table
  - Endpoint `POST /api/admin/marketing-partners/send-statements` (admin-triggered; cron-able). Stamps `last_statement_sent_at` per partner. Admin button "Email monthly statements" in the Lead partners tab.
- **Partner self-serve portal (NEW)**:
  - Admin grants access via `POST /api/admin/marketing-partners/{id}/grant-portal-access` — creates a `role=partner` user with `linked_partner_id` (or links existing user). Admin shares credentials out-of-band.
  - Public page `/partner` (`PartnerPortal.jsx`) — read-only dashboard with 3 stat cards (organizers / lifetime / unpaid), attached-organizers list, earnings ledger, mailto-Allsale link
  - Backend `GET /api/partner/me` + `GET /api/partner/me/earnings` require `linked_partner_id` on the calling user
  - Read-only on purpose: admin still controls payouts

## Recently Completed (Feb 2026 — current session)
- **Revenue hero card on `/admin/revenue` (Feb 28 2026, iter_28)** — answered the user's question "where can I see my collection amount?" by surfacing it as the dominant visual element above the per-booking table:
  - New endpoint `GET /api/admin/revenue/headline` aggregates current-month + previous-month + today buckets in 3 Mongo pipelines (cheap — uses ISO `paid_at` prefix comparison instead of date casting).
  - Returns `{current_month: {gross, platform_fees, count, currency, label, start, end}, previous_month: {...}, delta_percent, today_fees, today_count}`.
  - Frontend `AdminRevenue.jsx` hero card: huge serif "NZ$XX.YZ" platform-earnings amount + delta-vs-last-month chip (green +X% / red -X%) + "+ NZ$Y today" sub-line. Comparison block on the right shows previous month's total + count. Warm orange gradient background, accent-colored border. Empty-state message: "No paid bookings yet this month — when buyers purchase tickets, your 1% + $0.50 platform fee will appear here."
  - **Tests:** 4 new pytest cases (`test_admin_revenue_headline.py`). All pass. Live screenshot confirmed: "YOUR PLATFORM EARNINGS · JUNE 2026 / NZ$13.50 / From 1 paid booking so far this month" + right-side MAY 2026 / NZ$0.00 comparison.

- **AI flyer progress UI (Feb 28 2026, iter_27)** — fixed the 15-20s "looks broken" wait on `/events/{id}/share` → "Add AI text overlay":
  - New `AiFlyerProgress.jsx` inline progress card with rotating stage messages, asymptotic progress bar (capped at 95% until API returns), pulsing icon, elapsed-time counter, and a "taking longer than usual" honesty line after 15s.
  - 4 stages keyed to observed P50 latency: 0s "Reading your event details…", 5s "Drafting a punchy headline…", 10s "Polishing the tagline & CTA…", 16s "Almost done — finalising the text…".
  - Asymptotic curve `95 × (1 - exp(-t/8))` — rewarding fast start (30% by 3s, 60% by 8s, 82% by 15s), never claims 100% prematurely.
  - On success, parent sets `aiFinished=true` → card jumps to 100% with a green CheckCircle flash for 700ms before unmounting.
  - **Tests:** 9 jest unit tests for the math + stage selection (`AiFlyerProgress.math.test.js`) — all pass. Verified live via Playwright: progress card mounts on click, stage label updates, percent ticks up (40% at 4.5s → 55% at 7s).

- **Mixed-model softening (Feb 28 2026, iter_26b)** — user decision: manual payouts stay as the platform's default; Stripe Connect is an *opt-in upgrade* for organizers who want instant payouts:
  - **Email template `organizer_stripe_setup_nudge` rewritten** — old copy ("payouts will be held in escrow until you connect") → new soft tone ("Optional upgrade for faster payouts. No rush — manual bank transfers continue to work exactly as before."). Subject changed to "Want faster payouts? Connect Stripe (optional)".
  - **Organizer banner re-themed** (`OrganizerStripeConnectWarning.jsx`):
    - Color: rose/amber alarm → sky/emerald gradient with a Zap icon.
    - Copy: "ACTION REQUIRED · Stripe Connect not set up" → "Optional upgrade · faster payouts" with "Want your ticket revenue to land instantly?" headline.
    - Now **dismissible** (X button + "Maybe later") → stores `stripe_connect_invite_dismissed_at` in localStorage and hides for 7 days.
    - CTA copy: "Connect Stripe now" → "Try Stripe Connect".
  - **Admin tab re-labeled** (`AdminStripeConnectStatusTab.jsx`):
    - Title: "Stripe Connect status" → "Stripe Connect adoption". Nav label: "Connect status" → "Connect adoption".
    - KPI card: "🔴 Not connected" → "⚪ Manual payouts" (slate-coloured, no alarm).
    - Status badge: "🔴 Not connected" / rose chip → "⚪ Manual payouts" / slate chip.
    - Uncollected-revenue banner re-themed: amber alarm → sky info ("This works fine and will continue. Invite the ones who want faster payouts below.")
    - Bulk button: "Email all 🔴 organizers (52)" / emerald → "Invite 52 manual organizers to try Stripe" / sky.
    - Per-row button: "Send reminder" → "Invite to Stripe".
    - Confirm dialog softened: "Send reminder email to ALL organizers" → "Send a friendly 'try Stripe Connect for faster payouts' invite".


  - User context: Phase B deployed to production, but Stripe's "Collected fees" tab is still empty because 0 production organizers have completed Stripe Connect onboarding. All historical 38 paid charges happened pre-Phase-B, structured as single charges on Allsale's master account (Settlement merchant: Allsale Events / Transferred to: —) — those are immutable, will never show app fees in Stripe.
  - **Admin tab `/admin?tab=stripe-connect`** (component: `AdminStripeConnectStatusTab.jsx`):
    - 4 KPI cards: Total organizers, 🟢 Connected, 🟡 Onboarding incomplete, 🔴 Not connected.
    - Amber "uncollected revenue" banner showing total $$$ that went to non-connected organizers.
    - Filter pills + table with per-organizer revenue + last-paid + last-reminder timestamps.
    - **"Email all 🔴 organizers" bulk button** → blasts the existing `organizer_stripe_setup_nudge` template via the rate-limited fire-forget queue (respects Resend's 2 req/sec cap).
    - **Per-row "Send reminder"** for targeted nudges.
    - CSV export with full table.
  - **Backend endpoints (`/app/backend/routers/admin.py`):**
    - `GET /api/admin/stripe-connect-status` — aggregates paid revenue per organizer via single Mongo pipeline (bookings→events lookup), sorts by lifetime_revenue DESC.
    - `POST /api/admin/stripe-connect-status/remind` — accepts `user_ids: [...]` for targeted or `user_ids: null` for blast. Idempotent: re-checks `stripe_charges_enabled` per-target inside the loop so an admin double-clicking can't re-spam someone who just connected. Stamps `stripe_nudge_sent_at` + `stripe_nudge_sent_by`.
  - **Organizer-facing warning banner** (`OrganizerStripeConnectWarning.jsx`): Hard-warning red/amber banner on `/organizer` shown ONLY when the organizer has paid revenue AND `stripe_charges_enabled !== true`. Shows lifetime $$$ and a one-click "Connect Stripe now" CTA that fires `POST /stripe/connect/onboard`. Auto-hides on connect.
  - **Tests:** 5 + 3 new pytest cases (`test_admin_stripe_connect_status.py` + `test_iter26_stripe_connect_remind.py`). All 8 pass. Testing agent (iter_26): 100% pass (backend 8/8, frontend 13/13), no bugs, no blocking action items.

- **Phase B: Stripe Connect Destination Charges — admin's #1 ask fulfilled (Feb 28 2026)**:
  - User reported: "I can see the charges but I can't see the collection fees. I can't see my cut." Phase A (Admin Revenue Dashboard at `/admin/revenue`) exposed the platform cut in-app; Phase B makes it visible **natively in the Stripe Dashboard** as a separate `application_fee` line per charge.
  - **Backend (`routers/payments.py`):**
    - 3 new helpers: `_should_use_destination_charge(booking, organizer)`, `_application_fee_cents(booking)`, `_build_destination_charge_session(...)`.
    - `checkout_session` now routes through `stripe.checkout.Session.create(payment_intent_data={application_fee_amount, transfer_data: {destination: <organizer_stripe_account>}})` when the organizer has Connect + `stripe_charges_enabled=true` AND the booking has no gift-card redemption (gift cards stay on legacy to avoid underfunding the connected account).
    - Math: `application_fee_amount = booking.amount - booking.face_value` (= `service_fee` + any protection surcharge). Both exclusive and absorb_fees modes covered — verified by unit tests against `fees.compute_fees()`.
    - Graceful fallback: any error during destination-charge creation (e.g., Stripe rejects a stale acct_id) is logged and falls through to the legacy emergent-wrapper path. No 500s for the buyer.
    - Bookings flagged `stripe_destination_charge=True` + `stripe_connect_account_id` for downstream auditing.
  - **Backend (`routers/payouts.py`):** `_eligible_bookings_for_payout` now excludes `stripe_destination_charge=True` bookings — those were already settled to the organizer's connected account at checkout; including them would double-pay. Mongo's `$ne: True` correctly matches legacy bookings (missing field).
  - **Effect on admin's Stripe dashboard:** every Connect-routed charge now shows the platform's `application_fee_amount` as its own line — admin can finally see their 1% + $0.50 cut without a custom report.
  - **Tests:** 15 new pytest cases in `test_stripe_destination_charges.py` (gating + math + payout exclusion) + 9 new HTTP integration cases in `test_iter25_phase_b_integration.py` (smoke + legacy organizer + fake-acct fallback + payouts exclusion + admin revenue + public settings shape). **24/24 pass.** Testing agent (iter_25): no critical issues, no action items.
  - **Pre-existing fix:** also corrected `platform_settings.commission_percent` from 8.0 → 1.0 in the DB (test environment had drifted) and patched `tests/test_stripe_connect.py` to include the now-mandatory `phone` field on auth/register.
  - **Hold/payout semantics (note for ops):** Funds split at charge time means organizer's connected account holds the money per Stripe's default rolling payout schedule (typically 7-day for new accounts). To enforce the 5-day-after-event hold, set the connected account's payout schedule to `manual` and trigger payouts post-event via a future scheduler tick. This is operator-configurable — not a blocker for Phase B.

- **Fee math fix: platform_flat split from stripe_flat — 1% + $0.50 now collected correctly (Feb 26 2026)**:
  - User reported: "I could see the fee in my stripe account, we charge 1% + 0.50 cent fees."
  - **RCA:** The old `compute_fees()` only had `stripe_flat` parameter. Admin's `commission_flat_fee_per_ticket` ($0.50 platform flat) was being passed as `stripe_flat`, OVERWRITING Stripe's actual $0.30. Net effect: platform was under-collecting by $0.30 per ticket — the $0.50 was being used to cover Stripe's $0.30 instead of being kept by the platform. Also the env default was wrong (5% platform fee instead of the user's actual 1%).
  - **Fix:**
    1. Added separate `platform_flat` parameter to `compute_fees()`. Platform fee is now `face × platform_pct + platform_flat` (independent of Stripe's flat).
    2. Updated env defaults to match user's real rates: `PLATFORM_FEE_BPS=100` (1%), `PLATFORM_FEE_FLAT=0.50`, `STRIPE_FEE_FLAT=0.30` (unchanged).
    3. Updated `routers/bookings.py` to pass `admin_flat` as `platform_flat` (not `stripe_flat`).
    4. Updated DB doc `platform_settings.commission` to `commission_percent=1.0, commission_flat_fee_per_ticket=0.50` (was 5.0 / 0.30).
    5. Updated `GET /api/fees/public-settings` to expose `stripe_flat_per_ticket` so the frontend can render the exact buyer total.
  - **Live-verified:** NZ$25 Early Bird → face $25.00, platform_fee **$0.75** (1% × 25 + $0.50), stripe_fee $1.02, buyer pays **NZ$26.77**. Admin's Stripe will now actually see $0.75 of platform revenue per ticket.
  - **Tests:** 7 new pytest cases in `test_fees_platform_flat.py` covering: default rates, $25-ticket spot check, platform_flat independence from stripe_flat, override precedence, absorb_fees mode breakdown, public endpoint shape, breakdown.as_dict() carries both flats. **102/102 backend tests pass.**

- **Resend 429 retry-with-backoff — admin booking notifications now reliable (Feb 26 2026)**:
  - User reported: "admin can't receive the payment confirmation. When customer can buy make sure organizer and admin both can get paid."
  - **RCA:** Resend free tier rate-limits at **2 req/sec**. Each booking fires 3 emails in parallel (buyer + organizer + admin). The DB showed **18/24 admin emails failed with 429** and 12/24 organizer emails failed with the same rate-limit error.
  - **Fix:** `emails._resend_send_with_retry()` wraps `resend.Emails.send` with exponential backoff (400ms → 800ms → 1.6s → 3.2s, up to 4 attempts) on rate-limit errors. Non-rate-limit errors (auth, invalid recipient) still raise on the first attempt — retrying those would just delay the inevitable.
  - **Bonus:** `email_logs` rows now carry `booking_id` when ctx has one, so admin support can answer "did Alice's confirmation email go out?" with a single query. Closed the open backlog item from earlier turns.
  - **Tests:** 5 new pytest cases in `test_email_rate_limit_retry.py` covering: retry succeeds, retry exhausts, non-rate-limit fails fast, end-to-end log shape stays clean (one `sent` row, not one-per-attempt), booking_id cross-link present. **95/95 backend tests pass.**
  - **Verified live:** triggered booking-confirmation fan-out on `bk_partner_test_001` → admin email rate-limited twice (`attempt 1/4`, `attempt 2/4`), retried, **succeeded on attempt 3**. All three emails (buyer + organizer + admin) now land reliably.
  - **Payout flow audit:** ran `fees.compute_fees(100.0)` for both modes — confirmed math is correct: buyer-pays-fees: buyer NZ$108.22 → Stripe NZ$3.22 + platform/admin NZ$5.00 + organizer NZ$100.00. Absorb-fees: buyer NZ$100 → Stripe NZ$3.00 + platform/admin NZ$5.00 + organizer NZ$92.00. The `payouts.py` flow uses face_value as the single source of truth and admin's platform_fee is collected at checkout time.

- **Polished EventCard redesign — text moves above & below the poster (Feb 26 2026)**:
  - User reference: premiertickets.co style — clean poster on top, price + date + title below, no chrome covering the organizer's poster art.
  - **Changes (`components/EventCard.jsx`):** removed the full dark gradient overlay; kept only a 25%-top scrim for badge legibility. Removed the bottom-image overlay block (date + price). Below the image now reads top-to-bottom: small "STARTS FROM" label → big serif **NZ$XX.XX** price → date row with calendar icon and uppercase locale-formatted timestamp → serif title → venue line → organizer & creator faces. Price now uses 2-decimal precision (NZ$25.00) to match the reference exactly.
  - **Also polished `TrendingCarousel`/`TrendingTile`** (used on the home page) to the same clean layout — was still showing a price pill overlay on the poster. Now: clean poster + top-only scrim → "Starts from" label → big serif price → date → title → venue, all below the image.
  - **Verified live:** Geeta Rabari card on `/events` shows the polished layout. Home page featured grid (EventCard) and trending carousel (TrendingTile) both use the same polish pattern now. Lint clean.

- **Geo-IP auto-detect for the homepage country picker (Feb 26 2026)**:
  - User opted into the previous turn's improvement offer ("Yes").
  - **Backend (`/api/geo/country`):** new endpoint. Resolution order — (1) CDN edge headers (`cf-ipcountry`, `x-vercel-ip-country`, `fastly-geo-country`, `x-country-code`, `x-appengine-country`), (2) IP-based lookup via `ipapi.co` keyed off `x-forwarded-for` / client IP, with a 5-min in-memory TTL cache (capped at 2k entries) so repeat hits never hammer the upstream, (3) `NZ` default. Returns `{country, source: "header"|"ip"|"default"}`.
  - **Frontend:** new `"AUTO"` sentinel triggers the geo call only on first visit (no localStorage entry). Existing user selections always take precedence — we never overwrite an explicit choice. Trigger button shows "Detecting…" briefly while the call is in-flight.
  - **Live-verified:** cleared localStorage → reload → picker auto-set to "🇺🇸 United States" (test runner's IP), persisted to localStorage, empty-state CTA visible because US has no events. Real Indian/UAE visitors will auto-land on their market.
  - **Tests:** 6 new pytest cases in `test_geo_country_detection.py` covering header priority, header normalisation (lowercase → upper), invalid values (`XX`), response-shape contract, and the TTL cache. **90/90 tests pass across new + existing suites.**

- **Country picker on home page + organizer pre-launch checklist (Feb 26 2026)**:
  - User requested: country selector on home page + (from previous turn's offer) the pre-launch readiness widget.
  - **Country picker (`components/CountryPicker.jsx` + `pages/Landing.jsx`):** new component fed by the existing `GET /api/events/countries`. Two instances on the landing page (hero + above the featured grid). Persists choice to `localStorage["allsale_selected_country"]`. Refetches featured events with `?country=` when changed. Empty-state CTA when the selected country has zero events ("Show events from all countries"). Backend `GET /api/events/featured` now accepts `?country=` (backwards-compatible — no param = global feed).
  - **Pre-launch checklist (`components/OrganizerLaunchChecklist.jsx`):** new widget on `/organizer` (above StripeConnectPanel). Ticks 5 items: Stripe Connect, phone, profile photo, refund policy on ≥1 event, first event published. Shows progress bar + per-item hints + click-to-fix shortcuts. Auto-hides once all 5 are done. Built from existing endpoints — no new backend code.
  - **Verified live:** hero picker → AE returned 6 cards, NZ returned full list, choice persisted to localStorage; new organizer dashboard shows `1/5 complete · 20%` (phone ✓, rest ✗) — clickable rows route to /profile, /organizer, /organizer/new.
  - **Tests:** all 119 prior tests still pass. Lint clean on the two new components.

- **Stripe Connect gate on event publish (Feb 26 2026)**:
  - User requested: organizers must set up their Stripe bank account before they can publish a paid event (or get a reminder). Chose Option A — hard block on paid events, free events skip.
  - **Backend (`routers/events.py`):** new helper `_event_is_paid()`. Both `POST /events` and `PATCH /events/{id}` now return **402** `{code: "stripe_payouts_required", message, onboarding_path}` when a non-admin organizer tries to publish/flip a paid event without `stripe_payouts_enabled=true`. Admins are exempt. Free events (all tier prices == 0) skip the gate.
  - **Email:** new dedicated `organizer_stripe_required` template (sent the instant the 402 fires) with the 1-click `/organizer?stripe_return=1` onboarding URL, ID/bank/address checklist, and "free events don't need Stripe" disclaimer. The existing passive `organizer_stripe_setup_nudge` is unchanged.
  - **Frontend (`pages/CreateEvent.jsx`):** new sticky red banner above the form when the organizer has paid tiers AND no Stripe connected — surfaces the requirement BEFORE they hit submit. Inline "Connect Stripe now →" button starts onboarding immediately. If they still try to submit (or the state is stale), the 402 handler auto-refreshes the Stripe status and forwards them to the Stripe onboarding URL. The persistent `StripeConnectPanel` on `/organizer` already covers the dashboard-level reminder.
  - **Tests:** 6 new pytest cases in `test_stripe_connect_publish_gate.py` covering: (1) paid+no-stripe → 402, (2) free+no-stripe → 200, (3) paid+stripe-enabled → 200, (4) admin bypass, (5) email template registered & rendering, (6) PATCH edit gate when free→paid. **111/111 backend tests pass, frontend lint clean.**
  - **Verified live:** registered a fresh organizer in-browser, navigated to `/organizer/new` → red banner visible (count=1) with default $50 tier; set tier price to 0 → banner disappears (count=0).

- **Country → local currency for invoice + frontend (Feb 26 2026)**:
  - User reported: "make sure all country have their own currency show in invoice and frontend as well." 21+ countries (Qatar, Kuwait, Bahrain, Oman, Israel, Pakistan, Bangladesh, Sri Lanka, Nepal, Vietnam, Taiwan, Nigeria, Kenya, Egypt, Ghana, Argentina, Chile, Colombia, Turkey, Morocco, Czech Republic) wrongly defaulted to USD/EUR.
  - **Fix:**
    1. `frontend/src/lib/countries.js` — corrected every country's `currency` to its ISO-4217 local code (QAR, KWD, BHD, OMR, ILS, PKR, BDT, LKR, NPR, VND, TWD, NGN, KES, EGP, MAD, GHS, ARS, CLP, COP, TRY, PLN, CZK, FJD).
    2. `frontend/src/lib/currencies.js` — added 23 new currencies with proper symbols (₪/₨/৳/₫/NT$/₦/₵/₺/zł/Kč/etc). Catalog now covers **48 currencies**.
    3. `backend/emails.py` — `_money()` symbol map mirrored to all 48 currencies so invoices render the right symbol per country.
  - **Tests:** 25 parametrised currency-symbol tests + 31-country pin tests + completeness test (every country's currency MUST be in `_money()` symbol map). **105/105 backend tests pass.**
  - **Verified live:** create-event page shows 48 currencies + 58 countries; picking India → currency auto-flips to INR, Qatar → QAR, Pakistan → PKR, Vietnam → VND.

- **Bug fix: invoice / booking-confirmation emails showed USD on every booking (Feb 26 2026)**:
  - User reported: "in invoice it shows USD $ change with the country." Confirmed live — a NZD booking for $200 displayed `$200.00 USD` in the email body and text fallback.
  - **RCA:** `emails._money()` defaulted to `currency="USD"` *and* every call site invoked it as `_money(ctx.get('amount', 0))` without passing the booking's currency. The `_send_booking_confirmation_email` ctx in `payments.py` also didn't include `currency` (only the PDF context did — the PDF was correct, only the email body was wrong).
  - **Fix:** `_money()` now defaults to NZD and renders the correct symbol per ISO-4217 code (NZ$/A$/US$/£/€/₹/AED/CHF/R$/etc — full mirror of `frontend/src/lib/currencies.js`). All 9 call sites (booking-confirmation, refund-issued, organizer-payout) now pass `ctx.get('currency')`. `payments.py` and `payouts.py` include `currency` in the email ctx so the right value flows through.
  - **Tests:** 14 new pytest cases in `test_email_currency.py` cover 9 currency codes, default fallback, missing-currency fallback, and the three live templates. **30/30 email + auth tests pass.**
  - **Verified live:** triggered admin resend on the $200 NZD booking → Resend log shows `currency: NZD`, status `sent`, resend_id `343ecb0f...`. Buyer's email now reads **NZ$200.00**, not "$200.00 USD".

- **Bug fix: PhoneCaptureGate kept re-asking for a phone even after the user had saved one (Feb 26 2026)**:
  - User reported: "make sure mobile number once they added do not ask every time." Reproduced live — the gate showed for the admin account even though admin had `+64 21 555 0001` in the DB.
  - **RCA:** All four auth endpoints (`POST /auth/login`, `/register`, `/google-code`, `/google-session`) returned a user dict **without `phone`**. Frontend `setUser(data)` overwrote the auth-context user with a phone-less object → `PhoneCaptureGate`'s `!user.phone` check fired immediately after every login. `GET /auth/me` (called separately) did return phone, but the login response always raced ahead.
  - **Fix:** All four auth endpoints now echo `phone` in their response. Google endpoints re-read the user doc so they pick up phones saved during a prior session.
  - **Tests:** 4 new pytest cases in `test_auth_phone_in_response.py` pin the response contract. **All 57 auth + creator + partner tests still pass.**
  - **Verified live:** logged in as admin in the browser → no gate appears, user lands on `/admin` with phone persisted in context.

- **Bug fix: booking-confirmation e-tickets were silently failing (Feb 26 2026)**:
  - Buyers reported they never received their PDF tickets after paying. `email_logs` showed every `booking_confirmation` row as `status='failed', reason='Object of type bytes is not JSON serializable'`.
  - **RCA:** Resend Python SDK v2.30.1 requires attachment `content` to be a base64 string or `list[int]`. `routers/payments._send_booking_confirmation_email` was passing the raw `bytes` returned by `ticket_pdf.build_ticket_pdf` straight through. Resend's `json.dumps` choked on bytes; the helper's broad `except` swallowed it so checkout looked fine and the buyer got nothing.
  - **Fix:** `emails._normalize_attachments()` (new helper) base64-encodes bytes/bytearray/memoryview before passing to Resend; passes through str + list[int]; drops + logs anything else so a single bad attachment never blocks the send. Called once in `send_template()` — all current and future callers benefit.
  - **Tests:** 8 new unit tests in `test_email_attachment_bytes.py` + 6 new HTTP integration tests in `test_iter24_email_resend_api.py`. 14/14 pass. Verified end-to-end via testing_agent_v3_fork: real resends produce `status='sent'` rows with real Resend UUIDs; bytes-bug error count stays flat at the single pre-fix historical row.


  - **Bug fix: payout double-counting** — `payouts.py` (`/organizer/payouts/balance` and `/payouts/request`) now uses `sum(b.face_value)` instead of `sum(b.amount)` + second commission deduction. The platform fee was already routed at checkout via `compute_fees()`; deducting it again at payout was inflating the organizer's payout (~$51 instead of $50) and starving Allsale's margin. Fix: net = gross = sum(face_value). Works correctly in both exclusive AND absorb fee modes.
  - **Featured events sort first** — `/api/events` now ranks `featured` → `is_boosted` → date asc. Admin-curated picks land at the top of the discovery feed without manual rearrangement.
  - **Event cards now show organizer logo + creator avatar strip** — `events.py._attach_face_avatars()` batches both lookups (no N+1). `EventCard.jsx` renders the organizer's picture + name on a dedicated footer row, plus an avatar stack of up to 3 active creators promoting the event. `Featured` badge added on the cover.
  - **Backend tests:** 4 new pytest cases — featured-first sort, organizer_picture present, featured_creators present, payout balance no-double-deduction. **27/27 pass.**

- **Test credentials file refreshed (Feb 26 2026)**:
  - Corrected `orgtester` user_id (was stale).
  - Added current user_ids for admin + partner.
  - Backfilled phone numbers on admin / partner so the new `PhoneCaptureGate` doesn't intercept automated test flows.
  - Documented live fee rates + `PAYOUT_MIN_USD` constant so future agents don't guess.

- **Influencer commission system — end-to-end completion (NEW)**:
  - **Payout request now includes creator_earnings** (FIX): `POST /api/influencer/payouts/request` previously only summed legacy `affiliates` campaign revenue; it ignored the new `creator_earnings` rows from admin/organizer-assigned codes. Money was credited but invisible to the payout flow. Now drains BOTH ledgers, flips matched `creator_earnings` rows to `requested`, stamps the payout_id for clean reconciliation.
  - **Per-influencer summary endpoint** (`/api/{admin,organizer}/events/{event_id}/influencer-summary`) — one row per creator aggregating across all their codes for the event: tickets sold, bookings, revenue, commission credited/unpaid, plus the creator's avatar + display name + follower count. Sorted by tickets-sold leaderboard.
  - **"Influencers driving sales" leaderboard** added at the top of `OrganizerCreatorCodesPanel.jsx` — 3 KPI stat cards (tickets/revenue/unpaid commission) + ranked rows with avatar, code count, tickets, revenue, earnings.
  - **$50 minimum payout** confirmed working (`PAYOUT_MIN_USD = 50.0`).
  - **Backend tests**: 3 new pytest cases — summary endpoint, foreign-event 403, payout threshold block. **23/23 pass.**

- **Per-event "fees included vs on top" toggle (NEW)**:
  - `EventIn.absorb_fees: bool = False` — organizer picks fee presentation per event.
  - `compute_fees(absorb_fees=True)` reverses the gross-up: buyer pays exactly the displayed ticket price; platform + Stripe fees are deducted from the organizer's payout. Default behavior unchanged.
  - `bookings.py` passes `event.absorb_fees` through to `compute_fees` and persists the flag on each booking for downstream reporting.
  - `FeePresentationToggle.jsx` — new 2-card radio in `CreateEvent.jsx` with live preview (sample ticket price → Buyer pays / You receive in both modes).
  - `EventDetail.jsx` — when `event.absorb_fees=true`, the per-tier card shows **"all fees included"** instead of "$X + $Y fees", and the Total line uses the displayed price.
  - **Backend tests:** 3 new pytest cases — exclusive regression, absorb math, $0 comp safety. **20/20 pass.**

- **Bug fix: "AI unavailable" error in support chat (NEW)**:
  - Both support-chat AI endpoints (`POST /support/faq/ask` and `POST /admin/support/suggest`) previously called `openai/gpt-5.1` directly and surfaced any transient auth/outage blip as a hard 502 to the visitor.
  - Added a shared `_support_ai_complete()` helper with a 3-provider fallback chain (Gemini Flash → GPT-5.1 → Claude Haiku 4.5) — same pattern as `flyer_ai.py`. Auth errors short-circuit the chain to avoid 3× latency.
  - On TOTAL failure (every provider down) both endpoints return a friendly 200 response with `degraded:true` (suggest) or `can_help:false` (FAQ auto-escalates to human) instead of a red error toast.
  - Verified live: works on first try with key set; with key corrupted → still 200 + safe fallback text + auto-escalation; restored cleanly.

- **Phone number is now mandatory for every account (NEW)**:
  - `models.RegisterIn.phone` is required (`Field(..., min_length=6, max_length=20)`).
  - `/auth/register` validates with `_PHONE_RE` (lenient international: digits + optional + / space / dash / brackets); persists to `users.phone`.
  - `Signup.jsx` adds a phone input between email and password with the `Phone` lucid icon.
  - `PhoneCaptureGate.jsx` — non-dismissible app-wide modal rendered from `Layout.jsx` that intercepts any logged-in user whose `phone` is missing (Google OAuth signups + pre-existing accounts). PATCHes `/auth/me` and re-syncs `useAuth().user` on save.
  - **Backend tests:** 3 new pytest cases — missing-phone 422, invalid-phone 400, valid-phone persists. Existing `fresh_attendee_session` fixture updated to send phone. **17/17 pass.**

- **Organizers can self-manage creator codes (NEW)**:
  - 5 new `/api/organizer/events/{event_id}/creator-codes` endpoints (POST/GET/PATCH/DELETE + `/organizer/creator-codes/users-search`) mirror the admin set and share the same internal handlers; auth check is `_ensure_can_manage_event(user, event_id)` which lets admins through and 403s when an organizer doesn't own the event.
  - `OrganizerCreatorCodesPanel.jsx` — new panel rendered inside `OrganizerEvent.jsx` (between Influencer marketplace and UTM link generator). Lets the event's organizer view code, creator, discount %, commission %, uses, revenue, credited earnings; Add / Edit / Deactivate inline; uses the same modal UX as admin tab.
  - Server explicitly mounts the additional `organizer_router` from `creator_codes.py` so the auto-loader's "one router per module" convention still holds for everything else.
  - **Backend tests:** 4 new pytest cases — list/search/CRUD + cross-owner 403. **14/14 pass.**

- **Creator codes: discount is now OPTIONAL (NEW)**:
  - `routers/creator_codes.py` — `value` is `Optional[float]` (defaults to 0); backend rejects a code only when BOTH discount and commission are absent ("a code with neither has no effect").
  - `AdminCreatorCodesTab.jsx` — discount field labelled "% off (optional)" with `0 = no discount` placeholder + "Leave blank for a commission-only code." helper. Validation only blocks when both discount AND commission are empty.
  - `InfluencerHub.jsx` — commission-only codes render "Commission-only (no buyer discount) · X% commission to you".
  - Creator hub now shows the **"Your promo codes"** section with a clear empty state even when the creator has zero codes (so they know where assigned codes will appear). Mobile "Creator" nav link is now always visible.
  - **Backend tests:** 3 new pytest cases in `test_iter23_creator_features.py` for commission-only / discount-only / neither — 10/10 pass.

- **Creator profile photos + admin-assigned codes auto-show in creator account (NEW)**:
  1. **Avatar upload on `/influencer/onboarding`** — `ImageUploader` integrated at top of the form with a live circular preview. `avatar_url` round-trips through `POST /api/influencer/enable` → `GET /api/influencer/me`.
  2. **`GET /api/influencer/my-codes`** — new endpoint in `routers/influencers.py` returns all admin-assigned `discount_codes` where `creator_id == me`, enriched with event, bookings stats, and creator-earnings ledger (paid/unpaid totals).
  3. **"Your promo codes" on `/influencer`** — InfluencerHub.jsx rewritten with header avatar, an "Edit profile" button, a "Pending payout" stat that sums campaign + code earnings, and a code-by-code grid (code, event, discount, commission, uses, tickets, revenue, earnings) with Copy code + Copy share link + View buttons.
  4. **Homepage Creator Spotlight** — new `components/CreatorSpotlight.jsx` (rendered from `Landing.jsx`) showcases the top 6 enrolled creators with avatars/categories and a "Become a creator" CTA, plus an empty-state recruit panel before the first creator enrols.
  5. **Honest fee copy on `/become-organizer`** — removed hardcoded "8% platform commission + $0.50 per ticket"; perks card + What-changes list now pull live values from `useFeeSettings()` (5% + $0.30) and frame the fee as "added on top, paid by buyers — you keep 100% of your ticket price."
  - **Backend tests** at `/app/backend/tests/test_iter23_creator_features.py` — 7/7 pass.

- **Recruitment flyer system (NEW — 3 features)**:
  1. **Schedule for later** — `flyer_campaigns` collection + 60s `fast_loop` in `scheduler.py` picks up due campaigns and dispatches in 200-recipient chunks with atomic claim. Max 5000 recipients per scheduled campaign.
  2. **CSV import** — Drag-and-drop or file picker on the Recipients box. Regex-extracts all emails from any text/CSV file, dedupes case-insensitively, populates textarea.
  3. **Open/click tracking** — `POST /api/webhooks/resend` (public router) stores events in `email_events`. Admin campaigns table aggregates opens/clicks/bounces per campaign via `resend_ids` join with rate %.
  - Also added campaign label field, Cancel button for scheduled campaigns, and an instrumented "Recent campaigns" history table on the admin tab.
- **AdminFlyersTab UI** — preview iframe via authenticated srcDoc, Send now / Schedule toggle, optional label, CSV upload, validation, campaign history.
- **Two new email templates** in `emails.py`: `organizer_features_flyer` and `influencer_features_flyer` — fully-styled HTML pitches.
- **Help page (NEW)**: Static `/help` page (`/app/frontend/src/pages/Help.jsx`) with three persona tabs (For attendees / For organisers / For partners), each containing 4-6 icon cards with concrete next-action CTAs. Footer link added under "Company" column. "Show me the welcome tour" CTA at the bottom clears all `welcomeSeen_*` flags and dispatches the re-show event.
- **In-app Change Password for partners**: Backend `PUT /api/auth/change-password` + frontend collapsible section in `PartnerPortal.jsx`.
- **E2E backend test suite**: 26 pytest tests at `/app/backend/tests/test_marketing_partners_blog.py` covering Marketing Partner CRUD/attach/earnings/mark-paid/grant-portal/self-serve/change-password roundtrip + Blog subscribe/unsubscribe/resubscribe/admin notify fan-out idempotency. 100% pass rate.
- **Hardened 3 minor issues from testing-agent code review**:
  1. **Cascade cleanup**: `DELETE /api/admin/marketing-partners/{id}` now unsets `linked_partner_id` and flips role to `attendee` on linked portal users.
  2. **Bounded concurrent fan-out**: `notify-subscribers` now uses `asyncio.Semaphore(10)` + `asyncio.gather`.
  3. **DB-level idempotency**: Added unique compound index `partner_booking_unique` on `marketing_partner_earnings(partner_id, booking_id)` + `DuplicateKeyError` catch.
- **Opt-out survey on `/blog/unsubscribe` (NEW)**: After successful unsubscribe, show optional 5-option radio survey (Too many emails / Not relevant / Never signed up / Found better / Other) with comment textarea for "Other". POST `/api/blog/unsubscribe/reason` stamps `unsubscribe_reason`, `unsubscribe_comment`, `unsubscribe_feedback_at` on subscriber doc. Admin aggregate at GET `/api/admin/newsletter/unsubscribe-reasons` returns counts + recent comments. Fixed cramped layout by overriding global `input { width:100% }` for the radio buttons.

## Backlog
- AI flyer generation progress UI (P1 — 15-20s wait, looks broken).
- Twilio/WhatsApp utility notifications (P1 — awaiting user's Option A vs B + Twilio account decision).
- Admin newsletter dashboard widget — surface `/api/admin/newsletter/unsubscribe-reasons` aggregate counts.
- Public "Become a partner" application form (self-serve intake).
- Reseller panel — scope TBD with user.
- Email-confirmation alert on partner password change.
- Gift cards self-service portal (linked in footer; needs implementation).
- (Low priority, from iter_24 review) Retry transient Resend 429s with backoff; include booking_id on email_logs rows for support traceability.

## Critical Notes
- Partner login uses standard `/api/auth/login`; partner role is just `user.role="partner"` + `user.linked_partner_id`
- `marketing_partner_id` on organizer user = the partner that BROUGHT them; `linked_partner_id` on partner user = the partner record they CAN ACCESS — DO NOT mix these two fields
- Earnings hook still goes through `_finalize_paid_booking` → `record_partner_earning_for_booking`; idempotent on `(partner_id, booking_id)`
- Newsletter admin endpoints under `/admin/newsletter/...`, partner endpoints under `/admin/marketing-partners/...` and `/partner/me*`
- Emergent LLM Key model must be `gemini-2.5-pro` via LiteLLM
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs
