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
