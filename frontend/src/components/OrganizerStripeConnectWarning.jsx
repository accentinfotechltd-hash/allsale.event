import { useEffect, useState } from "react";
import { ArrowRight, Loader2, Zap, X } from "lucide-react";
import api from "@/lib/api";

const DISMISS_KEY = "stripe_connect_invite_dismissed_at";
const DISMISS_DAYS = 7; // re-show after 7 days

/**
 * Friendly OPTIONAL upgrade card shown to organizers who:
 *   1) have at least one paid booking, AND
 *   2) have NOT connected Stripe Connect (charges_enabled !== true)
 *
 * Tone is "want faster payouts?" not "ACTION REQUIRED" — manual bank
 * transfers continue to work exactly as before. This is purely opt-in.
 * Dismissible (auto-re-show after 7 days).
 */
export default function OrganizerStripeConnectWarning() {
  const [show, setShow] = useState(false);
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Check 7-day dismiss timer first — skip the API calls if recently dismissed.
    try {
      const dismissedAt = localStorage.getItem(DISMISS_KEY);
      if (dismissedAt) {
        const ageMs = Date.now() - parseInt(dismissedAt, 10);
        if (ageMs < DISMISS_DAYS * 24 * 60 * 60 * 1000) {
          setShow(false);
          return;
        }
      }
    } catch { /* localStorage unavailable — proceed */ }

    const load = async () => {
      try {
        const balRes = await api.get("/organizer/payouts/balance");
        const lifetimePaid = (balRes.data?.lifetime_paid || 0) + (balRes.data?.available?.gross || 0) + (balRes.data?.pending || 0);
        const bookings = balRes.data?.available?.bookings || 0;
        const hasRevenue = lifetimePaid > 0 || bookings > 0;

        const meRes = await api.get("/auth/me");
        const chargesEnabled = !!meRes.data?.stripe_charges_enabled;

        if (hasRevenue && !chargesEnabled) {
          setStats({
            lifetime: lifetimePaid,
            currency: balRes.data?.settings?.currency?.toUpperCase() || "NZD",
            bookings,
          });
          setShow(true);
        } else {
          setShow(false);
        }
      } catch {
        setShow(false);
      }
    };
    load();
  }, []);

  const startOnboarding = async () => {
    setBusy(true);
    try {
      const r = await api.post("/stripe/connect/onboard", { return_url: window.location.origin + "/organizer?stripe_return=1" });
      if (r.data?.url) {
        window.location.href = r.data.url;
      }
    } catch (e) {
      console.error("[stripe connect] onboard start failed", e);
      setBusy(false);
    }
  };

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* ignore */ }
    setShow(false);
  };

  if (!show || !stats) return null;

  return (
    <div
      data-testid="organizer-stripe-warning-banner"
      className="mb-6 rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-sky-50/40 to-emerald-50/40 p-5 shadow-sm relative"
    >
      <button
        onClick={dismiss}
        data-testid="organizer-stripe-dismiss"
        aria-label="Dismiss"
        className="absolute top-3 right-3 p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
      <div className="flex flex-col sm:flex-row gap-4 items-start pr-8">
        <div className="shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br from-sky-500 to-emerald-500 flex items-center justify-center shadow-sm">
          <Zap className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-[0.18em] text-sky-700 font-semibold mb-1">
            Optional upgrade · faster payouts
          </div>
          <h3 className="text-base font-semibold text-slate-900 mb-1.5">
            Want your ticket revenue to land instantly?
          </h3>
          <p className="text-sm text-slate-600 leading-relaxed max-w-2xl">
            Right now we pay you via manual bank transfer after each event (works great — keep using it if you like!).
            If you connect Stripe, money goes straight to your Stripe balance the moment a ticket sells.
            3-minute setup, no change in fees.
          </p>
          <div className="mt-3 flex flex-wrap gap-2 items-center">
            <button
              data-testid="organizer-stripe-warning-cta"
              onClick={startOnboarding}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white text-sm font-medium"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Try Stripe Connect <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={dismiss}
              data-testid="organizer-stripe-maybe-later"
              className="px-3 py-2 rounded-lg text-sm font-medium text-slate-500 hover:text-slate-700 hover:bg-slate-50"
            >
              Maybe later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
