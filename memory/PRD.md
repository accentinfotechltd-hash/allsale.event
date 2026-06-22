# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform with full partner-revenue ecosystem. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel + Railway.

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe, Resend, Google OAuth, GA4, Emergent LLM Key (Gemini 2.5 Pro)

## Partner / Revenue Programs (4 distinct)
1. **Affiliates** — per-event promo codes (`routers/affiliates.py`)
2. **Organizer referrals** — flat $50 credit when organizer brings new organizer (`routers/organizer_referrals.py`)
3. **Influencer hub** — promoters advertising events (`routers/influencers.py`)
4. **Marketing Lead Partners** — *NEW*: admin-controlled lead-generation partners earning a % of platform commission on every paid booking from attached organizers (`routers/marketing_partners.py`)

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Admin → Organizer creation + Event on-behalf-of, real-time Admin↔Organizer chat + typing indicators
- Eventfinda layout, image proxy, sidebar poster, ZIP flyer + Poster-First + AI text overlay
- Blog + SEO + newsletter signup + subscriber fan-out + unsubscribe page
- Protection P&L widget on Admin → Protection
- **Marketing Lead Partners (NEW)**:
  - `routers/marketing_partners.py` — full admin CRUD + organizer attach/detach + earnings ledger + mark-paid batches + organizer search helper
  - **Booking hook** in `payments.py::_finalize_paid_booking` calls `record_partner_earning_for_booking()` after marking a booking paid. Computes `earning = booking.platform_fee * partner.commission_pct%` and writes to `marketing_partner_earnings` (idempotent on `(partner_id, booking_id)`). Recurring forever on every paid booking — no time cap.
  - Admin → "Lead partners" tab with partners table (Partner, Commission, #Organizers, Lifetime, Unpaid chip) + side drawer with stat cards + attached-organizer list + earnings ledger + "Mark all unpaid as paid" batch button + organizer search-and-attach
  - Data: `marketing_partners` collection, `marketing_partner_earnings` ledger, `users.marketing_partner_id` field links organizers
  - Verified end-to-end with seeded booking: $13.50 platform fee × 20% = $2.70 earning row, status `unpaid`, attached organizer shown in drawer

## Backlog
- P3: Promote Protection P&L widget to Admin dashboard hero
- P3: Flyer template picker (Minimal / Neon / Bold)
- P3: Make `poster_url` field more prominent in CreateEvent
- P3: Per-partner monthly statement email via Resend
- P3: Partner self-serve portal (currently admin-only)

## Critical Notes
- Marketing partner earnings hook: `_finalize_paid_booking` → `record_partner_earning_for_booking()`. Don't bypass that path — webhook replays are safe because of `(partner_id, booking_id)` idempotency.
- Earnings use `booking.platform_fee` as the base — if commission math is ever overhauled, audit the partner hook too.
- `marketing_partner_id` lives on the user (organizer) doc, NOT on event — so events the organizer adds later still attribute correctly.
- Newsletter admin endpoints under `/admin/newsletter/...`, marketing partner endpoints under `/admin/marketing-partners/...`
- Emergent LLM Key model must be `gemini-2.5-pro` via LiteLLM
- `/api/img-proxy` required for `html-to-image` flyer exports
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs (not bugs)
