import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ArrowLeft, Wallet, TrendingUp, Clock, CheckCircle2, XCircle, BanknoteIcon, FileText } from "lucide-react";
import { toast } from "sonner";

const STATUS_META = {
  requested: { label: "Requested", color: "var(--warn)", bg: "rgba(251,191,36,0.12)", icon: Clock },
  paid: { label: "Paid", color: "var(--success)", bg: "rgba(52,211,153,0.12)", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "var(--danger)", bg: "rgba(239,68,68,0.12)", icon: XCircle },
};

function money(v, currency = "USD") {
  return `$${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }); } catch { return s; }
}

export default function OrganizerPayouts() {
  const { user } = useAuth();
  const [balance, setBalance] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [requesting, setRequesting] = useState(false);
  const [notes, setNotes] = useState("");

  const load = async () => {
    try {
      const [b, p] = await Promise.all([
        api.get("/organizer/payouts/balance"),
        api.get("/organizer/payouts"),
      ]);
      setBalance(b.data);
      setPayouts(p.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load payouts");
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const requestPayout = async () => {
    if (requesting) return;
    if (!balance?.available?.net) {
      toast.error("No balance available to request");
      return;
    }
    setRequesting(true);
    try {
      const { data } = await api.post("/organizer/payouts/request", { notes: notes || null });
      toast.success(`Payout ${data.payout_id} submitted for ${money(data.net_amount)}`);
      setNotes("");
      await load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not submit payout");
    } finally { setRequesting(false); }
  };

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }

  const avail = balance?.available;
  const settings = balance?.settings;

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      <Link to="/organizer" className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: "var(--text-muted)" }} data-testid="back-to-organizer">
        <ArrowLeft className="w-4 h-4" /> Back to dashboard
      </Link>

      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Earnings</div>
        <h1 className="serif text-5xl">Payouts</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Net = gross − platform commission ({settings?.commission_percent ?? 8}%) − ${settings?.commission_flat_fee_per_ticket ?? 0.5}/ticket processing fee.
        </p>
      </div>

      {/* Balance + Request card */}
      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-5 mb-12">
        <div className="border rounded-2xl p-8" style={{ borderColor: "var(--border)", background: "linear-gradient(140deg, rgba(255,79,0,0.08), rgba(255,79,0,0) 60%), var(--bg-card)" }}>
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Available to request</div>
            <Wallet className="w-5 h-5" style={{ color: "var(--accent)" }} />
          </div>
          <div className="serif text-6xl mb-1" data-testid="available-net" style={{ color: "var(--text)" }}>
            {money(avail?.net || 0)}
          </div>
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>
            from {avail?.bookings || 0} bookings · {avail?.tickets || 0} tickets
          </div>

          <div className="mt-8 grid grid-cols-3 gap-4 text-sm">
            <Mini label="Gross" value={money(avail?.gross || 0)} />
            <Mini label={`Commission (${settings?.commission_percent ?? 8}%)`} value={`− ${money(avail?.commission || 0)}`} accent="var(--danger)" />
            <Mini label={`Processing (${avail?.tickets || 0} × $${settings?.commission_flat_fee_per_ticket ?? 0.5})`} value={`− ${money(avail?.flat_fees || 0)}`} accent="var(--danger)" />
          </div>
        </div>

        <div className="border rounded-2xl p-7" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Request payout</div>
          <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
            Submit a payout request — an admin will wire funds and mark it paid.
          </p>
          <textarea
            placeholder="Notes for admin (optional) — e.g. preferred wire account"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full mb-4"
            data-testid="payout-notes-input"
          />
          <button
            onClick={requestPayout}
            disabled={requesting || !avail?.net}
            className="btn-primary w-full justify-center"
            data-testid="request-payout-btn"
          >
            <BanknoteIcon className="w-4 h-4" /> {requesting ? "Submitting…" : `Request ${money(avail?.net || 0)}`}
          </button>
          <div className="mt-5 pt-5 border-t flex justify-between text-sm" style={{ borderColor: "var(--border)" }}>
            <span style={{ color: "var(--text-muted)" }}>Lifetime paid</span>
            <span data-testid="lifetime-paid" style={{ color: "var(--success)" }}>{money(balance?.lifetime_paid || 0)}</span>
          </div>
          {balance?.pending > 0 && (
            <div className="flex justify-between text-sm mt-1">
              <span style={{ color: "var(--text-muted)" }}>Pending</span>
              <span style={{ color: "var(--warn)" }}>{money(balance.pending)}</span>
            </div>
          )}
        </div>
      </div>

      {/* History */}
      <div className="mb-4 flex items-end justify-between">
        <h2 className="serif text-2xl">Payout history</h2>
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>{payouts.length} {payouts.length === 1 ? "payout" : "payouts"}</div>
      </div>
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        {payouts.length === 0 ? (
          <div className="p-12 text-center" style={{ color: "var(--text-dim)" }}>
            <FileText className="w-10 h-10 mx-auto mb-3 opacity-50" />
            No payouts yet — request your first one above.
          </div>
        ) : (
          <table className="w-full text-sm" data-testid="payouts-history-table">
            <thead>
              <tr style={{ background: "var(--bg)", color: "var(--text-muted)" }}>
                <th className="text-left px-5 py-3 text-xs uppercase tracking-widest font-medium">Reference</th>
                <th className="text-left px-5 py-3 text-xs uppercase tracking-widest font-medium">Requested</th>
                <th className="text-left px-5 py-3 text-xs uppercase tracking-widest font-medium">Period</th>
                <th className="text-right px-5 py-3 text-xs uppercase tracking-widest font-medium">Gross</th>
                <th className="text-right px-5 py-3 text-xs uppercase tracking-widest font-medium">Fees</th>
                <th className="text-right px-5 py-3 text-xs uppercase tracking-widest font-medium">Net</th>
                <th className="text-left px-5 py-3 text-xs uppercase tracking-widest font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {payouts.map((p) => {
                const meta = STATUS_META[p.status] || { label: p.status, color: "var(--text-muted)" };
                const Icon = meta.icon || TrendingUp;
                return (
                  <tr key={p.payout_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`payout-row-${p.payout_id}`}>
                    <td className="px-5 py-4 font-mono text-xs">{p.payout_id}</td>
                    <td className="px-5 py-4" style={{ color: "var(--text-muted)" }}>{fmtDate(p.requested_at)}</td>
                    <td className="px-5 py-4" style={{ color: "var(--text-muted)" }}>{fmtDate(p.period_start)} → {fmtDate(p.period_end)}</td>
                    <td className="px-5 py-4 text-right">{money(p.gross)}</td>
                    <td className="px-5 py-4 text-right" style={{ color: "var(--text-muted)" }}>
                      − {money((p.commission || 0) + (p.flat_fees || 0))}
                    </td>
                    <td className="px-5 py-4 text-right font-semibold" style={{ color: "var(--text)" }}>{money(p.net_amount)}</td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ color: meta.color, background: meta.bg }}>
                        <Icon className="w-3.5 h-3.5" /> {meta.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Mini({ label, value, accent }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-base" style={{ color: accent || "var(--text)" }}>{value}</div>
    </div>
  );
}
