# Allsale Events — Premium Event Ticketing Platform

> **Brand**: Rebranded from "AURA Tickets" → **Allsale Events** on 2026-02-16 (display name, email branding, sender name, credential domain `@allsale.events`). Internal protocol identifiers (`AURA|` QR prefix, `aura_token` localStorage key, `aura-tickets/` object-storage path) intentionally preserved to keep existing tickets/uploads valid.

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

## Iteration 11 (2026-02-15) — Waitlist for sold-out events
- ✅ **Sold-out detection** baked into `GET /api/events/{id}` — returns `sold_out: bool` + per-tier `tier_status: [{name, sold, remaining}]` for tier-based events.
- ✅ **Schema**: `waitlist_entries` collection with partial unique index `(event_id, user_id, status="waiting")` preventing duplicate joins.
- ✅ **User endpoints** (`routers/waitlist.py`):
  - `POST /api/events/{id}/waitlist/join` — gated on sold-out + non-seatmap
  - `GET /api/events/{id}/waitlist/me` — returns active entries with computed `position` (FIFO)
  - `DELETE /api/events/{id}/waitlist/me` — cancel
  - `GET /api/me/waitlist` — all my active entries across events
- ✅ **Organizer endpoints**:
  - `GET /api/organizer/events/{id}/waitlist` — list + counts + sold_out flag
  - `POST /api/organizer/events/{id}/waitlist/offer-next` — atomically creates a 15-min pending booking for head, marks entry `offered`, fires `waitlist_spot_opened` email
- ✅ **Auto-trigger**: when a hold expires during another user's `bookings/hold` call, the expired-pending sweep also fires `try_offer_next_in_waitlist(event_id)` — capacity flows to the waitlist automatically.
- ✅ **Frontend**:
  - EventDetail: "Sold out" button + waitlist bell ("Notify me when a spot opens"), shows queue position when waiting, shows green "Claim my spot" button (linking to `/checkout/{booking_id}`) when offered.
  - OrganizerEvent: new Waitlist panel with counts, "Offer next" button, full table of entries with status pills.
- ✅ **13/13 pytest pass** (`tests/test_iteration11_waitlist.py`) — sold-out detection, join/leave/duplicate-guard/seatmap-reject/position, offer-next FIFO + email log + status transition.
- ✅ Added module-scoped cleanup fixtures to iter10 + iter11 tests so test artifacts don't contaminate other suites.
- ✅ **All 57/57 tests pass** across iter8 (check-in) + iter9 (emails) + iter10 (payouts) + iter11 (waitlist).

## Iteration 12 (2026-02-15) — AI Recommendations + Dynamic Pricing + Waitlist Count Badge
- ✅ **AI Recommendations** (`routers/recommendations.py`):
  - `GET /api/me/recommendations` returns 3–5 personalized event picks with a one-line "why" per pick.
  - Uses Emergent LLM key with GPT-5.1 (Claude/Gemini swappable). Strict-JSON output parsing with code-fence stripping.
  - Trending fallback for users with no booking history. Heuristic category-overlap fallback if LLM call fails.
  - **1-hour per-user cache** via `recommendation_cache` collection (unique index on `user_id`).
  - Landing page now has a "Picked for you" carousel above the featured grid (visible to logged-in users only).
- ✅ **Dynamic Pricing**:
  - `compute_tier_effective_price(event, tier, sold)` core helper — surges when remaining ≤ threshold%; multiplier clamped to [1.0, 3.0].
  - Per-event config: `{enabled, surge_threshold_pct, surge_multiplier}` (default 30% / 1.2×).
  - `PATCH /api/organizer/events/{id}/dynamic-pricing` to toggle/configure (organizer or admin only).
  - `GET /api/events/{id}` now returns `surging` flag + per-tier `effective_price` and `surging` booleans.
  - `POST /api/bookings/hold` uses the effective price at hold-time (snapshotted in the booking).
  - EventDetail UI shows "HIGH DEMAND" pill + strikethrough base price + surged display price.
  - OrganizerEvent has a "Demand pricing" panel with toggle + dual sliders (threshold, multiplier) + live preview.
- ✅ **Waitlist count badge**:
  - `GET /api/events` now annotates each tier-based event with `waitlist_count` when ≥ 1 person waiting.
  - EventCard shows "X waiting" pill in the top-left corner (FOMO/social-proof signal on Browse).
- ✅ **11/11 pytest pass** (`tests/test_iteration12_dynamic_recs.py`).
- ✅ **68/68 tests pass** in full regression across iter8–iter12.

## Iteration 13 (2026-02-15) — Seatmap Waitlist
- ✅ **Sold-out detection for seatmap events**: `GET /api/events/{id}` now returns `sold_out: true` when every non-aisle seat is locked (booked or held with non-expired hold). Aisles correctly excluded from capacity calc.
- ✅ **Join waitlist** on seatmap events now succeeds (previously rejected with 400). Users specify `quantity`; seat preference deferred until offer time.
- ✅ **Offer-next claims seats atomically**: `_create_waitlist_offer` for seatmap events picks the first N available seats and inserts each into `seat_reservations` with `status=held` + `source=waitlist`. Compound unique index on `(event_id, seat_id)` ensures atomic claim even under race conditions.
- ✅ **Partial fulfillment**: if user asked for 3 but only 1 free, offer 1 seat (better than nothing).
- ✅ **Expired offers free seats**: when a 15-min waitlist hold expires, its seat reservations are deleted, returning capacity to inventory + triggering the next person in the queue.
- ✅ **Auto-trigger extended**: `/bookings/hold` flow also sweeps expired seat reservations and calls `try_offer_next_in_waitlist` for both event types.
- ✅ **Frontend**: EventDetail now shows waitlist UI on sold-out seatmap events (previously hidden). Offer-ready panel lists the specific offered seats as chips before the "Claim my spot" button.
- ✅ **8/8 pytest pass** (`tests/test_iteration13_seatmap_waitlist.py`).
- ✅ **76/76 total tests pass** across iter8–iter13.

## Iteration 14 (2026-02-15) — Theatre-style Seat Layout + Backdrop Alignment Fix
- ✅ **Curved rows** (`seatmap_curved`): rows fan in a parabolic arc (front rows minimal, back rows pronounced).
- ✅ **Labeled section dividers** (`seatmap_sections: [{after_row, label}]`): orange-pill dividers between rows (Mezzanine, Balcony, Loge, etc.).
- ✅ **Backdrop alignment — 4 sliders** (per user feedback after seeing initial v1):
  - `seatmap_backdrop_opacity` (default 0.4)
  - `seatmap_backdrop_scale` (0.4×–2.5×)
  - `seatmap_backdrop_offset_x` (−200 to +200 px)
  - `seatmap_backdrop_offset_y` (−200 to +200 px)
  - These let organizers tune the uploaded venue floor-plan to align with the seat grid exactly.
- ✅ **Adaptive seat sizing**: grid auto-shrinks seat tiles (26→22→18→14 px) when col count grows (10/14/18/26), so wide cinemas (11+ cols) fit on screen without horizontal scroll.
- ✅ **Mode toggle** (Aisle / Section) on the designer header.
- ✅ Backdrop image uses `object-fit: contain` (was `cover`) so it doesn't crop and lines up with seats predictably.
- ✅ Backwards compatible: legacy events without new fields fall back to safe defaults.
- ✅ **3/3 pytest pass** (`tests/test_iteration14_theatre_layout.py`), **79/79 total** across iter8–iter14.
- 📸 Visual: cinema-style 11-col × 6-row event with uploaded floor-plan now renders correctly — image visible behind seat grid, organizers tune scale/offset to align seats with image.

## Iteration 15 (2026-02-15) — Attendee → Organizer self-serve upgrade flow
- ✅ **Security gap closed**: previously, any signed-in attendee could navigate to `/organizer/new` and only got blocked on submit. Now all `/organizer/*` routes are gated by a `RequireOrganizer` route guard:
  - Not signed in → redirected to `/login?redirect=...`
  - Signed in but role !== organizer/admin → redirected to `/become-organizer?redirect=...`
- ✅ **`/become-organizer` upgrade page** (`BecomeOrganizer.jsx`) — friendly Eventbrite-style onboarding screen: 4 perk cards, commission disclosure (8% + $0.50/ticket), ToS checkbox, one-click "Become an organizer" CTA.
- ✅ **`POST /api/auth/become-organizer`** — idempotent role-flip endpoint:
  - Attendees → role updates to "organizer" + `upgraded_at` timestamp, returns `upgraded=True`
  - Organizers → no-op, returns `upgraded=False`
  - Admins → role unchanged (never downgrade), returns `upgraded=False`
- ✅ **Navbar**: attendees see a new "Host an event" link (with Sparkles icon). Footer "Sell Tickets" link goes to `/become-organizer` for attendees, `/organizer` for organizers, `/signup` for anon users.
- ✅ **6/6 pytest pass** (`tests/test_iteration15_become_organizer.py`): auth required, attendee-flip, organizer idempotent, admin protected, before/after upgrade event-creation gates.
- ✅ **85/85 total tests pass** across iter8–iter15.

## Iteration 16 (2026-02-15) — Live WebSocket seat updates + seat-section pricing
- ✅ **Phase B complete — WebSocket seat updates** (`routers/ws_seats.py`):
  - Single-process `EventHub` pub/sub keyed by `event_id`.
  - WS endpoint `wss://<host>/api/ws/events/{event_id}` accepts connections, sends initial snapshot, broadcasts deltas (`seat`/`tier`/`snapshot` message types).
  - Server-side 25s heartbeat ping keeps proxy connections alive.
  - Broadcasts wired into `routers/bookings.py` (on hold creation) and `routers/payments.py` (on payment success). Held → Booked deltas emit per-seat events for seatmap events; tier-count refreshes for tier-based events.
- ✅ **Frontend `useEventLiveUpdates` hook** (`lib/useEventLiveUpdates.js`):
  - WebSocket with exponential-backoff reconnect (1s → 30s cap, resets on connect).
  - Applies `onSnapshot` / `onSeat` / `onTier` deltas to local state without network round-trips.
  - Replaces the old 8-second polling on EventDetail (kept a 60s safety-net refresh for missed deltas).
  - Live indicator dot on the EventDetail booking sidebar when connected.
- ✅ **Seat-section pricing**:
  - `core.seat_section_for_row(event, row_idx)` + `seat_price_for(event, seat_id)` helpers.
  - Sections in `seatmap_sections[]` now accept an optional `price` field. Front zone falls back to base `seat_price`.
  - `POST /api/bookings/hold` uses per-seat pricing — different zones can charge different amounts.
  - Frontend `EventDetail` mirrors the logic for the subtotal preview before submit.
- ✅ **7/7 pytest pass** (`tests/test_iteration16_websocket_pricing.py`): section-row mapping, price fallback, invalid seat IDs, WS snapshot delivery, unknown-event WS resilience.
- ✅ **92/92 total tests pass** across iter8–iter16.

### Not shipped this iteration (intentional)
- 🟢 **CreateEvent UI** for entering per-section prices — backend persists/reads them fine, organizers can set via API or future UI tweak.

## Iteration 17 (2026-02-16) — Event-views tracking + Demand sparkline + Sales velocity
- ✅ **`/api/events/{id}/view`** anonymous-friendly view ping; stored in `event_views` collection with timestamp + fingerprint (user_id or client IP). 60-second sessionStorage debounce on the EventDetail page.
- ✅ **`/api/events/{id}/demand`** returns 7-day buckets (views + paid bookings, oldest → newest). Rendered as an inline SVG sparkline (`<DemandSparkline />` component) under the booking sidebar on EventDetail — bars = views, dots = bookings, totals labeled.
- ✅ **`/api/organizer/events/{id}/velocity`** organizer-only: capacity, sold, remaining, sold_24h, sold_7d, per_hour_24h, per_day_7d, forecast_days, forecast_label ("Sellout today", "Expected sellout in 4d", "No sales yet", "Sold out", "Slow demand"). Organizers see urgency-colored forecast on `/organizer/events/:id`.
- ✅ Handles seatmap and tier-based events. Forbid other organizers (403) and anon (401).
- ✅ **9/9 pytest pass** (`tests/test_iteration17_demand_velocity.py`).

## Iteration 19 (2026-02-16) — Brand artwork + Light theme palette swap
- ✅ **Official logo wired**: user-uploaded "AllSale EVENT" artwork stored at `/app/frontend/public/allsale-logo.png`. `Logo.jsx` now renders the PNG via `<img>` (lockup variant in header/footer/auth cards, mark variant available for square avatars).
- ✅ **Theme repalette** (`index.css`): switched from dark + hot-coral (#FF4F00) → **light** + teal/orange. New CSS variables:
  - `--bg: #FBFCFE` · `--bg-card: #FFFFFF` · `--border: #E2E8EF` · `--text: #0F2A3A` (deep teal-navy)
  - `--accent: #F08A2A` (logo orange — primary CTA) · `--primary: #1B7A9E` (logo teal — secondary brand)
  - Soft radial-gradient body backdrop using both brand colors at 10% opacity.
- ✅ **Component updates**: `.glass` is now translucent white blur, `.card-event` has subtle shadow + orange hover-border, `.chip-primary` introduced for teal pills, seat colors swapped to light theme (`#DDE3EA` booked, `#FCE3CB` held).
- ✅ **Hard-coded color literals updated**: Recharts (`OrganizerEvent.jsx`, `Organizer.jsx`) — bar/line colors `#ff4f00 → #F08A2A`, axis stroke `#71717a → #8092A3`, tooltip background dark → white card. `EventCard.jsx` FROM-price chip now orange-on-white. `SeatDesigner.jsx` toggle text now white-on-orange.
- ✅ **Favicon** swapped to a teal disc + orange swoosh mark matching the logo palette.
- ✅ Removed dark-only Tailwind classes (`hover:text-white`, `text-white` on links) — now uses `hover:opacity-80` + font-weight indicator.
- ✅ All 31/31 backend tests still pass (no logic changes to API). Smoke-tested landing, events list, event detail, and login pages — all render cleanly in the new palette.

## Iteration 18 (2026-02-16) — Allsale Events rebrand
- ✅ **Display name** "AURA" → "Allsale Events" across UI: Layout header/footer, Login, Signup, BecomeOrganizer, toast copy.
- ✅ **Email branding** updated in `emails.py`: SENDER_NAME, layout header ("Allsale · Events"), footer ("© 2026 Allsale Events"), all template body strings ("event is live on Allsale Events", etc.).
- ✅ **Backend FastAPI title + logger banner** rebranded.
- ✅ **AI recommendations prompt** updated to "Allsale Events' recommendation engine".
- ✅ **Credential domain migration**: legacy `admin@aura.events`, `organizer@aura.events`, `attendee@aura.events` are auto-renamed to `@allsale.events` on backend startup (idempotent). Organizer display "AURA Productions" → "Allsale Productions" and admin display "AURA Admin" → "Allsale Events Admin" backfilled. Legacy `events.organizer_name` backfilled.
- ✅ **Internal identifiers preserved** (no breakage): QR payload prefix `AURA|<bid>`, frontend `localStorage.aura_token`, object-storage path `aura-tickets/uploads/...`, `sessionStorage` view-debounce key `aura:view:`.
- ✅ **7/7 rebrand regression pytest pass** + **15/15 email template pytest pass** + **9/9 demand/velocity pytest pass** (31/31 critical tests green).

### Not shipped this iteration (intentional)
- 🟢 **Demand sparkline + Sales velocity widget** — deferred; both depend on a small `event_views` aggregation we haven't seeded yet.

## Test Credentials
See `/app/memory/test_credentials.md`

## Iteration 20 (2026-06-04) — Upload hardening + Error visibility
- ✅ **Profile picture / image upload bug fix**: backend `/api/uploads` now sniffs magic bytes when the filename extension is missing (mobile share-sheets often strip extensions) and transcodes **iPhone HEIC/HEIF photos → JPEG** on the server. Added `pillow-heif` to requirements.
- ✅ **Clearer upload errors**: backend returns string-only `detail` messages ("Unsupported image format. Please upload a JPG, PNG, WEBP or HEIC file.", "File too large — please pick an image under 5 MB."). Frontend `ProfileEditPanel.onPicture` now surfaces the real HTTP status (413/401/Network) when the server can't respond, and resets the file input so retry works.
- ✅ **Frontend accept widened**: `<input accept="image/jpeg,image/png,image/webp,image/heic,image/heif">` in ProfileEditPanel and ImageUploader.
- ✅ **ErrorBoundary upgraded**: crash page now shows the current route, the error message, the component stack, AND a "Copy crash report" button that puts a full diagnostic blob on the clipboard so users (or support) can paste it back to us.
- ✅ **Defensive guards** in places where the user reported a `Cannot read properties of undefined (reading 'length')` crash: `OrganizerEvent.jsx` destructures `tiers/days/hours/codes` with array defaults; `WaitlistPanel` falls back to `[]`/`{waiting:0,...}` when API omits fields; `EventDetail.jsx` WS handlers (`onSnapshot`/`onTier`) skip the tiers re-map when `prev.tiers` is missing (seatmap-only events).
- ✅ Verified via curl: normal JPG ✓, extension-less JPG (magic sniff) ✓, HEIC → JPEG transcode ✓, plain-text rejected with friendly message ✓.



## Iteration 21 (2026-06-04) — Demo data wipe + real live counter
- ✅ **New admin endpoint** `POST /api/admin/wipe-demo-data` (admin-only) — removes the 10 seed events (Dune, Hamilton, AllBlacks, etc.) by exact title match plus the demo `organizer@allsale.events` / `attendee@allsale.events` users. Cascades cleanly through bookings, holds, reservations, scanner tokens, team grants, discount codes, waitlist entries and event views. Real organizer events and real signed-up users are untouched.
- ✅ **Admin UI panel** added to the Settings tab: "Demo data cleanup" card with red destructive button + cascade report showing exactly how many records were removed (`data-testid="wipe-demo-btn"`).
- ✅ **Public stats endpoint** `GET /api/events/stats/public` → `{live_events: <count>}` — counts approved + future events only.
- ✅ **Landing hero chip** swapped from hard-coded `"Live · 124 events on sale"` → real `liveCount` from the public stats endpoint. Falls back to `"Be the first to host"` when the platform is empty (`data-testid="live-event-count"`).
- ✅ **Seed defaults flipped**: `SEED_DEMO` now defaults to **false** so future deployments never re-create demo events or demo users. Admin user is still always created on a fresh DB.
- ✅ Smoke-tested end-to-end via curl (local dev DB: 2 demo users removed, real events unaffected) + screenshot (chip now shows "Live · 5 events on sale" instead of the fake 124).




## Iteration 22 (2026-06-04) — Editor's Pick (curated landing hero)
- ✅ **Site settings extended** with an `editor_pick: {event_id, blurb, badge_text}` field. Backwards-compatible — defaults to no pick, falls back to first featured event.
- ✅ **New public endpoint** `GET /api/site-settings/editor-pick` — joins the picked event into a public payload + returns the curator blurb + badge text. Auto-falls-back to `{event: null}` when the pick references a deleted or un-approved event so the landing page never breaks.
- ✅ **Admin PATCH** `/api/admin/site-settings` now accepts `editor_pick.event_id` (string or `null` to clear), `blurb` (≤220 chars), and `badge_text` (defaults to "Editor's Pick").
- ✅ **Landing page hero** auto-pulls the pick. Renders the curator blurb in italics under the title, swaps the chip text to the configured badge (e.g. "Editor's Pick" / "Don't Miss" / "Trending now"), and uses the brand accent border for extra prominence. Falls back to the existing "first featured event" behaviour when no pick is set.
- ✅ **Admin UI panel** added to Settings tab — dropdown of approved events, 220-char blurb textarea with counter, badge override input, live preview card, "Clear" button, and a save flow that confirms via toast.
- ✅ Verified end-to-end via curl (5 backend tests) + screenshot (the chip, blurb, and orange-bordered hero all render correctly on https://seathold.preview.emergentagent.com/).



## Iteration 23 (2026-06-04) — Live launch on www.allsale.events
- ✅ **Custom domain LIVE**: `https://www.allsale.events` serving production via Vercel + Railway. DNS upgraded to project-specific Vercel records (`4db50d8aa4cfd9b4.vercel-dns-017.com` CNAME + `76.76.21.93` A) — no more "DNS Change Recommended" warning.
- ✅ **CORS hardened**: hardcoded allowlist for `*.allsale.events`, `*.allsale.co.nz`, and any `*.vercel.app` preview via regex, so a half-configured `CORS_ORIGINS` env var can't lock real users out again.
- ✅ **Admin password reset endpoint** `POST /api/auth/admin-reset` — gated by `ADMIN_RESET_TOKEN` env var (idempotent, returns clear `{ok, reason}` diagnostics). Used to recover the prod admin login.
- ✅ **Stripe Test → Live**: `STRIPE_API_KEY` swapped to `sk_live_...` on Railway. Verified via `GET /api/payments/health` returning `mode: "live"`.
- ✅ **Payments health probe** `GET /api/payments/health` (admin-only) — sanity-check endpoint that reports test/live/restricted mode from the key prefix. Never echoes the key itself.
- ⏳ Pending: $1 end-to-end test charge to verify real payment flow + email confirmation + QR ticket render.

## Iteration 24 (2026-06-05) — Contact organizer + Swap seats
- ✅ **Public organizer profile** at `/organizers/:id` — picture, name, bio, "X events hosted", joined date, list of upcoming approved events, "Contact organizer" CTA. Backed by new public endpoint `GET /api/organizers/:id`.
- ✅ **Contact organizer dialog** (`<ContactOrganizerButton>` / `<ContactOrganizerDialog>`) — drop-in component used on:
  - Event detail page (next to the organizer name)
  - Organizer public profile page
  Pre-fills sender's name/email when signed-in, accepts an optional `event_id` for context-rich messages.
- ✅ **Organizer inbox** in dashboard top (`<OrganizerInboxPanel>`) — shows unread badge, expandable message thread, "Reply" mailto button, mark read/unread, delete. Persists to new `organizer_messages` Mongo collection.
- ✅ **Email notification** to organizer on every new message — new `organizer_contact_message` template renders the sender details + message preview + a one-click reply CTA. Reply-To header lands customer's reply directly in the organizer's Gmail.
- ✅ **Swap seats endpoint** `POST /api/organizer/bookings/:id/swap-seats` — admin/organizer moves a paid booking's seats within the same event. Validates: paid status, no check-in yet, same seat count, same tier (pricing parity), all new seats free, no duplicates. Atomically frees old reservations, writes new ones, updates booking, broadcasts seat-status delta over WS, and emails the customer a fresh confirmation noting the swap reason.
- ✅ **Swap seats dialog** (`<SwapSeatsDialog>`) — live validation feedback (wrong count, duplicates, taken, wrong tier, unknown seat IDs), reason field, surfaced in `OrganizerEvent` attendees table next to "Transfer".
- ✅ Verified via smoke test: 404s for unknown organizer, dev compile clean, organizer-profile page renders, swap/contact dialogs lint clean.


## Iteration 25 (2026-06-09) — Auto-archive past events
- ✅ **Past-event auto-archival**: events whose start `date` is older than `EVENT_FINISHED_GRACE_HOURS` (default **24h**, env-overridable) are now hidden from `/api/events`, `/api/events/featured`, and AI recommendations. The grace window covers multi-day festivals; the env var lets the owner tune it without a code change.
- ✅ **`/api/events?past=true|false`** — public listing accepts a `past` query param; `true` returns finished events sorted newest-first and annotates each with `is_past: true`. Default is `false` (upcoming only).
- ✅ **`/api/events/{id}`** now carries `is_past: bool` so direct links + old QR/ticket URLs still resolve, but the booking sidebar shuts off.
- ✅ **Events page UI**: new **Upcoming / Past** segmented tabs (`data-testid="events-tab-upcoming"`/`-past`), heading auto-switches to "Past events", past empty-state copy, past cards rendered with grayscale + a "Past event" chip badge.
- ✅ **Event detail**: shows "PAST EVENT" badge over the banner, **Book Now → "Event ended"** (disabled), helper note "This event has finished. Browse upcoming events instead.", waitlist CTA hidden.
- ✅ **Footer**: new "Past Events" link under the Discover column (`/events?past=1`).
- ✅ Regression suite at `/app/backend/tests/test_past_events.py` — 5 tests covering helper logic, default hide, `past=true` reveal, featured exclusion, and detail `is_past` flag. All passing.




## Iteration 26 (2026-06-10) — Stripe Connect Express (Batch 1)

**Charge model chosen**: Marketplace — separate-charges-and-transfers / hold-until-event. Platform holds all ticket revenue in Allsale's Stripe balance; transfers organizer share (minus 5% platform fee + Stripe processing) ~24h after event end. This gives full control for refunds, chargebacks, and cancelled events.

**Batch 1 — Organizer onboarding (DONE):**
- ✅ New router `/app/backend/routers/stripe_connect.py` with:
  - `POST /api/stripe/connect/onboard` — lazily creates a Stripe **Express** account for the organizer, requests `card_payments` + `transfers` capabilities, mints a fresh AccountLink and returns the hosted-onboarding URL.
  - `GET /api/stripe/connect/status` — returns `{stripe_account_id, stripe_charges_enabled, stripe_payouts_enabled, stripe_details_submitted, stripe_requirements_due, stripe_last_synced_at}`. Auto re-syncs from Stripe if stale (>60s).
  - `POST /api/stripe/connect/dashboard-link` — generates one-time Express dashboard login URL for the organizer.
  - `POST /api/webhook/stripe/connect` — listens for `account.updated`, mirrors capability flags onto the user row. Other Connect events (transfer.*, payout.*) logged for Batch 2.
- ✅ `/auth/me` extended with the four Stripe fields.
- ✅ New React component `/app/frontend/src/components/StripeConnectPanel.jsx` (3-state: Not connected / In progress + missing requirements / Verified). Mounted at the top of `/organizer`.
- ✅ Smoke-tested on preview: panel renders, copy + CTA correct, all four backend endpoints respond.
- ✅ Regression suite `/app/backend/tests/test_stripe_connect.py` — 5 tests covering status-empty, dashboard-link-without-account, role-gating, `/me` field exposure, webhook dev-mode acceptance. All passing.

**Env vars (production):**
- `STRIPE_API_KEY` — already set (live key).
- `STRIPE_CONNECT_WEBHOOK_SECRET` — must be added on Railway after creating the Connect webhook in Stripe dashboard (see action items).
- `PLATFORM_FEE_BPS=500` — 5% (default if unset).

**Batch 2 — Scheduled payouts (DONE):**
- ✅ New module `/app/backend/connect_payouts_engine.py` — finds events ≥`PAYOUT_HOLD_HOURS` (default **120h = 5 days**) past their start, organizer has verified Connect, sums paid bookings (excluding refunded), subtracts platform fee (`PLATFORM_FEE_BPS=500` = 5%), creates `stripe.Transfer` with idempotency key `event-payout-{event_id}`, stamps event with payout_status/transfer_id/amount, writes audit row in new `connect_payouts` collection.
- ✅ Hourly scheduler tick now runs `run_due_event_payouts(db)` alongside reminders + digest.
- ✅ New routes:
  - `GET /api/organizer/event-payouts` — organizer-facing list with `hold_remaining_hours` countdown.
  - `POST /api/admin/stripe/payouts/{event_id}/run` — admin force-trigger.
  - `GET /api/admin/stripe/payouts` — admin audit listing.
- ✅ Organizer emailed via existing `organizer_payout_issued` template (routes through `notification_email` if set).
- ✅ New React component `OrganizerPayoutsPanel` — countdown badges ("Payout in 4 days"), Paid/Failed/Processing-soon/No-sales states. Mounted at bottom of `/organizer`.
- ✅ Regression suite `/app/backend/tests/test_connect_payouts.py` — 4 tests covering 3 skip branches + hold-hours constant. All passing.

**Future:**

## Iteration 27 (2026-06-10) — Buyer-pays-fees pricing model

**Change:** the organizer now keeps the full ticket face value; the buyer pays Stripe + platform fees on top in a single combined "Service fee" line.

- ✅ New module `/app/backend/fees.py` with `compute_fees(face_value, currency)` — gross-ups the buyer total so that after Stripe's 2.7% + $0.30 deduction the platform retains exactly `face_value + platform_fee`. Default rates: 5% platform + 2.7% + $0.30 Stripe NZ. All knobs are env vars: `PLATFORM_FEE_BPS`, `STRIPE_FEE_BPS`, `STRIPE_FEE_FLAT`. Free tickets (face_value=0) skip all fees.
- ✅ Booking schema extended: `face_value`, `platform_fee`, `stripe_fee_estimated`, `service_fee`, `amount` (now the grossed-up buyer total). Subtotal/discount math unchanged.
- ✅ Connect payout engine updated — now uses `face_value` as the organizer's transfer amount (not `amount - platform_fee`). Legacy bookings (missing `face_value`) fall back to treating `amount` as face value so old events still pay out correctly during the migration window.
- ✅ Checkout UI shows three lines: **Tickets** (face value) + **Service fee** (combined) + **Payable now** (total). No platform-vs-Stripe split exposed to the buyer.
- ✅ Math verified end-to-end: $25 ticket → $2.29 service fee → buyer charged $27.29 → organizer paid $25.00. After Stripe's real-world cut, platform retains face_value + 5% exactly.
- ✅ Regression suite `/app/backend/tests/test_fees.py` — 4 tests covering pure math, free tickets, dict serialisation, and end-to-end booking creation. All passing.


- Multi-org-per-event splits (e.g., promoter + venue revenue share).
- Display platform fee preview at checkout (transparency).

## Iteration 28 (2026-06-10) — Admin "new event submitted" alerts

- ✅ Backend: when an organizer creates an event with status=pending, emails are fired to every `admin`-role user using the new `admin_new_event_submitted` template (full event card + organizer + venue + date + one-click "Open admin queue" CTA). Re-routes through `notification_email` like every other automated send.
- ✅ Backend: new `GET /api/admin/pending-events-count` — cheap counter for the badge poll.
- ✅ Frontend: `Layout` polls the count every 60 s for admin users. Renders an orange numeric pill next to the **Admin** nav link when `> 0`, with a hover-title summarising the count.
- ✅ Smoke-verified: submitted a test event on preview, template fired and re-routed to `allsaletickets+admin@gmail.com`. Resend rejected only because preview is sandbox-only — on production the verified `noreply@allsale.events` sender delivers.


- Organizer balance/transfer history page using `stripe.Transfer.list(destination=acct_id)`.

