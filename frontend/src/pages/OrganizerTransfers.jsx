import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, Banknote, ExternalLink, ArrowDownRight, ArrowUpRight, Loader2,
} from "lucide-react";
import api from "@/lib/api";
import { formatMoney } from "@/lib/currencies";

/**
 * Organizer transfer history — paid-out events + any refund reversals.
 *
 * Each row is one entry in `connect_payouts` for the calling organizer. We
 * hydrate the event title server-side. The header shows running totals so
 * the organizer sees "you've been paid $X net so far" at a glance.
 */
export default function OrganizerTransfers() {
  const nav = useNavigate();
  const [data, setData] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/organizer/stripe/transfers");
        setData(r.data);
      } catch {
        setData({ items: [], total_paid: 0, total_reversed: 0, net_settled: 0 });
      }
    })();
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      <button
        type="button"
        onClick={() => nav(-1)}
        className="text-sm mb-6 inline-flex items-center gap-1"
        style={{ color: "var(--text-dim)" }}
        data-testid="transfers-back-btn"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>
      <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Stripe</div>
      <h1 className="serif text-4xl mb-2">Transfer history</h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
        Every payout we&apos;ve sent to your Stripe Connect account, plus any reversals from refunded bookings. Funds typically reach your bank 2-7 business days after the transfer date depending on Stripe&apos;s payout schedule.
      </p>

      {data === null ? (
        <div className="border rounded-2xl p-10 text-center" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          <Loader2 className="w-5 h-5 animate-spin inline" style={{ color: "var(--text-dim)" }} />
        </div>
      ) : (
        <>
          {/* Totals */}
          <div className="grid sm:grid-cols-3 gap-3 mb-8">
            <Card label="Paid out" value={formatMoney(data.total_paid || 0, "NZD")} icon={<ArrowDownRight className="w-4 h-4" style={{ color: "rgb(46,160,67)" }} />} />
            <Card label="Reversed (refunds)" value={formatMoney(data.total_reversed || 0, "NZD")} icon={<ArrowUpRight className="w-4 h-4" style={{ color: "rgb(198,40,40)" }} />} />
            <Card label="Net settled" value={formatMoney(data.net_settled || 0, "NZD")} icon={<Banknote className="w-4 h-4" style={{ color: "var(--accent)" }} />} accent />
          </div>

          {/* Table */}
          <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            {data.items.length === 0 ? (
              <div className="p-10 text-center text-sm" style={{ color: "var(--text-dim)" }} data-testid="transfers-empty">
                No transfers yet. Once your first event completes its 5-day hold, a payout will appear here automatically.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                    <th className="text-left p-4">Event</th>
                    <th className="text-left p-4">Type</th>
                    <th className="text-left p-4">Date</th>
                    <th className="text-right p-4">Amount</th>
                    <th className="text-left p-4 hidden md:table-cell">Stripe ref</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => <TransferRow key={p.payout_id} p={p} />)}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Card({ label, value, icon, accent }) {
  return (
    <div
      className="p-4 rounded-2xl border"
      style={{
        borderColor: accent ? "var(--accent)" : "var(--border)",
        background: accent ? "var(--accent-soft)" : "var(--bg-card)",
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        {icon}
        <span className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</span>
      </div>
      <div className="serif text-3xl">{value}</div>
    </div>
  );
}

function TransferRow({ p }) {
  const isReversal = p.status === "reversed";
  const amount = p.net_amount || 0;
  const cur = (p.currency || "NZD").toUpperCase();
  return (
    <tr className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`transfer-row-${p.payout_id}`}>
      <td className="p-4">
        <div className="font-medium text-sm">{p.event_title || "Event"}</div>
        {p.event_date && (
          <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
            {new Date(p.event_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </div>
        )}
      </td>
      <td className="p-4">
        {isReversal ? (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
            style={{ background: "rgba(198,40,40,0.12)", color: "rgb(198,40,40)" }}
          >
            <ArrowUpRight className="w-3 h-3" /> Reversal
          </span>
        ) : p.status === "paid" ? (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
            style={{ background: "rgba(46,160,67,0.12)", color: "rgb(46,160,67)" }}
          >
            <ArrowDownRight className="w-3 h-3" /> Payout
          </span>
        ) : (
          <span
            className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest"
            style={{ background: "rgba(198,40,40,0.12)", color: "rgb(198,40,40)" }}
          >
            Failed
          </span>
        )}
      </td>
      <td className="p-4" style={{ color: "var(--text-muted)" }}>
        {p.created_at ? new Date(p.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
      </td>
      <td
        className="p-4 text-right font-medium"
        style={{ color: isReversal ? "rgb(198,40,40)" : "rgb(46,160,67)" }}
      >
        {isReversal ? "−" : ""}{formatMoney(Math.abs(amount), cur)}
      </td>
      <td className="p-4 hidden md:table-cell">
        <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
          {p.stripe_reversal_id || p.stripe_transfer_id || "—"}
        </span>
      </td>
    </tr>
  );
}
