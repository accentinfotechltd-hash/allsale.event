/**
 * Google Analytics 4 — single source of truth for the whole app.
 *
 * Why a wrapper instead of hard-coding `gtag(...)` calls?
 *   • If the env var is missing (preview, local dev), every call no-ops so
 *     we never see "gtag is not defined" errors in the console.
 *   • Easier to swap providers later (Plausible / Posthog / Fathom).
 *
 * The actual `gtag.js` script tag is injected once by `initAnalytics()`
 * (called from App.js on mount). All other helpers are safe to call at
 * any time — they queue into `window.dataLayer` even before the script
 * has loaded, which is how Google's snippet is meant to be used.
 */

const MEASUREMENT_ID = process.env.REACT_APP_GA_MEASUREMENT_ID || "";

// Whether to fire events. We fire if EITHER:
//   (a) a build-time env-var measurement ID is set, OR
//   (b) the global window.gtag is already loaded by `public/index.html`
// This way the hardcoded tag in index.html (G-E4WPC8V5XZ) keeps working
// even without a build-time env var configured.
function gaEnabled() {
  if (typeof window === "undefined") return false;
  if (MEASUREMENT_ID) return true;
  return typeof window.gtag === "function";
}

function gtag(...args) {
  if (typeof window === "undefined") return;
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(args);
}

let initialized = false;

export function initAnalytics() {
  if (initialized) return;
  // If the loader was already injected by public/index.html, skip — just
  // mark as initialized so trackPageView etc. fire normally.
  if (typeof window !== "undefined" && typeof window.gtag === "function") {
    initialized = true;
    return;
  }
  if (!MEASUREMENT_ID) return; // nothing to load
  if (typeof window === "undefined") return;
  initialized = true;

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID, { send_page_view: false });
}

export function trackPageView(path, title) {
  if (!gaEnabled()) return;
  gtag("event", "page_view", {
    page_path: path,
    page_title: title || (typeof document !== "undefined" ? document.title : ""),
    page_location: typeof window !== "undefined" ? window.location.href : "",
  });
}

/**
 * Fire an arbitrary GA event.
 * @param {string} name - e.g. "purchase", "sign_up", "join_campaign"
 * @param {object} params - GA4 recommended params for that event
 */
export function trackEvent(name, params = {}) {
  if (!gaEnabled()) return;
  gtag("event", name, params);
}

/* ---------------------------------------------------------------------------
 * GA4 Enhanced E-commerce — funnel events for the booking flow.
 * Standard event names so GA4's built-in Monetization reports light up
 * (Reports → Monetization → E-commerce purchases / Conversions / Funnel).
 * ---------------------------------------------------------------------------*/

export function trackViewItem({ eventId, eventTitle, price, currency = "NZD", category }) {
  trackEvent("view_item", {
    currency,
    value: Number(price) || 0,
    items: [{
      item_id: eventId,
      item_name: eventTitle,
      item_category: category,
      price: Number(price) || 0,
      quantity: 1,
    }],
  });
}

export function trackAddToCart({ eventId, eventTitle, price, currency = "NZD", quantity = 1, tier }) {
  trackEvent("add_to_cart", {
    currency,
    value: (Number(price) || 0) * quantity,
    items: [{
      item_id: eventId,
      item_name: eventTitle,
      item_variant: tier,
      price: Number(price) || 0,
      quantity,
    }],
  });
}

export function trackPurchase({ bookingId, eventId, eventTitle, amount, currency = "NZD", quantity = 1 }) {
  trackEvent("purchase", {
    transaction_id: bookingId,
    value: Number(amount) || 0,
    currency,
    items: [{
      item_id: eventId,
      item_name: eventTitle,
      quantity,
      price: Number(amount) / Math.max(1, quantity),
    }],
  });
}

export function trackSignup(method = "email", role = "attendee") {
  trackEvent("sign_up", { method, role });
}

export function trackInfluencerJoin(eventId, code) {
  trackEvent("join_campaign", { event_id: eventId, affiliate_code: code });
}

/**
 * GA4 standard `share` event — fires whenever a visitor uses a share button.
 * Method is the channel ("whatsapp" | "facebook" | "twitter" | "telegram" | "copy" | "native").
 * Once enough shares accrue, Reports → Engagement → Events shows which channel
 * drives the most clicks back, and Explorations can chain share→view_item→purchase.
 */
export function trackShare({ method, eventId, eventTitle }) {
  trackEvent("share", {
    method,
    content_type: "event",
    item_id: eventId,
    item_name: eventTitle,
  });
}

