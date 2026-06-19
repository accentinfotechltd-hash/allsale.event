/**
 * usePageMeta — set document title, meta description, canonical URL, Open Graph
 * tags and a JSON-LD payload from inside any React page.
 *
 * Why DOM-manipulation instead of react-helmet? We're avoiding a dependency
 * for a single use-case. Modern Googlebot executes JS, so meta tags set in
 * useEffect ARE indexed. Social-media crawlers (Facebook, Slack, iMessage)
 * generally don't run JS — those continue to fall back to the rich defaults
 * baked into /app/frontend/public/index.html.
 *
 * Usage:
 *   usePageMeta({
 *     title: "Geeta Rabari Live | Allsale Events",
 *     description: "Saturday 15 March, Eventfinda Stadium. Tickets from NZ$50.",
 *     image: event.image_url,
 *     canonical: `https://allsale.events/events/${event.event_id}`,
 *     jsonLd: { "@context": "https://schema.org", "@type": "Event", ... },
 *   });
 */
import { useEffect } from "react";

const META_OWNED = "data-allsale-meta";  // marker so cleanup only touches tags we added

function upsertMeta(selector, attr, key, value) {
  if (!value) return;
  let el = document.head.querySelector(selector);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    el.setAttribute(META_OWNED, "1");
    document.head.appendChild(el);
  }
  el.setAttribute("content", value);
}

function upsertLink(rel, href) {
  if (!href) return;
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    el.setAttribute(META_OWNED, "1");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function upsertJsonLd(payload, id) {
  if (!payload) return;
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("script");
    el.type = "application/ld+json";
    el.id = id;
    el.setAttribute(META_OWNED, "1");
    document.head.appendChild(el);
  }
  try {
    el.textContent = JSON.stringify(payload);
  } catch {
    /* skip silently — bad payload shouldn't crash a page render */
  }
}

export function usePageMeta({ title, description, image, canonical, jsonLd, jsonLdId = "page-jsonld" } = {}) {
  useEffect(() => {
    const prevTitle = document.title;
    if (title) document.title = title;
    upsertMeta('meta[name="description"]', "name", "description", description);
    upsertMeta('meta[property="og:title"]', "property", "og:title", title);
    upsertMeta('meta[property="og:description"]', "property", "og:description", description);
    upsertMeta('meta[property="og:image"]', "property", "og:image", image);
    upsertMeta('meta[property="og:url"]', "property", "og:url", canonical);
    upsertMeta('meta[name="twitter:title"]', "name", "twitter:title", title);
    upsertMeta('meta[name="twitter:description"]', "name", "twitter:description", description);
    upsertMeta('meta[name="twitter:image"]', "name", "twitter:image", image);
    upsertLink("canonical", canonical);
    upsertJsonLd(jsonLd, jsonLdId);
    return () => {
      // Reset the title on unmount; meta tags stay but get overwritten by the
      // next page's usePageMeta call (or fall back to the static defaults).
      document.title = prevTitle;
    };
  }, [title, description, image, canonical, jsonLd, jsonLdId]);
}
