/**
 * Vercel Serverless Function — per-event Open Graph HTML for social crawlers.
 *
 * Why this exists:
 *   Facebook, WhatsApp, iMessage, LinkedIn, Slack, Discord, Twitter etc. fetch
 *   the URL without executing JavaScript. The SPA's React-side `usePageMeta`
 *   never runs for them, so they fall back to the static Allsale logo defined
 *   in `public/index.html`.
 *
 *   This function fetches the event from the backend, returns a minimal HTML
 *   document with proper og:* / twitter:* tags pointing at the event poster,
 *   and meta-refreshes any human who somehow lands here back to the SPA URL.
 *
 * How it gets invoked:
 *   `vercel.json` rewrites `/events/:id` to `/api/og-event?id=:id` ONLY when
 *   the request's User-Agent matches a known social-crawler pattern. Normal
 *   browser visits and Googlebot are untouched.
 *
 * Required env on Vercel:
 *   - BACKEND_URL  (preferred) or REACT_APP_BACKEND_URL — the API base, eg
 *     https://api.allsale.events  (no trailing slash)
 */

const SITE_URL = "https://allsale.events";
const FALLBACK_IMAGE = `${SITE_URL}/allsale-logo.png`;

function escapeHtml(input = "") {
  return String(input).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function buildHtml(event, id) {
  const title = event?.title || "Event";
  const venue = [event?.venue, event?.city].filter(Boolean).join(", ");
  const desc =
    `${title}${venue ? ` — ${venue}` : ""}. ` +
    (event?.description ? String(event.description).slice(0, 140) : "Book tickets on Allsale Events.");
  const image = event?.banner_url || event?.image_url || FALLBACK_IMAGE;
  const url = `${SITE_URL}/events/${encodeURIComponent(id)}`;

  const t = escapeHtml(title);
  const d = escapeHtml(desc);
  const i = escapeHtml(image);
  const u = escapeHtml(url);

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>${t} | Allsale Events</title>
    <meta name="description" content="${d}" />
    <link rel="canonical" href="${u}" />

    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Allsale Events" />
    <meta property="og:url" content="${u}" />
    <meta property="og:title" content="${t}" />
    <meta property="og:description" content="${d}" />
    <meta property="og:image" content="${i}" />
    <meta property="og:image:alt" content="${t}" />
    <meta property="og:locale" content="en_NZ" />

    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${t}" />
    <meta name="twitter:description" content="${d}" />
    <meta name="twitter:image" content="${i}" />

    <meta http-equiv="refresh" content="0;url=${u}" />
  </head>
  <body>
    <h1>${t}</h1>
    <p>${d}</p>
    <p><a href="${u}">Open ${t} on Allsale Events</a></p>
  </body>
</html>`;
}

function fallbackHtml(id) {
  const url = `${SITE_URL}/events/${encodeURIComponent(id || "")}`;
  return `<!doctype html><html><head><meta http-equiv="refresh" content="0;url=${escapeHtml(url)}"/></head><body><a href="${escapeHtml(url)}">View event on Allsale Events</a></body></html>`;
}

export default async function handler(req, res) {
  const id = (req.query && req.query.id) || "";
  if (!id) {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    return res.status(400).send(fallbackHtml(""));
  }

  const backend = process.env.BACKEND_URL || process.env.REACT_APP_BACKEND_URL;
  if (!backend) {
    // No backend configured — at least give crawlers the static logo card.
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    return res.status(200).send(buildHtml({}, id));
  }

  try {
    const r = await fetch(`${backend.replace(/\/$/, "")}/api/events/${encodeURIComponent(id)}`, {
      // Crawlers tolerate slow responses, but cap to keep Vercel fn snappy.
      signal: AbortSignal.timeout(4500),
      headers: { Accept: "application/json" },
    });
    if (!r.ok) {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      return res.status(200).send(buildHtml({}, id));
    }
    const event = await r.json();
    const html = buildHtml(event, id);
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    // Cache at Vercel's edge so repeated crawls don't hammer the backend.
    res.setHeader("Cache-Control", "public, max-age=300, s-maxage=600, stale-while-revalidate=86400");
    return res.status(200).send(html);
  } catch {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    return res.status(200).send(buildHtml({}, id));
  }
}
