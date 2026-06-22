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
- **Poster-First flyer redesign**: full poster shown via `object-contain` (no bleed, no overlay text), thin brand strip at bottom with QR + ticket URL, system-font fallback for reliable PNG export
- **Blog / SEO setup (NEW)**:
  - Backend router `routers/blog.py` (public list/get + admin CRUD)
  - Public pages `/blog` (index) & `/blog/:slug` (post)
  - Full SEO meta: `<title>`, description, canonical, OG, Twitter cards, JSON-LD Article schema
  - Admin tab "Blog" with full WYSIWYG editor (reuses RichTextEditor), draft/publish toggle, tags, cover upload, SEO meta overrides
  - Sitemap now includes `/blog` + every published post (`routers/seo.py` is canonical sitemap; removed duplicate from `events.py`)
  - Footer link to `/blog` under Company column
  - Long-form prose styling `.prose-allsale` in `index.css`

## Backlog
- P3: Dedicated 9:16 `poster_url` upload field already exists in CreateEvent (was misreported)
- P3: Protection P&L widget on Admin dashboard — premiums collected vs. claims paid, net pool balance, claim ratio %
- P3: Typing indicators in Admin↔Organizer chat
- P3: AI auto-generate flyer text overlay (Emergent LLM key)

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads (background + QR)
- Commission math reads from MongoDB `platform_settings`, not env var
- Flyer preview wrapper uses explicit `width × height` + `overflow:hidden` so the 1080px DOM doesn't intercept clicks on download buttons below
- `routers/seo.py` is the canonical `/api/sitemap.xml` endpoint; `events.py` previously had a duplicate that shadowed it (now removed)
- Blog posts live in MongoDB `blog_posts` collection, keyed by `slug` (unique, auto-generated from title)
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard-side configs (not code bugs)
