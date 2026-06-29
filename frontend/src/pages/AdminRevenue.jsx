import { useEffect, useMemo, useState } from "react";
import { Download, DollarSign, TrendingUp, Calendar } from "lucide-react";
import api from "@/lib/api";
import { formatMoney } from "@/lib/currencies";

/**
 * Admin Revenue Dashboard.
 *
 * Reconstructs the per-booking fee split so admin can see their platform
 * cut without leaving Allsale (Stripe natively doesn't surface it under
 * the current "platform-keeps-100%-then-manual-payout" model).
 *
 * Columns:
 *   Paid at · Event · Buyer · Qty · Gross · Stripe fee · Organizer share · YOUR CUT
 *
 * Filters: date range. Pagination: 200 rows per page.
 * Export: client-side CSV of the current filtered slice.
 */
export default function AdminRevenue() {
  const [data, setData] = useState({ items: [], totals: null, currency: "NZD", mixed_currencies: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 200;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setError(null);
      try {
        const { data: d } = await api.get("/admin/revenue", {
          params: { start: start || undefined, end: end || undefined, limit, offset },
        });
        if (!cancelled) setData(d);
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || "Failed to load revenue");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [start, end, offset]);

  const exportCsv = () => {
    const headers = [
      "paid_at", "booking_id", "event_title", "organizer_name", "buyer_email",
      "quantity", "currency", "gross", "stripe_fee", "platform_fee", "organizer_share",
      "absorb_fees", "stripe_session_id",
    ];
    const rows = data.items.map((r) => headers.map((h) => {
      const v = r[h];
      const s = v == null ? "" : String(v);
      // CSV-escape: wrap in quotes if contains comma/quote/newline
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(","));
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `allsale-revenue-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const kpis = useMemo(() => {
    if (!data.totals) return [];
    const cur = data.currency;
    return [
      { label: "Tickets sold", value: data.totals.count, fmt: (v) => v.toLocaleString() },
      { label: "Gross collected (buyer paid)", value: data.totals.gross, fmt: (v) => formatMoney(v, cur) },
      { label: "Stripe processing fees", value: data.totals.stripe_fees, fmt: (v) => formatMoney(v, cur), accent: "#7A1410" },
      { label: "Organizer share (you'll pay out)", value: data.totals.organizer_share, fmt: (v) => formatMoney(v, cur), accent: "#374151" },
      { label: "YOUR PLATFORM CUT", value: data.totals.platform_fees, fmt: (v) => formatMoney(v, cur), accent: "var(--accent)", highlight: true },
    ];
  }, [data]);

  return (
    <div className="max-w-7xl mx-auto px-6 py-8" data-testid="admin-revenue-page">
      <div className="flex items-end justify-between mb-6 flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-1" style={{ color: "var(--accent)" }}>Admin · Revenue</div>
          <h1 className="serif text-3xl">Platform-fee P&amp;L</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Per-booking breakdown of what each buyer paid, what Stripe took,
            what you owe the organizer, and what stays with Allsale.
          </p>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          disabled={!data.items.length}
          className="btn-secondary inline-flex items-center gap-2"
          data-testid="revenue-export-csv"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
      </div>

      {/* Date filter */}
      <div className="flex items-end gap-3 mb-6 flex-wrap" data-testid="revenue-filters">
        <div>
          <label htmlFor="rev-start" className="block text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>From</label>
          <input
            id="rev-start"
            type="date"
            value={start}
            onChange={(e) => { setStart(e.target.value); setOffset(0); }}
            className="!py-2"
            data-testid="revenue-filter-start"
          />
        </div>
        <div>
          <label htmlFor="rev-end" className="block text-xs uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>To</label>
          <input
            id="rev-end"
            type="date"
            value={end}
            onChange={(e) => { setEnd(e.target.value); setOffset(0); }}
            className="!py-2"
            data-testid="revenue-filter-end"
          />
        </div>
        {(start || end) && (
          <button
            type="button"
            onClick={() => { setStart(""); setEnd(""); setOffset(0); }}
            className="text-sm underline opacity-80 hover:opacity-100"
            data-testid="revenue-filter-clear"
          >
            Clear
          </button>
        )}
        {data.mixed_currencies && (
          <span className="ml-auto text-xs px-2 py-1 rounded-full" style={{ background: "#FFF4F2", color: "#7A1410", border: "1px solid #E84B3C" }} title="Mixed currencies in this slice — KPI cards use the majority currency. Per-row currency is shown in the table.">
            Mixed currencies
          </span>
        )}
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6" data-testid="revenue-kpis">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="rounded-2xl border p-4"
            style={{
              borderColor: k.highlight ? "var(--accent)" : "var(--border)",
              background: k.highlight ? "#FFF9F0" : "var(--bg-card)",
            }}
            data-testid={`revenue-kpi-${k.label.toLowerCase().replace(/[^a-z]/g, "-")}`}
          >
            <div className="text-[10px] uppercase tracking-widest" style={{ color: k.highlight ? "var(--accent)" : "var(--text-muted)" }}>
              {k.label}
            </div>
            <div className="serif text-2xl mt-1" style={{ color: k.accent || "var(--text)" }}>
              {data.totals ? k.fmt(k.value) : "—"}
            </div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-2xl border overflow-x-auto" style={{ borderColor: "var(--border)" }}>
        {loading ? (
          <div className="p-10 text-center" style={{ color: "var(--text-muted)" }}>Loading…</div>
        ) : error ? (
          <div className="p-10 text-center" style={{ color: "#7A1410" }} data-testid="revenue-error">{error}</div>
        ) : data.items.length === 0 ? (
          <div className="p-10 text-center" style={{ color: "var(--text-muted)" }} data-testid="revenue-empty">
            No paid bookings {start || end ? "in this date range" : "yet"}.
          </div>
        ) : (
          <table className="w-full text-sm" data-testid="revenue-table">
            <thead>
              <tr className="text-left" style={{ background: "var(--bg-card)", color: "var(--text-muted)" }}>
                <th className="px-3 py-2 font-medium">Paid</th>
                <th className="px-3 py-2 font-medium">Event</th>
                <th className="px-3 py-2 font-medium">Buyer</th>
                <th className="px-3 py-2 font-medium text-right">Qty</th>
                <th className="px-3 py-2 font-medium text-right">Gross</th>
                <th className="px-3 py-2 font-medium text-right">Stripe fee</th>
                <th className="px-3 py-2 font-medium text-right">Organizer</th>
                <th className="px-3 py-2 font-medium text-right" style={{ color: "var(--accent)" }}>Your cut</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr
                  key={r.booking_id}
                  className="border-t"
                  style={{ borderColor: "var(--border)" }}
                  data-testid={`revenue-row-${r.booking_id}`}
                >
                  <td className="px-3 py-2 text-xs whitespace-nowrap" title={r.paid_at}>{(r.paid_at || "").slice(0, 10)}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium truncate max-w-[260px]" title={r.event_title}>{r.event_title}</div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>{r.organizer_name}</div>
                  </td>
                  <td className="px-3 py-2 text-xs truncate max-w-[180px]" title={r.buyer_email}>{r.buyer_email || "—"}</td>
                  <td className="px-3 py-2 text-right">{r.quantity}</td>
                  <td className="px-3 py-2 text-right font-mono whitespace-nowrap">{formatMoney(r.gross, r.currency)}</td>
                  <td className="px-3 py-2 text-right font-mono whitespace-nowrap" style={{ color: "#7A1410" }}>
                    −{formatMoney(r.stripe_fee, r.currency)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono whitespace-nowrap" style={{ color: "#374151" }}>
                    {formatMoney(r.organizer_share, r.currency)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold whitespace-nowrap" style={{ color: "var(--accent)" }}>
                    {formatMoney(r.platform_fee, r.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4 text-sm" style={{ color: "var(--text-muted)" }}>
        <span data-testid="revenue-page-info">
          Showing {data.items.length} bookings {offset > 0 && `(from row ${offset + 1})`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0 || loading}
            className="btn-secondary disabled:opacity-50"
            data-testid="revenue-prev-page"
          >
            ← Prev
          </button>
          <button
            type="button"
            onClick={() => setOffset(offset + limit)}
            disabled={data.items.length < limit || loading}
            className="btn-secondary disabled:opacity-50"
            data-testid="revenue-next-page"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
