import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Banknote, ExternalLink, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Organizer-facing Stripe Connect onboarding strip.
 *
 * Renders one of three states:
 *   – Not connected: "Connect with Stripe" CTA.
 *   – In progress (account exists, charges/payouts not yet enabled): "Continue onboarding" + missing requirements list.
 *   – Verified: green pill + "Open Stripe dashboard" link.
 *
 * Refreshes from `GET /stripe/connect/status` on mount and every 8s when the
 * page is open. Also re-checks immediately when the URL carries
 * `?stripe_return=1` (set on the return URL Stripe redirects back to).
 */
export default function StripeConnectPanel() {
  const [status, setStatus] = useState(null); // null while loading
  const [working, setWorking] = useState(false);
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/stripe/connect/status");
      setStatus(data);
    } catch {
      setStatus({ stripe_account_id: null });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // When organizer returns from Stripe onboarding, poll a few times — the
  // webhook may not have landed yet so the badge needs a refresh.
  useEffect(() => {
    if (params.get("stripe_return") !== "1") return;
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      await load();
      if (attempts < 4) setTimeout(tick, 3000);
      else {
        const next = new URLSearchParams(params);
        next.delete("stripe_return");
        setParams(next, { replace: true });
      }
    };
    tick();
  }, [params.get("stripe_return")]);

  const startOnboarding = async () => {
    setWorking(true);
    try {
      const returnUrl = `${window.location.origin}/organizer?stripe_return=1`;
      const { data } = await api.post("/stripe/connect/onboard", { return_url: returnUrl });
      if (data?.url) window.location.href = data.url;
      else toast.error("Couldn't start onboarding — try again");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't start onboarding");
    } finally {
      setWorking(false);
    }
  };

  const openDashboard = async () => {
    setWorking(true);
    try {
      const { data } = await api.post("/stripe/connect/dashboard-link", {});
      if (data?.url) window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't open dashboard");
    } finally {
      setWorking(false);
    }
  };

  const resetConnection = async () => {
    if (!window.confirm("Reset your Stripe connection? This will clear the link to your Stripe account so you can start the onboarding flow again from scratch. (It does NOT delete the account on Stripe — you can still log in to your Stripe dashboard directly.)")) return;
    setWorking(true);
    try {
      await api.post("/stripe/connect/reset", {});
      toast.success("Stripe connection reset — click 'Connect with Stripe' to start fresh.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't reset");
    } finally {
      setWorking(false);
    }
  };

  const [health, setHealth] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const runHealth = async () => {
    setDiagnosing(true);
    try {
      const { data } = await api.get("/organizer/stripe/health");
      setHealth(data);
      // Live state may have changed — refresh the badge.
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Health check failed");
    } finally {
      setDiagnosing(false);
    }
  };

  if (status === null) {
    return (
      <div
        className="mb-6 p-4 rounded-2xl border flex items-center gap-3"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
        data-testid="stripe-connect-panel-loading"
      >
        <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--text-dim)" }} />
        <span className="text-sm" style={{ color: "var(--text-dim)" }}>Checking payout setup…</span>
      </div>
    );
  }

  const hasAccount = !!status.stripe_account_id;
  const verified = status.stripe_charges_enabled && status.stripe_payouts_enabled;
  const inProgress = hasAccount && !verified;
  const requirementsDue = status.stripe_requirements_due || [];

  return (
    <div
      className="mb-6 p-5 rounded-2xl border flex flex-col sm:flex-row items-start sm:items-center gap-4"
      style={{
        borderColor: verified ? "rgba(46,160,67,0.4)" : "var(--border)",
        background: verified ? "rgba(46,160,67,0.06)" : "var(--bg-card)",
      }}
      data-testid="stripe-connect-panel"
    >
      <div
        className="w-11 h-11 rounded-full flex items-center justify-center shrink-0"
        style={{
          background: verified ? "rgba(46,160,67,0.18)" : "var(--bg-elev)",
          color: verified ? "rgb(46,160,67)" : "var(--accent)",
        }}
      >
        <Banknote className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        {!hasAccount && (
          <>
            <div className="text-sm font-medium mb-0.5">Get paid for your events</div>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>
              Connect a Stripe account once. We&apos;ll transfer your ticket revenue automatically <b>5 days after each event finishes</b>. Zero commission — you keep the full ticket price.
            </div>
          </>
        )}
        {inProgress && (
          <>
            <div className="text-sm font-medium mb-0.5 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" style={{ color: "var(--accent)" }} />
              Finish your Stripe setup to receive payouts
            </div>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>
              Stripe still needs {requirementsDue.length > 0 ? `${requirementsDue.length} more detail${requirementsDue.length === 1 ? "" : "s"}` : "a few more details"} before they&apos;ll release funds.
              {requirementsDue.length > 0 && (
                <span className="block mt-1">
                  Missing:{" "}
                  <span style={{ color: "var(--text-muted)" }}>
                    {requirementsDue.slice(0, 5).map((r) => r.replace(/_/g, " ")).join(", ")}
                    {requirementsDue.length > 5 ? "…" : ""}
                  </span>
                </span>
              )}
              {status._warning && (
                <span className="block mt-1" style={{ color: "rgb(198,40,40)" }}>
                  ⚠ {status._warning}
                </span>
              )}
              <button
                type="button"
                onClick={resetConnection}
                className="block mt-1.5 underline text-[11px]"
                style={{ color: "var(--text-dim)" }}
                data-testid="stripe-connect-reset-btn"
              >
                Start over with a new Stripe account
              </button>
              <button
                type="button"
                onClick={runHealth}
                disabled={diagnosing}
                className="block mt-1 underline text-[11px]"
                style={{ color: "var(--accent)" }}
                data-testid="stripe-connect-self-diagnose-btn"
              >
                {diagnosing ? "Checking with Stripe…" : "Why isn't this verified?"}
              </button>
              {health && health.ok && (health.currently_due?.length > 0 || health.past_due?.length > 0 || health.disabled_reason) && (
                <div className="mt-3 p-3 rounded-lg border text-[11px]" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }} data-testid="stripe-connect-self-diagnose-result">
                  {health.disabled_reason && (
                    <div className="mb-1.5" style={{ color: "rgb(198,40,40)" }}>⚠ {health.disabled_reason.replace(/_/g, " ")}</div>
                  )}
                  {health.past_due?.length > 0 && (
                    <>
                      <div className="font-medium mb-0.5" style={{ color: "rgb(198,40,40)" }}>Past due — fix these urgently:</div>
                      <ul className="list-disc list-inside mb-1.5" style={{ color: "rgb(198,40,40)" }}>
                        {health.past_due.map((r) => <li key={r}>{r.replace(/_/g, " ").replace(/\./g, " → ")}</li>)}
                      </ul>
                    </>
                  )}
                  {health.currently_due?.length > 0 && (
                    <>
                      <div className="font-medium mb-0.5" style={{ color: "var(--text-muted)" }}>Currently due:</div>
                      <ul className="list-disc list-inside" style={{ color: "var(--text-muted)" }}>
                        {health.currently_due.map((r) => <li key={r}>{r.replace(/_/g, " ").replace(/\./g, " → ")}</li>)}
                      </ul>
                    </>
                  )}
                  <div className="mt-2" style={{ color: "var(--text-dim)" }}>Fix these by clicking <b>Continue onboarding</b> above.</div>
                </div>
              )}
              {health && health.ok === false && (
                <div className="mt-3 p-3 rounded-lg border text-[11px]" style={{ borderColor: "rgba(198,40,40,0.4)", background: "rgba(198,40,40,0.06)", color: "rgb(198,40,40)" }}>
                  ⚠ {health.reason}
                </div>
              )}
            </div>
          </>
        )}
        {verified && (
          <>
            <div className="text-sm font-medium mb-0.5 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" style={{ color: "rgb(46,160,67)" }} />
              Stripe connected — ready for payouts
            </div>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>
              Your share of each event lands in your Stripe balance <b>5 days after the event ends</b>. <a href="/organizer/transfers" style={{ color: "var(--accent)" }} data-testid="stripe-connect-transfers-link">View transfer history →</a>
            </div>
          </>
        )}
      </div>
      <div className="flex gap-2 self-stretch sm:self-auto">
        {!hasAccount && (
          <button
            type="button"
            onClick={startOnboarding}
            disabled={working}
            className="btn-primary !py-2 !px-4"
            data-testid="stripe-connect-start-btn"
          >
            {working ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}
            Connect with Stripe
          </button>
        )}
        {inProgress && (
          <button
            type="button"
            onClick={startOnboarding}
            disabled={working}
            className="btn-primary !py-2 !px-4"
            data-testid="stripe-connect-continue-btn"
          >
            {working ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
            Continue onboarding
          </button>
        )}
        {verified && (
          <button
            type="button"
            onClick={openDashboard}
            disabled={working}
            className="btn-ghost !py-2 !px-4"
            data-testid="stripe-connect-dashboard-btn"
          >
            {working ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
            Open Stripe dashboard
          </button>
        )}
      </div>
    </div>
  );
}
