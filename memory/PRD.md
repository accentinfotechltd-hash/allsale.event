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
- **Sidebar event poster always visible** — falls back through `poster_url → banner_url → image_url`
- **Social flyer "Download all 3 as ZIP"** — uses `jszip` + `file-saver`, packs square/story/wide PNGs into one archive
- **Flyer visual polish** — brightened bg photo (brightness 0.7 vs 0.55), softer top gradient so the photo can breathe, bg source falls back through poster/banner/image, QR code routed through `/api/img-proxy` so canvas stays untainted, `waitForAssets()` preloads imgs+fonts before snapshot
- **CRACO patch** — excludes `node_modules` from `source-map-loader` (jszip→pako sourcemap ENOENT)

## Backlog
- P2: AI auto-generate flyer text overlay (Emergent LLM key)
- P3: Dedicated `poster_url` upload field in Create/Edit Event form
- P3: Protection P&L widget on Admin dashboard
- P3: `/blog` SEO setup
- P3: Typing indicators in Admin↔Organizer chat

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads (both background and QR)
- Commission math reads from MongoDB `platform_settings`, not env var
- Flyer preview wrapper uses explicit `width × height` + `overflow:hidden` so the 1080px DOM doesn't intercept clicks on download buttons below
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard-side configs (not code bugs)
