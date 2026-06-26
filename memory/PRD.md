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
- All current P0/P1/P2/P3 items shipped.
- Possible future: surface aggregate unsub reasons on the admin newsletter tab UI; add gift cards self-service portal; partner application intake form; AI flyer generation progress UI; reseller panel (scope TBD with user).

## Critical Notes
- Partner login uses standard `/api/auth/login`; partner role is just `user.role="partner"` + `user.linked_partner_id`
- `marketing_partner_id` on organizer user = the partner that BROUGHT them; `linked_partner_id` on partner user = the partner record they CAN ACCESS — DO NOT mix these two fields
- Earnings hook still goes through `_finalize_paid_booking` → `record_partner_earning_for_booking`; idempotent on `(partner_id, booking_id)`
- Newsletter admin endpoints under `/admin/newsletter/...`, partner endpoints under `/admin/marketing-partners/...` and `/partner/me*`
- Emergent LLM Key model must be `gemini-2.5-pro` via LiteLLM
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs
