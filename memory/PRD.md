# AURA — Premium Event Ticketing Platform

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. Originally proposed in .NET stack; pivoted to React + FastAPI + MongoDB. Must handle concurrency (no double-booking), tiered tickets, interactive seat selection, 10-min seat hold, QR e-tickets, organizer + admin dashboards, payments, email confirmation.

## Architecture
- **Backend**: FastAPI (Python 3.11), MongoDB via Motor, JWT (PyJWT) + Emergent Google OAuth, Stripe via emergentintegrations, QR codes via `qrcode`, bcrypt for password hashing.
- **Frontend**: React 19 + React Router 7, Tailwind, shadcn/ui primitives, Recharts, Sonner toasts, lucide-react icons, Instrument Serif + General Sans fonts, hot-coral (#FF4F00) accent on dark theme.

## User Personas
- **Attendee**: browses events, picks seats/tiers, books with 10-min hold, pays via Stripe, gets QR e-ticket.
- **Organizer**: lists events, sets pricing + seatmap, tracks sales/revenue, sees attendee list.
- **Admin**: approves/rejects organizer events, features events, full moderation.

## Core Requirements (static)
- Event browsing, search/filter (keyword, category, city)
- Two booking modes: tiered tickets (Early Bird/General/VIP) and interactive seat map (rows×cols)
- 10-minute seat hold with atomic locking (prevent double-booking)
- Stripe Checkout (test mode key in env), webhook + polling, transaction tracking
- QR-code e-tickets in user profile
- Organizer dashboard (revenue chart, events table, attendee list)
- Admin moderation (approve/reject/feature events)
- JWT email/password auth + Emergent Google social login (both coexist)

## What's been implemented (2026-02-15)
- ✅ Auth: register, login, logout, me, Google OAuth callback (`/api/auth/*`)
- ✅ Events: list/search/filter/detail/create with seat & tier states (`/api/events/*`)
- ✅ Bookings: hold (atomic), get, list mine (`/api/bookings/*`, `/api/me/bookings`)
- ✅ Stripe: create session, poll status, webhook handler (`/api/checkout/*`, `/api/webhook/stripe`)
- ✅ Organizer: events, analytics with 14-day series, attendees (`/api/organizer/*`)
- ✅ Admin: list, approve, reject, feature (`/api/admin/*`)
- ✅ Frontend pages: Landing, Events listing, Event detail (tiers + seat map), Checkout (countdown), Success, Profile (QR modal), Organizer dashboard, Create Event, Admin moderation, Login, Signup, AuthCallback
- ✅ Seed: 3 users (admin, organizer, attendee) + 8 demo events across 8 categories
- ✅ 29/30 backend tests passing in iter1; Stripe status endpoint hardened against transient errors

## Iteration 2 (2026-02-15, same day) — Custom seat layouts + uploads
- ✅ **File uploads**: `POST /api/uploads` (multipart) returns `{url, filename}`; served via `/api/uploads/{name}` static mount. Organizer/admin only, 5MB cap, image extensions whitelist.
- ✅ **Cover photo upload from computer**: `ImageUploader` component in Create Event replaces URL field. Drag/click → preview → replace/clear.
- ✅ **Seat designer**: `SeatDesigner` component lets organizer mark cells as aisles (non-rectangular venues like cinemas). Output is an `aisles: ["A-6", "B-6", ...]` array stored on the event.
- ✅ **Venue floor-plan backdrop**: optional `seat_map_image_url` uploaded as a backdrop behind the seat grid (both in designer and attendee view) at low opacity.
- ✅ **Atomic seat reservations**: dedicated `seat_reservations` collection with **unique compound index `(event_id, seat_id)`**. Inserts on hold; `DuplicateKeyError` → 409 with rollback. Marked `booked` on payment success.
- ✅ Demo seatmap events seeded with realistic aisles (Stand-Up Saturday: 1 center aisle = 16 cells; Hamilton: 2 aisles = 20 cells).
- ✅ 42/42 backend tests passing (12 new in iter2: uploads, aisle reject, concurrent holds, etc.)

## Iteration 3 (2026-02-15) — Object storage + polish
- ✅ **Emergent object storage**: uploads now persisted to `https://integrations.emergentagent.com/objstore` under `aura-tickets/uploads/{user_id}/{uuid}.{ext}`. Survives container restart.
- ✅ `GET /api/files/{path:path}` — public read endpoint streams files from object storage with content-type + cache headers.
- ✅ DB-backed file metadata in `uploaded_files` (file_id, storage_path, content_type, size, user_id, etag).
- ✅ **shadcn Calendar + time picker** replaces native HTML datetime-local input on Create Event (`DateTimePicker.jsx`).
- ✅ Tightened allow-list: removed `.gif` (only jpg/jpeg/png/webp).
- ✅ 55/55 backend tests + 100% frontend E2E passing.

## Iteration 4 (2026-02-15) — Refactor + Drilldown + CSV + ETag
- ✅ **Refactor**: `server.py` (1188 lines → 86 lines) split into modular package:
  - `core.py` — shared db, env, helpers, auth deps
  - `models.py` — Pydantic in/out models
  - `seed.py` — demo data
  - `storage.py` — object storage client (unchanged)
  - `routers/{auth,events,bookings,payments,uploads,admin,organizer}.py` — endpoint groups (each <180 lines)
- ✅ **Per-event drilldown** `GET /api/organizer/events/{event_id}/analytics`: event meta + totals (revenue, tickets_sold, capacity, **sell_through_pct**, bookings_count, unique_attendees) + tier breakdown + day series + hour-of-day (24 entries) + bookings_count.
- ✅ **CSV export** `GET /api/organizer/events/{event_id}/attendees.csv` (text/csv with Content-Disposition).
- ✅ **Frontend drilldown page** `/organizer/events/:eventId` — 4 KPI cards, "Revenue by tier" bar chart, "Revenue by day" line chart, hour-of-day bars, tier breakdown table, attendees table, "Export attendees (CSV)" button (authenticated fetch + blob download).
- ✅ Organizer dashboard table rows are now clickable → drill into event analytics.
- ✅ **ETag on `/api/files/{path}`** — browsers send `If-None-Match`, server replies `304 Not Modified` with empty body. Partial mitigation for K8s ingress stripping our `Cache-Control` header. ETag backfilled on first miss.
- ✅ Polish: loading state on dashboard table, default cache headers on file responses.
- ✅ **74/75 backend pass, 100% frontend E2E** (1 stale iter3 test using a hard-coded storage path that no longer exists; not a regression).

## Iteration 5 (2026-02-15) — Index optimization + CDN guide + Discount Code Engine
- ✅ Added `bookings (event_id, status)` compound index + `bookings.user_id` index for analytics & profile queries.
- ✅ `/app/memory/CDN_DEPLOYMENT.md` — Cloudflare / BunnyCDN / CloudFront step-by-step deployment guides.
- ✅ **Discount code engine** (`routers/discount_codes.py`):
  - Organizer CRUD `POST/GET/DELETE /api/organizer/discount-codes` (with `?active=true` filter)
  - Public validate `POST /api/discount-codes/validate` — no consumption; computes discount
  - Apply at hold `POST /api/bookings/hold` accepts optional `code`, stores `discount_code` + `discount_amount` + `subtotal`
  - **Atomic uses_count enforcement** with `$expr` guard — concurrent overflows return 409 consistently
  - Code rules: `[A-Z0-9_-]{2,24}`, percent (≤100) or flat, optional `max_uses`, `expires_at`, `restricted_tiers`
- ✅ **Attribution analytics**: drilldown returns a `codes` bucket (Direct + each code with revenue/tickets/discount_given). Rendered as horizontal bar chart + attribution table on the drilldown page.
- ✅ Frontend `/organizer/codes` (`DiscountCodes.jsx`) + EventDetail promo input with Apply + applied badge + strikethrough subtotal.
- ✅ Login redirect by role (organizer → /organizer, admin → /admin, attendee → /).
- ✅ **94/95 backend pass + 100% frontend E2E** (20 new iter5 cases). Status-code 409 consistency + max_length=24 added post-test.

## Prioritized Backlog (deferred)
- **P0**: Real email confirmations (SendGrid/Resend — needs API key from user)
- **P1**: Refresh tokens / token expiry handling (current JWT is 7-day)
- **P2**: Waitlists for sold-out events with auto-notify
- **P2**: AI event recommendations ("Because you liked X…")
- **P2**: On-site QR check-in app for organizers (scan QR with phone camera at the door)
- **P2**: Dynamic pricing (auto-bump as stock depletes / date approaches)
- **P2**: Live seat updates via WebSockets (currently 8-sec polling)
- **P2**: NFC/RFID festival entry, virtual event Zoom integration
- **P2**: CDN for `/api/files/*` (guide ready in `CDN_DEPLOYMENT.md`)
- **P3**: Marketing referral tracking, organizer payout system, KYC verification

## Done (no longer in backlog)
- ~~Split server.py into routers~~ (iter4)
- ~~Atomic seat reservation via unique compound index~~ (iter2)
- ~~Discount codes / promo engine~~ (iter5)

## Mocked / Open Items
- Email confirmation sending: **MOCKED** (logged to console only)
- Stripe in test mode — full payment completion requires real browser interaction

## Iteration 6 (2026-02-15) — Movies category + Admin user management
- ✅ **Movies/Film category** added as the first category. Two cinema demo events seeded:
  - `Dune: Part Three — IMAX Premiere` (Hoyts Sylvia Park, 9×14 seatmap with 2 aisles)
  - `Studio Ghibli Retrospective — Spirited Away (35mm)` (Embassy Theatre, 7×12 with center aisle)
- ✅ **Admin user management** — new "Users" tab on `/admin` with stats (total/by-role/suspended), search by name/email, filters by role/status, role change (inline select), suspend/unsuspend with session invalidation. Backend endpoints:
  - `GET /api/admin/users` (with `?q=`, `?role=`, `?active=` filters)
  - `GET /api/admin/users/stats`
  - `POST /api/admin/users/{id}/role`, `/suspend`, `/unsuspend`
- ✅ **Security guards**:
  - Suspended users blocked from login (`403 Account suspended`)
  - Active-flag check enforced in `get_current_user` for both JWT and Google-session paths (stale tokens rejected post-suspension)
  - Cannot demote yourself
  - Cannot demote the last remaining admin (count-based guard)
- ✅ Per-user activity counts (bookings_count, events_count) in the listing.
- ✅ **22/22 new iter7 tests pass + 100% frontend E2E**. One pre-existing critical bug (JWT branch didn't check `active`) caught by tester and fixed during the run.

## Iteration 7 (2026-02-15) — Movies category + Admin user management
(captured above as iter6 block)

## Iteration 8 (2026-02-15) — On-site QR check-in for organizers
- ✅ **Door scanner page** `/organizer/events/:id/checkin` (`CheckIn.jsx`) using `html5-qrcode`:
  live camera scanning with 1.5s throttle, manual booking-ID fallback, last-result card with Undo, Recent check-ins panel (auto-polled every 5s), stat cards (Bookings / Checked-in / No-shows / Attendance %).
- ✅ **Backend APIs** (`routers/organizer.py`):
  - `POST /api/organizer/checkin` — idempotent QR / booking-id scan; rejects wrong-event tickets, unpaid bookings, foreign organizers.
  - `GET /api/organizer/events/{id}/checkin-stats` — totals + 20 most recent.
  - `POST /api/organizer/events/{id}/checkin/{bid}/undo` — reverse a mistaken scan.
  - `GET /api/organizer/events/{id}/attendance-report.csv` — full attendance CSV (ATTENDED / NO-SHOW sort).
- ✅ Idempotent contract: single `utc_now().isoformat()` per request — DB and response timestamps match.
- ✅ "Check-in" button added to organizer event drill-down (`OrganizerEvent.jsx`).
- ✅ **16/16 pytest pass** in `tests/test_iteration8.py`. Frontend e2e all 7 flows pass (testing-agent iter8).

## Iteration 9 (2026-02-15) — Transactional Emails (Resend)
- ✅ **Resend SDK** integrated (`emails.py`): single `send_template(name, to, ctx, db)` entry point, non-blocking (`asyncio.to_thread`), all sends logged to `email_logs` collection with status sent/failed/skipped.
- ✅ **6 templates** with dark-theme + hot-coral inline HTML + plaintext fallback: `booking_confirmation`, `hold_expired`, `refund_issued`, `organizer_event_approved`, `organizer_payout_issued`, `waitlist_spot_opened`.
- ✅ **Wired**: payment-success path (status poll + Stripe webhook) → `booking_confirmation`; admin event approval → `organizer_event_approved`.
- ✅ **Admin Emails tab** (`/admin` → Emails): stats (sent/failed/skipped), recipient search, template/status filters, audit table.
- ✅ `GET /api/admin/email-logs` (admin-only) with filters & summary stats.
- ✅ **15/15 pytest pass** (`tests/test_iteration9_emails.py`).
- ⚠️ **Resend test-mode**: sender is `onboarding@resend.dev`; emails only deliver to the account-verified email until a domain is verified at resend.com/domains.

## Iteration 10 (2026-02-15) — Commission & Payouts
- ✅ **Schema**: `platform_settings` singleton (commission %, flat per-ticket fee), `payouts` collection (`payout_id`, organizer_id, gross, commission, flat_fees, net_amount, bookings_count, tickets_count, booking_ids[], period_start/end, status), and `bookings.payout_id` lock field.
- ✅ **Commission engine** (`routers/payouts.py`): % + fixed-per-ticket model, snapshotted on each payout request so future settings changes don't retroactively alter pending payouts.
- ✅ **Organizer endpoints**: `GET /api/organizer/payouts/balance` (available net, lifetime paid, pending), `POST /api/organizer/payouts/request` (locks eligible bookings, atomic), `GET /api/organizer/payouts` (history).
- ✅ **Admin endpoints**: `GET/PUT /api/admin/platform-settings`, `GET /api/admin/payouts` (totals + status filter), `POST /api/admin/payouts/{id}/mark-paid` (triggers `organizer_payout_issued` email), `POST /api/admin/payouts/{id}/reject` (rolls bookings back into balance).
- ✅ **Frontend**: organizer `/organizer/payouts` (balance card with breakdown, request panel, history table), admin `/admin` → **Payouts** tab (status filters, mark-paid/reject actions, totals) + **Settings** tab (commission config with live preview).
- ✅ Stripe-Connect-ready schema: payout amounts already snapshotted, organizer_id + currency already tracked, can swap manual mark-paid for Connect webhook later.
- ✅ **13/13 pytest pass** (`tests/test_iteration10_payouts.py`).

## Test Credentials
See `/app/memory/test_credentials.md`
