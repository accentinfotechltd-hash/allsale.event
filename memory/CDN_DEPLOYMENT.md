# AURA Tickets — CDN Deployment Guide for `/api/files/{path}`

## Problem
- All cover photos, venue floor plans, and uploaded images are served via
  `GET /api/files/{path}` from the FastAPI backend, which fetches them from
  Emergent Object Storage and streams them to the browser.
- The Kubernetes ingress rewrites the `Cache-Control` header we set on these
  responses. Browsers fall back to ETag-based revalidation (already wired —
  returns 304 Not Modified on `If-None-Match`), but every request still hits
  our backend for at least a HEAD-equivalent round-trip.
- At scale (thousands of page views per minute) this adds avoidable latency
  and load on the backend pod.

## Goal
Place a public CDN in front of `/api/files/*` so cache hits never reach the
backend. The CDN respects our origin's ETag and serves cached bytes for the
configured TTL (recommend 24h, with stale-while-revalidate of 7 days).

---

## Option A — Cloudflare CDN (recommended; zero infra change)

1. Add the AURA Tickets domain to Cloudflare and proxy DNS (orange cloud).
2. **Page Rules → Create rule**:
   - URL: `*aura.events/api/files/*` (or your prod domain)
   - Cache Level: **Cache Everything**
   - Edge Cache TTL: **1 day**
   - Browser Cache TTL: **1 day**
3. **Transform Rules → Modify Response Header**:
   - Set `Cache-Control: public, max-age=86400, stale-while-revalidate=604800`
     (this restores what the K8s ingress strips)
4. **Cache Reserve / Tiered Cache** ON for global PoP coverage (optional).
5. Test: `curl -I https://aura.events/api/files/<path>` and check
   `cf-cache-status: HIT` after the second request.

Cost: **free tier sufficient** for early-stage traffic.

---

## Option B — BunnyCDN (cheap, simple, fast for media)

1. Sign up at bunny.net, create a **Pull Zone**:
   - Origin: `https://api.aura.events`
   - Origin path: `/api/files`
   - Cache control: **Override → 1 day**
   - Respect origin Cache-Control: ON (fallback)
2. Replace the served URL in the frontend:
   - `ImageUploader.jsx` already returns `${REACT_APP_BACKEND_URL}/api/files/<path>`
   - Add a `REACT_APP_CDN_URL` (e.g. `https://aura-cdn.b-cdn.net`)
   - Swap to `${CDN_URL}/<path>` when reading images (uploads keep going to backend).
3. Done. Bunny serves the bytes from edge POPs; backend only sees cache misses.

Cost: ~$0.005 / GB (very cheap for images).

---

## Option C — AWS CloudFront + S3 (full migration)

Use this if you also want to move object storage off Emergent. Steps:

1. Provision an S3 bucket (private, server-side encryption ON).
2. Configure CloudFront distribution with:
   - Origin: the S3 bucket (Origin Access Control)
   - Default behavior: cache `*`, TTL 1 day, allowed methods GET/HEAD
   - Response headers policy: `CORS-and-SecurityHeadersPolicy`
3. Swap `routers/uploads.py` to use `boto3` for `put_object` / `head_object`.
4. Frontend uses the CloudFront URL directly (no more `/api/files/*` proxy).
5. Add a presigned-URL endpoint for non-public uploads if needed (e.g. organizer
   private docs in the future).

Cost: S3 ~$0.023/GB, CloudFront ~$0.085/GB out (first 10 TB).

---

## Implementation checklist (when ready)

- [ ] Decide on provider (Cloudflare is the lowest-effort option)
- [ ] Provision + verify TTL with `curl -I` showing `Cache-Control` + cache HIT
- [ ] If using a separate CDN URL: add `REACT_APP_CDN_URL` to `frontend/.env`
- [ ] Update `ImageUploader.jsx` to return `CDN_URL` for display URLs (keep
      uploads going to the backend's `/api/uploads` endpoint)
- [ ] Smoke test cover-photo load times before/after with Chrome DevTools

## Current state (no CDN yet)

- ETag conditional GET works — second request to `/api/files/<path>` returns
  `304 Not Modified` with no body when the browser sends `If-None-Match`.
- This already reduces bandwidth significantly; CDN is purely a latency +
  backend-load optimization for prod scale.
