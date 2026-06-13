import { useEffect, useState } from "react";
import api from "@/lib/api";
import { CheckCircle2, AlertCircle, RefreshCw, Loader2, Copy, Check } from "lucide-react";

/**
 * Admin-only Stripe diagnostics panel.
 *
 *   1. Webhook health — confirms the Stripe Connect dashboard webhook is
 *      wired up correctly (signature secret set, all required events seen
 *      in the last 30 days, deliveries flowing).
 *   2. Tax status — shows whether Stripe Tax is enabled + tax collected
 *      breakdown when active.
 *
 * Mount on the Admin → Stripe tab.
 */
export default function StripeAdminDiagnostics() {
  const [health, setHealth] = useState(null);
  const [tax, setTax] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [h, t, r] = await Promise.all([
      api.get("/admin/stripe/webhook-health").then((r) => r.data).catch(() => null),
      api.get("/admin/stripe/tax-status").then((r) => r.data).catch(() => null),
      api.get("/admin/stripe/tax-report?days=30").then((r) => r.data).catch(() => null),
    ]);
    setHealth(h);
    setTax(t);
    setReport(r);
    setLoading(false);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [h, t, r] = await Promise.all([
        api.get("/admin/stripe/webhook-health").then((r) => r.data).catch(() => null),
        api.get("/admin/stripe/tax-status").then((r) => r.data).catch(() => null),
        api.get("/admin/stripe/tax-report?days=30").then((r) => r.data).catch(() => null),
      ]);
      if (cancelled) return;
      setHealth(h);
      setTax(t);
      setReport(r);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="text-xs flex items-center gap-2 py-6" style={{ color: "var(--text-dim)" }}>
        <Loader2 className="w-3 h-3 animate-spin" /> Loading diagnostics…
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="stripe-admin-diagnostics">
      {/* Webhook health */}
      <div className="border rounded-2xl p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="serif text-2xl">Stripe Connect webhook health</div>
          <button onClick={load} className="btn-ghost !py-1 !px-2 text-xs" data-testid="diagnostics-refresh">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>

        {!health ? (
          <div className="text-xs" style={{ color: "var(--danger)" }}>Couldn&apos;t load health data.</div>
        ) : (
          <>
            <StatusPill
              ok={health.secret_configured}
              label="STRIPE_CONNECT_WEBHOOK_SECRET configured"
              hint="Without the secret, we accept unverified webhooks (sandbox only)."
              testid="webhook-secret-status"
            />
            <div className="mt-3 text-xs" style={{ color: "var(--text-dim)" }}>
              Last delivery: {health.last_seen_at || "—"}
            </div>

            {/* Setup card — only show if not all green */}
            {(!health.secret_configured || Object.values(health.critical_events_seen || {}).some((v) => !v)) && (
              <div
                className="mt-4 p-4 rounded-xl border"
                style={{ borderColor: "var(--accent)", background: "rgba(240,138,42,0.08)" }}
                data-testid="webhook-setup-card"
              >
                <div className="font-medium text-sm mb-2" style={{ color: "var(--accent)" }}>
                  Setup steps
                </div>
                <CopyField label="Webhook URL — paste into Stripe Dashboard" value={health.webhook_url} testid="webhook-url-copy" />
                <CopyField
                  label="Events to enable (one per line)"
                  value={(health.required_events || []).join("\n")}
                  testid="webhook-events-copy"
                  multiline
                />
                <ol className="text-xs space-y-1 list-decimal pl-5 mt-3" style={{ color: "var(--text-muted)" }}>
                  <li>
                    Stripe Dashboard → <strong>Developers → Webhooks → Add endpoint</strong>
                    <a href="https://dashboard.stripe.com/webhooks/create" target="_blank" rel="noopener noreferrer" className="ml-1.5 underline" style={{ color: "var(--accent)" }}>Open ↗</a>
                  </li>
                  <li>Toggle <strong>&ldquo;Listen to events on Connected accounts&rdquo;</strong> ON.</li>
                  <li>Paste the URL above and select the 5 events.</li>
                  <li>Copy the <strong>Signing secret</strong> (whsec_…).</li>
                  <li>
                    On Railway → Your Service → Variables, add:
                    <code className="block mt-1 px-2 py-1 rounded text-[11px]" style={{ background: "var(--bg-elev)", color: "var(--text)" }}>STRIPE_CONNECT_WEBHOOK_SECRET=whsec_xxx</code>
                  </li>
                  <li>Redeploy. Refresh this page in a few minutes — checkpoints below will turn green as Stripe delivers events.</li>
                </ol>
              </div>
            )}

            <div className="mt-4">
              <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Required Connect events (last 30 days)</div>
              <div className="space-y-1.5">
                {health.required_events.map((ev) => (
                  <div key={ev} className="flex items-center gap-2 text-sm" data-testid={`event-${ev}`}>
                    {health.critical_events_seen[ev] ? (
                      <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "rgb(46,160,67)" }} />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5" style={{ color: "var(--accent)" }} />
                    )}
                    <span style={{ color: "var(--text)" }}>{ev}</span>
                    <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                      {health.event_type_counts[ev] || 0} received
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {Object.keys(health.event_type_counts).length > 0 && (
              <details className="mt-4">
                <summary className="text-xs cursor-pointer" style={{ color: "var(--text-dim)" }}>Full event-type breakdown</summary>
                <div className="mt-2 grid sm:grid-cols-2 gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
                  {Object.entries(health.event_type_counts).map(([k, v]) => (
                    <div key={k}>{k}: <strong>{v}</strong></div>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>

      {/* Tax status */}
      <div className="border rounded-2xl p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="serif text-2xl mb-3">Stripe Tax</div>
        {!tax ? (
          <div className="text-xs" style={{ color: "var(--danger)" }}>Couldn&apos;t load.</div>
        ) : (
          <>
            <StatusPill
              ok={tax.enabled}
              label={tax.enabled ? `Active (${tax.behavior} pricing)` : "Off"}
              hint="Toggle via STRIPE_TAX_ENABLED env var after activating in Stripe dashboard."
              testid="tax-status"
            />
            {!tax.enabled && (
              <>
                <ol className="mt-3 text-xs space-y-1 list-decimal pl-5" style={{ color: "var(--text-muted)" }}>
                  {tax.activation_checklist.map((step, i) => <li key={i}>{step}</li>)}
                </ol>
                <CopyField
                  label="Railway env vars (paste once you've activated Stripe Tax)"
                  value={"STRIPE_TAX_ENABLED=true\nSTRIPE_TAX_BEHAVIOR=exclusive"}
                  testid="tax-env-copy"
                  multiline
                />
              </>
            )}
            {tax.enabled && report && (
              <div className="mt-4 grid sm:grid-cols-3 gap-3">
                <Kpi label="Tax collected (30d)" value={`$${(report.total_tax || 0).toFixed(2)}`} testid="tax-kpi-total" />
                <Kpi label="Paid bookings w/ tax" value={(report.total_paid_with_tax || 0).toString()} testid="tax-kpi-count" />
                <Kpi label="Jurisdictions" value={(report.by_jurisdiction || []).length.toString()} testid="tax-kpi-jur" />
              </div>
            )}
            {tax.enabled && (report?.by_jurisdiction || []).length > 0 && (
              <div className="mt-3 border rounded-xl overflow-hidden" style={{ borderColor: "var(--border)" }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                      <th className="text-left p-2">Country</th>
                      <th className="text-left p-2">Tax</th>
                      <th className="text-right p-2">Rate</th>
                      <th className="text-right p-2">Collected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_jurisdiction.map((j, i) => (
                      <tr key={i} className="border-b" style={{ borderColor: "var(--border)" }}>
                        <td className="p-2">{j.country || "—"}</td>
                        <td className="p-2">{j.name || "—"}</td>
                        <td className="p-2 text-right">{j.rate || "—"}%</td>
                        <td className="p-2 text-right">${(j.amount || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <a href={tax.dashboard_url} target="_blank" rel="noopener noreferrer" className="text-xs mt-3 inline-block" style={{ color: "var(--accent)" }}>
              Open Stripe Tax dashboard →
            </a>
          </>
        )}
      </div>
    </div>
  );
}

function StatusPill({ ok, label, hint, testid }) {
  return (
    <div className="flex items-center gap-2" data-testid={testid}>
      {ok ? (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium" style={{ background: "rgba(46,160,67,0.12)", color: "rgb(46,160,67)" }}>
          <CheckCircle2 className="w-3 h-3" /> {label}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium" style={{ background: "rgba(240,138,42,0.12)", color: "var(--accent)" }}>
          <AlertCircle className="w-3 h-3" /> {label}
        </span>
      )}
      {hint && <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>{hint}</span>}
    </div>
  );
}

function Kpi({ label, value, testid }) {
  return (
    <div className="border rounded-xl p-3" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }} data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-xl serif">{value}</div>
    </div>
  );
}

function CopyField({ label, value, testid, multiline = false }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <div className="mt-3" data-testid={testid}>
      <label className="text-[11px]" style={{ color: "var(--text-dim)" }}>{label}</label>
      <div className="mt-1 flex gap-2 items-start">
        {multiline ? (
          <pre
            className="flex-1 text-xs px-2.5 py-2 rounded-md border overflow-x-auto whitespace-pre"
            style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text)" }}
          >{value}</pre>
        ) : (
          <code
            className="flex-1 text-xs px-2.5 py-2 rounded-md border break-all"
            style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text)" }}
          >{value}</code>
        )}
        <button onClick={onCopy} className="btn-ghost !py-2 !px-2.5 shrink-0" title="Copy">
          {copied ? <Check className="w-3.5 h-3.5" style={{ color: "rgb(46,160,67)" }} /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}
