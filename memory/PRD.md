# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. MVP covers event browsing, search/filter, atomic-hold ticket booking, custom seat layouts with aisles, QR-code e-tickets, and dashboards for attendees, organizers, and admins. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel (frontend) + Railway (backend).

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe, Resend, Google OAuth, GA4, **Emergent LLM Key** (Gemini 2.5 Pro)

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Admin → Organizer creation + Event creation on-behalf-of
- Real-time Admin↔Organizer WebSocket chat + typing indicators
- Eventfinda-style layout, backend image proxy, sidebar poster always visible
- Social flyer "Download all 3 as ZIP" + Poster-First flyer redesign + **AI text overlay**
- Blog + SEO — backend CRUD, public pages, JSON-LD, sitemap, admin CMS
- Newsletter signup — public form + admin Subscribers panel + CSV export
- Protection P&L widget on Admin → Protection claims
- **Subscriber Fan-out (NEW)**:
  - New email template `blog_new_post` in `emails.py` — branded layout with cover image, post title, excerpt, "Read the full story" CTA, and footer unsubscribe link.
  - New endpoint `POST /api/admin/blog/{slug}/notify-subscribers` — fetches `status=active` subscribers from `blog_subscribers`, sends `blog_new_post` template via Resend through existing `send_template()` infra. Records sent recipients on the post doc as `notified_subscribers` for **per-subscriber idempotency** (re-runs only email new signups). Returns `{sent, failed, skipped, total_active}`.
  - Frontend: Send icon (orange paper-plane) added to admin blog row for published posts. Confirmation dialog shows subscriber count, toast confirms send result with breakdown.

## Backlog
- P3: Promote Protection P&L widget to Admin dashboard hero
- P3: Make `poster_url` field more prominent in CreateEvent
- P3: Flyer template picker (Minimal / Neon / Bold)
- P3: Wire `/blog/unsubscribe` URL to actual one-click unsubscribe page

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads
- Emergent LLM Key model must be `"gemini-2.5-pro"` via LiteLLM proxy (`gemini-2.5-flash` fails)
- Newsletter admin endpoints live under `/admin/newsletter/...` (NOT `/admin/blog/...`) to avoid FastAPI path collision with `/admin/blog/{slug}`
- Blog notify-subscribers endpoint IS under `/admin/blog/{slug}/notify-subscribers` — the extra `/notify-subscribers` suffix makes it unambiguous
- Blog posts → `blog_posts`, subscribers → `blog_subscribers` (lowercased email PK)
- `notified_subscribers` array on each post enables idempotent fan-out
- Commission math reads from MongoDB `platform_settings`
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs (not bugs)
