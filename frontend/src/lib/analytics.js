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

function gtag(...args) {
  if (typeof window === "undefined") return;
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(args);
}

let initialized = false;

export function initAnalytics() {
  if (initialized) return;
  if (!MEASUREMENT_ID) return; // no-op when env var missing
  if (typeof window === "undefined") return;
  initialized = true;

  // Inject the async gtag.js loader exactly once
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
  document.head.appendChild(script);

  // Bootstrap the dataLayer (matches the snippet GA gives you in the console)
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  // We send_page_view=false because we manage SPA page views ourselves
  // (React Router doesn't fire window navigations).
  window.gtag("config", MEASUREMENT_ID, { send_page_view: false });
}

export function trackPageView(path, title) {
  if (!MEASUREMENT_ID) return;
  gtag("event", "page_view", {
    page_path: path,
    page_title: title || (typeof document !== "undefined" ? document.title : ""),
    page_location: typeof window !== "undefined" ? window.location.href : "",
    send_to: MEASUREMENT_ID,
  });
}

/**
 * Fire an arbitrary GA event.
 * @param {string} name - e.g. "purchase", "sign_up", "join_campaign"
 * @param {object} params - GA4 recommended params for that event
 */
export function trackEvent(name, params = {}) {
  if (!MEASUREMENT_ID) return;
  gtag("event", name, { ...params, send_to: MEASUREMENT_ID });
}

/* ---------------------------------------------------------------------------
 * Convenience wrappers for the conversions we care about most.
 * Using GA4 recommended event names so the standard reports light up.
 * ---------------------------------------------------------------------------*/

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
