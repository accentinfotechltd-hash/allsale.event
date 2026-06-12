import { useEffect, useState } from "react";
import { Banknote, Clock, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import api from "@/lib/api";

/**
 * Organizer-facing per-event payout status.
 *
 * Pulls /api/organizer/event-payouts and renders a table:
 *   – PAST events: payout status (Paid / Failed / Pending hold)
 *     - "Pending hold" shows a "Hold ends in X days" countdown until the
 *       5-day hold window elapses; after that the next scheduler tick
 *       (hourly) will trigger the Stripe Transfer automatically.
 *   – UPCOMING events: a muted "Upcoming" pill so organizers see the row but
 *     understand no payout has been queued yet.
 *
 * Hidden entirely if the user has no events.
 */
export default function OrganizerPayoutsPanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/organizer/event-payouts");
        setData(r.data);
      } catch {
        setData({ items: [], platform_fee_bps: 500, hold_hours: 120 });
      }
    })();
  }, []);

  if (!data) {
    return (
      <div
        className="mt-10 border rounded-2xl p-6 flex items-center gap-3"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
        data-testid="payouts-panel-loading"
      >
        <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--text-dim)" }} />
        <span className="text-sm" style={{ color: "var(--text-dim)" }}>Loading payouts…</span>
      </div>
    );
  }

  if (!data.items || data.items.length === 0) return null;

  const feePct = ((data.platform_fee_bps || 0) / 100).toFixed(1);
  const holdDays = Math.round((data.hold_hours || 120) / 24);

  return (
    <div
      className="mt-10 border rounded-2xl overflow-hidden"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="organizer-payouts-panel"
    >
      <div className="p-5 border-b flex items-center justify-between flex-wrap gap-2" style={{ borderColor: "var(--border)" }}>
        <div>
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Payouts</div>
          <div className="serif text-2xl flex items-center gap-2"><Banknote className="w-5 h-5" style={{ color: "var(--accent)" }} /> Per-event payouts</div>
        </div>
        <div className="text-xs text-right" style={{ color: "var(--text-dim)" }}>
          Platform fee: <b style={{ color: "var(--text-muted)" }}>{feePct}%</b> · Hold: <b style={{ color: "var(--text-muted)" }}>{holdDays} days after event ends</b>
        </div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            <th className="text-left p-4">Event</th>
            <th className="text-left p-4">Date</th>
            <th className="text-left p-4">Status</th>
            <th className="text-right p-4">Net payout</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((it) => <Row key={it.event_id} it={it} />)}
        </tbody>
      </table>
    </div>
  );
}

function Row({ it }) {
  const eventDate = it.date ? new Date(it.date) : null;
  const dateStr = eventDate
    ? eventDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "—";
  // Backend already computed remaining hold hours relative to UTC now.
  // 0 means the 5-day hold window has elapsed — the next scheduler tick will pay it.
  const holdElapsed = it.hold_remaining_hours === 0;

  const { pill, amountText } = pickRowPresentation(it, holdElapsed);

  return (
    <tr className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`payout-row-${it.event_id}`}>
      <td className="p-4">
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>{it.title}</span>
      </td>
      <td className="p-4" style={{ color: "var(--text-muted)" }}>{dateStr}</td>
      <td className="p-4">{pill}</td>
      <td className="p-4 text-right">{amountText || <span style={{ color: "var(--text-dim)" }}>—</span>}</td>
    </tr>
  );
}

function pickRowPresentation(it, hasEnded) {
  const isSplit = Array.isArray(it.payout_recipients) && it.payout_recipients.length > 1;
  const splitBadge = isSplit ? (
    <span
      className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px]"
      style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }}
      title={`Revenue split between ${it.payout_recipients.length} recipients`}
    >
      Split × {it.payout_recipients.length}
    </span>
  ) : null;
  if (it.payout_status === "paid") {
    return {
      pill: (
        <span className="inline-flex items-center gap-1">
          <span
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
            style={{ background: "rgba(46,160,67,0.12)", color: "rgb(46,160,67)" }}
            data-testid={`payout-status-paid-${it.event_id}`}
          >
            <CheckCircle2 className="w-3 h-3" /> Paid out
          </span>
          {splitBadge}
        </span>
      ),
      amountText: (
        <span style={{ color: "rgb(46,160,67)", fontWeight: 500 }}>
          {it.currency} {(it.payout_amount || 0).toFixed(2)}
        </span>
      ),
    };
  }
  if (it.payout_status === "partial") {
    const paidRcpts = (it.payout_recipients || []).filter((r) => r.status === "paid").length;
    const totalRcpts = (it.payout_recipients || []).length;
    return {
      pill: (
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{ background: "rgba(240,138,42,0.12)", color: "var(--accent)" }}
          data-testid={`payout-status-partial-${it.event_id}`}
          title="Some recipients paid; rest pending or failed"
        >
          <AlertCircle className="w-3 h-3" /> Partial — {paidRcpts}/{totalRcpts} paid
        </span>
      ),
      amountText: (
        <span style={{ color: "var(--accent)", fontWeight: 500 }}>
          {it.currency} {(it.payout_amount || 0).toFixed(2)}
        </span>
      ),
    };
  }
  if (it.payout_status === "failed") {
    return {
      pill: (
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{ background: "rgba(198,40,40,0.12)", color: "rgb(198,40,40)" }}
          title={it.payout_error || ""}
          data-testid={`payout-status-failed-${it.event_id}`}
        >
          <AlertCircle className="w-3 h-3" /> Payout failed — contact support
        </span>
      ),
      amountText: null,
    };
  }
  if (it.payout_status === "no_revenue") {
    return {
      pill: (
        <span
          className="inline-flex items-center px-2.5 py-1 rounded-full text-xs"
          style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }}
          data-testid={`payout-status-noreveue-${it.event_id}`}
        >
          No sales
        </span>
      ),
      amountText: null,
    };
  }
  if (hasEnded) {
    return {
      pill: (
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
          style={{ background: "rgba(240,138,42,0.12)", color: "var(--accent)" }}
          data-testid={`payout-status-pending-${it.event_id}`}
        >
          <Clock className="w-3 h-3" /> Processing soon
        </span>
      ),
      amountText: null,
    };
  }
  if (it.hold_remaining_hours !== null && it.hold_remaining_hours > 0) {
    const days = Math.ceil(it.hold_remaining_hours / 24);
    return {
      pill: (
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs"
          style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}
          data-testid={`payout-status-hold-${it.event_id}`}
        >
          <Clock className="w-3 h-3" /> Payout in {days} day{days === 1 ? "" : "s"}
        </span>
      ),
      amountText: null,
    };
  }
  return {
    pill: (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs" style={{ color: "var(--text-dim)" }}>
        —
      </span>
    ),
    amountText: null,
  };
}
