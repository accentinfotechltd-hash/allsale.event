import { useEffect } from "react";

/**
 * SeoHead — sets `<title>`, meta description, Open Graph + Twitter card,
 * and (when given an event) a Schema.org Event JSON-LD blob. Imperative
 * because we don't bundle react-helmet — for a 3-tag-update use case it
 * isn't worth the dependency weight.
 */
export default function SeoHead({ title, description, image, url, event }) {
  useEffect(() => {
    if (title) document.title = title;
    upsertMeta("name", "description", description);
    upsertMeta("property", "og:title", title);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:image", image);
    upsertMeta("property", "og:url", url);
    upsertMeta("property", "og:type", event ? "event" : "website");
    upsertMeta("name", "twitter:card", "summary_large_image");
    upsertMeta("name", "twitter:title", title);
    upsertMeta("name", "twitter:description", description);
    upsertMeta("name", "twitter:image", image);

    // Schema.org JSON-LD for rich Google results (only for event pages)
    let script = document.getElementById("ld-event");
    if (script) script.remove();
    if (event) {
      script = document.createElement("script");
      script.id = "ld-event";
      script.type = "application/ld+json";
      script.text = JSON.stringify({
        "@context": "https://schema.org",
        "@type": "Event",
        name: event.title,
        startDate: event.date,
        eventStatus: "https://schema.org/EventScheduled",
        eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
        location: { "@type": "Place", name: event.venue,
          address: { "@type": "PostalAddress", addressLocality: event.city, addressCountry: event.country || "NZ" } },
        image: event.banner_url || event.image_url,
        description: event.description,
        offers: { "@type": "Offer", url, price: event.min_price || 0, priceCurrency: event.currency || "NZD",
          availability: "https://schema.org/InStock" },
      });
      document.head.appendChild(script);
    }
    return () => { /* leave meta tags in place — next page will overwrite */ };
  }, [title, description, image, url, event]);
  return null;
}

function upsertMeta(attr, name, content) {
  if (content == null) return;
  let el = document.querySelector(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", String(content));
}
