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
- ✅ 29/30 backend tests passing; Stripe status endpoint hardened against transient errors

## Prioritized Backlog (deferred)
- **P0**: Real email confirmations (SendGrid/Resend — needs API key from user)
- **P1**: Stronger atomic seat reservation (unique compound index per (event_id, seat))
- **P1**: Refresh tokens / token expiry handling (current JWT is 7-day)
- **P1**: Split server.py (~1070 lines) into routers (auth/events/bookings/payments/admin)
- **P2**: Discount codes / promo engine
- **P2**: Waitlists for sold-out events with auto-notify
- **P2**: AI event recommendations ("Because you liked X…")
- **P2**: On-site QR check-in app for organizers
- **P2**: Dynamic pricing (auto-bump as stock depletes / date approaches)
- **P2**: Live seat updates via WebSockets/SignalR (currently 8-sec polling)
- **P2**: NFC/RFID festival entry, virtual event Zoom integration
- **P3**: Marketing referral tracking, organizer payout system, KYC verification

## Mocked / Open Items
- Email confirmation sending: **MOCKED** (logged to console only)
- Stripe in test mode — full payment completion requires real browser interaction

## Test Credentials
See `/app/memory/test_credentials.md`
