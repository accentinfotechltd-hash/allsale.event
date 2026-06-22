# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. MVP covers event browsing, search/filter, atomic-hold ticket booking, custom seat layouts with aisles, QR-code e-tickets, and dashboards for attendees, organizers, and admins. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel (frontend) + Railway (backend).

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe, Resend, Google OAuth, GA4, **Emergent LLM Key** (Gemini 2.5 Pro) for Seatmap AI + Flyer AI

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Vercel serverless OG share image
- Admin → Organizer creation + Event creation on-behalf-of
- Real-time Admin↔Organizer WebSocket chat **+ typing indicators**
- Eventfinda-style layout (hero lightbox banner, YouTube embed, vertical poster sidebar)
- Backend image proxy `/api/img-proxy` for CORS-safe canvas exports
- Sidebar event poster always visible (poster→banner→image fallback)
- Social flyer "Download all 3 as ZIP" + Poster-First flyer redesign (`object-contain`)
- Blog + SEO — backend CRUD, public pages, JSON-LD, sitemap, admin CMS tab
- Newsletter signup — public `BlogSubscribeForm` + admin Subscribers panel + CSV export
- Protection P&L widget on Admin → Protection claims
- **AI Flyer Text Overlay (NEW)**:
  - Backend `POST /api/events/{event_id}/flyer/generate-text` uses **Emergent LLM Key + Gemini 2.5 Pro** via `emergentintegrations.llm.chat.LlmChat` (same pattern as `seatmap_ai.py`)
  - Returns `{headline, tagline, cta}` — punchy ad-copy tailored to the event title/category/description
  - Frontend `/events/:id/share` adds **"Add AI text overlay"** button. When clicked, calls API, renders editable form with char counters for all 3 lines + **Regenerate** button + **Remove text overlay** toggle
  - `FlyerCanvas` accepts an `aiText` prop. When set: renders a translucent gradient caption strip overlaid on bottom of the poster image (headline in Georgia serif with text-shadow, tagline below in lighter weight) and swaps the brand strip's "GET TICKETS AT" micro-copy with the AI-generated CTA
  - All 3 formats (Square/Story/Wide) use the same `aiText`; ZIP download captures the overlay in all 3 PNGs
  - **Emergent LLM Key refresh**: rotated the stale key in `backend/.env` via `emergent_integrations_manager` — old key was returning `Invalid API key` from LiteLLM

## Backlog
- P3: Promote Protection P&L widget to Admin dashboard hero
- P3: "Notify subscribers about this post" button on blog publish flow (fan-out via Resend)
- P3: Make existing `poster_url` field in CreateEvent more prominent

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads
- Emergent LLM Key model must be `"gemini-2.5-pro"` (the only Gemini that works through the LiteLLM proxy). `gemini-2.5-flash` returns `OpenAIException Invalid API key`.
- Newsletter admin endpoints live under `/admin/newsletter/...` (NOT `/admin/blog/...`) to avoid FastAPI path collision with `/admin/blog/{slug}`
- Blog posts → `blog_posts`, subscribers → `blog_subscribers` (lowercased email PK)
- Commission math reads from MongoDB `platform_settings`
- `routers/seo.py` is the canonical `/api/sitemap.xml`
- Typing WebSocket events on `/api/ws/admin-organizer-chat/{organizer_id}`
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs (not bugs)
