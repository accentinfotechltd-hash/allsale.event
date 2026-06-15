import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CheckCircle2, AlertCircle, DollarSign } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function InfluencerPayouts() {
  const { user, loading: authLoading } = useAuth();
  const nav = useNavigate();
  const [profile, setProfile] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [dash, setDash] = useState(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    try {
      const [prof, p, d] = await Promise.all([
        api.get("/influencer/me"),
        api.get("/influencer/payouts"),
        api.get("/influencer/dashboard"),
      ]);
      if (!prof.data?.enabled) { nav("/influencer/onboarding"); return; }
      setProfile(prof.data);
      setPayouts(p.data || []);
      setDash(d.data);
    } catch {
      toast.error("Couldn't load payouts");
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) { nav("/login"); return; }
    reload();
  }, [user, authLoading]); // eslint-disable-line

  const connectStripe = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/influencer/stripe/onboard", {
        return_url: window.location.href,
        refresh_url: window.location.href,
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Stripe onboarding failed");
      setBusy(false);
    }
  };

  const requestPayout = async () => {
    setBusy(true);
    try {
      await api.post("/influencer/payouts/request");
      toast.success("Payout requested! Funds arrive in 3-5 business days.");
      reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Payout request failed");
    } finally {
      setBusy(false);
    }
  };

  if (!profile || !dash) return <div className="container mx-auto px-6 py-20 text-center opacity-70">Loading…</div>;

  const ready = profile.stripe_payouts_ready;
  const pending = dash.summary.pending_payout;
  const threshold = profile.payout_threshold || 50;

  return (
    <div className="container mx-auto px-6 py-10 max-w-3xl" data-testid="influencer-payouts">
      <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
        <h1 className="serif text-4xl sm:text-5xl">Payouts</h1>
        <Link to="/influencer" className="px-3 py-2 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>← Back to hub</Link>
      </div>

      <div className="rounded-xl border p-6 mb-6" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
        <div className="flex items-center gap-3 mb-2">
          {ready ? <CheckCircle2 size={20} style={{ color: "#10b981" }} /> : <AlertCircle size={20} style={{ color: "var(--accent)" }} />}
          <span className="font-medium">{ready ? "Stripe Connect: Active" : "Stripe Connect: Not connected"}</span>
        </div>
        <p className="text-sm opacity-70 mb-4">
          {ready
            ? "Your Stripe account is verified and ready to receive payouts."
            : "Connect a Stripe account to receive your earnings. Takes 5 minutes (Stripe handles KYC + bank details)."}
        </p>
        <button
          onClick={connectStripe}
          disabled={busy}
          data-testid="stripe-connect-btn"
          className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
          style={{ background: ready ? "transparent" : "var(--accent)", color: ready ? "var(--text)" : "#000", border: ready ? "1px solid var(--border)" : "none" }}
        >
          {ready ? "Re-verify on Stripe" : "Connect Stripe →"}
        </button>
      </div>

      <div className="rounded-xl border p-6 mb-6" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="text-xs uppercase opacity-60">Pending balance</div>
            <div className="serif text-4xl mt-1" style={{ color: "var(--accent)" }}>${pending.toFixed(2)}</div>
            <div className="text-xs opacity-60 mt-1">Minimum payout: ${threshold.toFixed(2)}</div>
          </div>
          <button
            onClick={requestPayout}
            disabled={busy || !ready || pending < threshold}
            data-testid="request-payout-btn"
            className="px-5 py-3 rounded-lg font-medium disabled:opacity-40"
            style={{ background: "var(--accent)", color: "#000" }}
          >
            <DollarSign size={16} className="inline -mt-0.5 mr-1" />
            Request payout
          </button>
        </div>
        {!ready && pending >= threshold && (
          <div className="text-xs mt-3 opacity-70">Connect Stripe above to enable payouts.</div>
        )}
      </div>

      <h2 className="serif text-2xl mb-4">Payout history</h2>
      {payouts.length === 0 ? (
        <div className="rounded-xl border p-8 text-center opacity-70" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          No payouts yet.
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          {payouts.map((p) => (
            <div key={p.payout_id} className="flex items-center justify-between p-4 border-b last:border-0" style={{ borderColor: "var(--border)" }} data-testid={`payout-${p.payout_id}`}>
              <div>
                <div className="font-medium">${p.amount.toFixed(2)}</div>
                <div className="text-xs opacity-60">{new Date(p.requested_at).toLocaleString()}</div>
              </div>
              <span className="px-2 py-1 rounded text-xs uppercase" style={{
                background: p.status === "paid" ? "rgba(16,185,129,0.15)" : p.status === "failed" ? "rgba(239,68,68,0.15)" : "rgba(255,255,255,0.05)",
                color: p.status === "paid" ? "#10b981" : p.status === "failed" ? "#ef4444" : "var(--text)",
              }}>{p.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
