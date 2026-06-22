# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. MVP covers event browsing, search/filter, atomic-hold ticket booking, custom seat layouts with aisles, QR-code e-tickets, and dashboards for attendees, organizers, and admins. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel (frontend) + Railway (backend).

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets for live seat/chat updates
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe (Payments/Tax/Boost), Resend (Email), Google OAuth, GA4, OpenAI/Gemini via Emergent LLM Key

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Vercel serverless OG share image (`/api/og-event.js`)
- Google Search Console verification meta tag
- Admin → Organizer creation + Event creation on-behalf-of
- Real-time Admin↔Organizer WebSocket chat (`/api/ws/admin-organizer-chat`)
- Eventfinda-style layout: hero lightbox banner, YouTube promo embed, vertical poster sidebar
- Rich-text event descriptions
- Backend image proxy (`/api/img-proxy`) for CORS-safe canvas exports
- Dynamic commission from `platform_settings` MongoDB collection
- Fan-out booking/enquiry emails (organizer + admin)
- IP protection: `robots.txt`, `/terms`, copyright meta
- Sidebar event poster always visible — falls back through `poster_url → banner_url → image_url`
- Social flyer "Download all 3 as ZIP" (jszip) — packs square/story/wide PNGs
- Poster-First flyer redesign — full poster via `object-contain`, brand strip with QR
- Blog / SEO setup — backend CRUD, public pages, JSON-LD, sitemap, admin CMS tab
- **Protection P&L widget (NEW)** on Admin → Protection claims tab:
  - Backend endpoint `GET /api/admin/ticket-protection/stats` aggregates premiums, claims, opt-in rate, loss ratio
  - Widget shows Net pool, Loss ratio (color-coded red/orange/green vs 50%/70% benchmarks), Premiums lifetime + 30d, Claims paid lifetime + 30d, Pending count, Opt-in rate
- **Typing indicators in Admin↔Organizer chat (NEW)**:
  - WebSocket protocol extended: client sends `{type:"typing", is_typing:bool}` events; server rebroadcasts to OTHER subscribers on the same thread (exclusion to avoid echo)
  - `useChatLive` hook exports throttled `sendTyping(bool)` (1.5s throttle) + `onTyping` callback
  - Both AdminChatPanel (organizer side) and OrganizerChatTab (admin side) render `"X is typing…"` with pulsing dots, auto-clear after 3s safety timeout, on send, on blur, or on inbound real message

## Backlog
- P3: AI auto-generate flyer text overlay (Emergent LLM key)
- P3: Subscribe-to-blog email capture (feed `db.email_subscribers`)
- P3: Existing dedicated 9:16 `poster_url` field already in CreateEvent — could be made more prominent

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads (background + QR)
- Commission math reads from MongoDB `platform_settings`, not env var
- `routers/seo.py` is the canonical `/api/sitemap.xml` endpoint
- Blog posts live in MongoDB `blog_posts` collection, keyed by `slug`
- Protection pool currency hard-coded NZD in the widget; switch to `platform_settings.currency` if multi-currency ever ships
- Typing WebSocket events use the existing `/api/ws/admin-organizer-chat/{organizer_id}` socket — no new endpoint
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard-side configs (not code bugs)
