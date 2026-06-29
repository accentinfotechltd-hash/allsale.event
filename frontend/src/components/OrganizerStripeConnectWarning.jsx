import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import api from "@/lib/api";

/**
 * Hard-warning banner shown to organizers who:
 *   1) have at least one paid booking on their events, AND
 *   2) have NOT completed Stripe Connect onboarding (charges_enabled !== true)
 *
 * Different from `StripeConnectPanel` (passive panel with the Connect button)
 * and from `OrganizerLaunchChecklist` (checklist for new organizers). This is
 * the "you are losing money" warning for organizers who already have revenue
 * landing on Allsale's master account instead of their own.
 *
 * Hidden the moment they connect (charges_enabled === true) OR if they have
 * zero paid bookings yet (in which case the launch checklist is doing the
 * onboarding nudge).
 */
export default function OrganizerStripeConnectWarning() {
  const [show, setShow] = useState(false);
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        // Check own balance: if there's any paid booking, we have revenue to talk about.
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

  if (!show || !stats) return null;

  const sym = stats.currency === "NZD" ? "NZ$" : stats.currency === "AUD" ? "A$" : stats.currency === "USD" ? "US$" : `${stats.currency} `;
  const fmt = `${sym}${stats.lifetime.toFixed(2)}`;

  return (
    <div
      data-testid="organizer-stripe-warning-banner"
      className="mb-6 rounded-2xl border-2 border-rose-300 bg-gradient-to-r from-rose-50 to-amber-50 p-5 shadow-sm"
    >
      <div className="flex flex-col sm:flex-row gap-4 items-start">
        <div className="shrink-0 w-12 h-12 rounded-full bg-rose-100 flex items-center justify-center">
          <AlertTriangle className="w-6 h-6 text-rose-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-[0.2em] text-rose-700 font-semibold mb-1">
            Action required · Stripe Connect not set up
          </div>
          <h3 className="text-lg font-semibold text-slate-900 mb-1">
            You have <span className="text-rose-700 tabular-nums">{fmt}</span> in revenue waiting — but Stripe isn&apos;t connected
          </h3>
          <p className="text-sm text-slate-700 leading-relaxed max-w-2xl">
            Until you connect Stripe, ticket revenue lands on Allsale&apos;s master account and gets paid out to your bank manually (slower).
            Once connected, money flows directly to your Stripe balance at the moment of each sale — and you&apos;ll see every charge in your
            own Stripe dashboard. Takes about 3 minutes (bank + ID).
          </p>
          <div className="mt-3 flex flex-wrap gap-2 items-center">
            <button
              data-testid="organizer-stripe-warning-cta"
              onClick={startOnboarding}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white text-sm font-medium"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Connect Stripe now <ArrowRight className="w-4 h-4" />
            </button>
            <span className="text-xs text-slate-500">·  3 mins · No platform fee charged</span>
          </div>
        </div>
      </div>
    </div>
  );
}
