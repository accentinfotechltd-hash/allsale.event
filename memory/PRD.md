# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. MVP covers event browsing, search/filter, atomic-hold ticket booking, custom seat layouts with aisles, QR-code e-tickets, and dashboards for attendees, organizers, and admins. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel (frontend) + Railway (backend).

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe, Resend, Google OAuth, GA4, OpenAI/Gemini via Emergent LLM Key

## What's Implemented (latest session — Feb 2026)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- Vercel serverless OG share image (`/api/og-event.js`)
- Admin → Organizer creation + Event creation on-behalf-of
- Real-time Admin↔Organizer WebSocket chat + **typing indicators**
- Eventfinda-style layout (hero lightbox banner, YouTube embed, vertical poster sidebar)
- Backend image proxy (`/api/img-proxy`) for CORS-safe canvas exports
- Sidebar event poster always visible (poster→banner→image fallback)
- Social flyer "Download all 3 as ZIP" + Poster-First flyer redesign
- **Blog + SEO** — backend CRUD, public `/blog` + `/blog/:slug`, JSON-LD, sitemap, admin CMS tab
- **Protection P&L widget** on Admin → Protection claims tab (premiums vs claims vs net pool vs loss ratio)
- **Newsletter signup (NEW)**:
  - Backend `POST /api/blog/subscribers` (public, idempotent), `POST /api/blog/unsubscribe`, `GET /api/admin/newsletter/subscribers`, `DELETE /api/admin/newsletter/subscribers/{email}`
  - `BlogSubscribeForm` component embedded at bottom of `/blog` index AND every `/blog/:slug` post (passes `source` field so admin can see which surface converted)
  - Idempotent — repeat submits update `last_seen_at`, won't duplicate
  - Unsubscribe support — flips `status` to `unsubscribed`; re-subscribing flips it back
  - Admin sees `Subscribers` panel inside Admin → Blog tab with total/active counts, table of recent signups (email · source · status · joined), per-row Remove, and **CSV export**

## Backlog
- P3: AI auto-generate flyer text overlay (Emergent LLM key)
- P3: Promote Protection P&L widget to Admin dashboard hero
- P3: Make existing `poster_url` field in CreateEvent more prominent

## Critical Notes
- `/api/img-proxy` must stay — required for `html-to-image` flyer downloads
- Commission math reads from MongoDB `platform_settings`
- `routers/seo.py` is the canonical `/api/sitemap.xml`
- Blog posts → `blog_posts` collection (keyed by `slug`)
- Newsletter subscribers → `blog_subscribers` collection (keyed by `email`, lowercased)
- Newsletter admin endpoints live under `/admin/newsletter/...` (NOT `/admin/blog/...`) to avoid FastAPI path collision with `/admin/blog/{slug}`
- Typing WebSocket events on existing `/api/ws/admin-organizer-chat/{organizer_id}` socket
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard configs (not bugs)
