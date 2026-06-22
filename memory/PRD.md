# Allsale Events — Product Requirements (PRD)

## Original Problem Statement
Build an Eventbrite / BookMyShow-style ticketing platform. MVP covers event browsing, search/filter, atomic-hold ticket booking, custom seat layouts with aisles, QR-code e-tickets, and dashboards for attendees, organizers, and admins. Stack: **React + FastAPI + MongoDB Atlas**, deployed on Vercel (frontend) + Railway (backend).

## Architecture
- **Backend**: FastAPI, routers in `/app/backend/routers/`, MongoDB Atlas, WebSockets for live seat/chat updates
- **Frontend**: React 19, Tailwind, Shadcn UI, deployed to Vercel
- **Integrations**: Stripe (Payments/Tax/Boost), Resend (Email), Google OAuth, GA4, OpenAI/Gemini via Emergent LLM Key

## What's Implemented (latest session)
- Event browsing, atomic seat hold, QR e-tickets, dashboards
- **Vercel serverless OG share image** (`/api/og-event.js`)
- **Google Search Console** verification meta tag
- **Admin → Organizer creation + Event creation on-behalf-of**
- **Real-time Admin↔Organizer WebSocket chat** (`/api/ws/admin-organizer-chat`)
- **Eventfinda-style layout**: hero lightbox banner, YouTube promo video embed, vertical poster sidebar
- **Rich-text event descriptions** with sanitized HTML rendering
- **Backend image proxy** (`/api/img-proxy`) to fix CORS on flyer PNG download
- **Dynamic commission** (reads from `platform_settings` collection)
- **Fan-out emails** for bookings & enquiries (organizer + admin)
- **IP protection**: `robots.txt`, `/terms`, copyright meta tags
- **Sidebar event poster always visible** — falls back from `poster_url → banner_url → image_url` so every event shows a 9:16 poster in the sidebar (Feb 2026)

## Backlog
- P2: "Download all 3 flyers as ZIP" on `/events/:id/share` (jszip)
- P2: AI auto-generate flyer text overlay (Emergent LLM key)
- P3: Protection P&L widget on Admin dashboard
- P3: `/blog` SEO setup
- P3: Typing indicators in Admin↔Organizer chat
- P3: Dedicated poster_url upload field in Create/Edit Event form

## Critical Notes
- Image proxy `/api/img-proxy` must stay — required to avoid tainted-canvas during `html-to-image` flyer download
- Commission math reads from MongoDB `platform_settings`, not env var
- Google OAuth `redirect_uri_mismatch` & Stripe USD/NZD display are dashboard-side configs (not code bugs)
