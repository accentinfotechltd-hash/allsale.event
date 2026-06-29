import { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { Loader2, CheckCircle2, AlertTriangle, XCircle, Mail, Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_META = {
  connected: { dot: "🟢", label: "Connected", chip: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  onboarding_incomplete: { dot: "🟡", label: "Onboarding", chip: "bg-amber-50 text-amber-700 border-amber-200", icon: AlertTriangle },
  not_connected: { dot: "⚪", label: "Manual payouts", chip: "bg-slate-50 text-slate-600 border-slate-200", icon: XCircle },
};

const CURRENCY_SYMBOL = { NZD: "NZ$", AUD: "A$", USD: "US$", GBP: "£", EUR: "€", INR: "₹", AED: "د.إ" };
const fmtMoney = (amt, ccy) => {
  const sym = CURRENCY_SYMBOL[ccy] || `${ccy} `;
  return `${sym}${(amt || 0).toFixed(2)}`;
};

const fmtDate = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso.slice(0, 10); }
};

export default function AdminStripeConnectStatusTab() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ items: [], summary: { total: 0, connected: 0, onboarding: 0, not_connected: 0 } });
  const [filter, setFilter] = useState("all"); // all | not_connected | onboarding_incomplete | connected
  const [busyIds, setBusyIds] = useState(new Set());
  const [blasting, setBlasting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("auth_token");
      const r = await axios.get(`${API}/admin/stripe-connect-status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load Connect status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filteredItems = useMemo(() => {
    if (filter === "all") return data.items;
    return data.items.filter((x) => x.status === filter);
  }, [data.items, filter]);

  const totalUncollectedFromRevenue = useMemo(() => {
    // Revenue from organizers who are NOT connected — i.e., money that
    // landed on Allsale's master account because there was no destination
    // charge. Useful headline metric.
    return data.items
      .filter((x) => x.status !== "connected")
      .reduce((acc, x) => acc + (x.lifetime_revenue || 0), 0);
  }, [data.items]);

  const remindOne = async (userId) => {
    setBusyIds((s) => new Set(s).add(userId));
    try {
      const token = localStorage.getItem("auth_token");
      const r = await axios.post(`${API}/admin/stripe-connect-status/remind`,
        { user_ids: [userId] },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`Sent ${r.data.sent} invite${r.data.sent === 1 ? "" : "s"}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send reminder");
    } finally {
      setBusyIds((s) => { const n = new Set(s); n.delete(userId); return n; });
    }
  };

  const remindAll = async () => {
    if (!confirm("Send a friendly 'try Stripe Connect for faster payouts' invite to all organizers currently on manual payouts?")) return;
    setBlasting(true);
    try {
      const token = localStorage.getItem("auth_token");
      const r = await axios.post(`${API}/admin/stripe-connect-status/remind`,
        { user_ids: null },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`Queued ${r.data.sent} invite${r.data.sent === 1 ? "" : "s"} (${r.data.skipped} skipped)`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to blast reminders");
    } finally {
      setBlasting(false);
    }
  };

  const exportCsv = () => {
    const headers = ["Status", "Name", "Email", "Phone", "Events", "Bookings", "Tickets", "Lifetime revenue", "Currency", "Platform fees collected", "Stripe account", "Last paid", "Last reminder sent"];
    const rows = filteredItems.map((x) => [
      STATUS_META[x.status]?.label || x.status,
      x.name || "",
      x.email || "",
      x.phone || "",
      x.events_count,
      x.bookings_count,
      x.tickets_sold,
      (x.lifetime_revenue || 0).toFixed(2),
      x.currency,
      (x.platform_fees_collected || 0).toFixed(2),
      x.stripe_account_id || "",
      fmtDate(x.last_paid_at),
      fmtDate(x.last_reminder_sent_at),
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `stripe-connect-status-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
      </div>
    );
  }

  return (
    <div data-testid="admin-stripe-connect-status-tab" className="space-y-6">
      {/* Header + KPI cards */}
      <div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-slate-900">Stripe Connect adoption</h2>
            <p className="text-sm text-slate-600 mt-1 max-w-3xl">
              Stripe Connect is an <b>optional upgrade</b> for organizers — they get instant payouts directly to their own Stripe balance.
              Organizers who don&apos;t connect continue to be paid via your existing manual payout flow (no change needed).
              When an organizer DOES connect, future ticket sales appear in Stripe&apos;s native <b>&quot;Collected fees&quot;</b> tab so you can see your platform cut without opening Allsale.
            </p>
          </div>
          <button
            data-testid="connect-status-refresh"
            onClick={load}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-sm font-medium text-slate-700"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
          <KpiCard label="Organizers total" value={data.summary.total} testid="kpi-total" />
          <KpiCard label="🟢 Connected" value={data.summary.connected} accent="emerald" testid="kpi-connected" />
          <KpiCard label="🟡 Onboarding" value={data.summary.onboarding} accent="amber" testid="kpi-onboarding" />
          <KpiCard label="⚪ Manual payouts" value={data.summary.not_connected} accent="slate" testid="kpi-not-connected" />
        </div>

        {totalUncollectedFromRevenue > 0 && (
          <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900" data-testid="uncollected-banner">
            <b>NZ${totalUncollectedFromRevenue.toFixed(2)}</b> in revenue has been processed via manual payouts (Allsale collects, then bank-transfers to organizers). That&apos;s the default — it works fine and will continue.
            <span className="block text-xs mt-1 opacity-80">If any of these organizers want faster (instant) payouts straight to their Stripe, send them an invite below.</span>
          </div>
        )}
      </div>

      {/* Filter + actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 text-sm">
          {[
            { id: "all", label: "All" },
            { id: "not_connected", label: "⚪ Manual payouts" },
            { id: "onboarding_incomplete", label: "🟡 Onboarding" },
            { id: "connected", label: "🟢 Connected" },
          ].map((b) => (
            <button
              key={b.id}
              data-testid={`connect-status-filter-${b.id}`}
              onClick={() => setFilter(b.id)}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                filter === b.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            data-testid="connect-status-export-csv"
            onClick={exportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-sm font-medium text-slate-700"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button
            data-testid="connect-status-remind-all"
            onClick={remindAll}
            disabled={blasting || data.summary.not_connected === 0}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:bg-slate-300 text-white text-sm font-medium"
          >
            {blasting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
            Invite {data.summary.not_connected} manual organizers to try Stripe
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr className="text-left text-slate-600 uppercase text-xs tracking-wider">
                <th className="p-3 font-semibold">Status</th>
                <th className="p-3 font-semibold">Organizer</th>
                <th className="p-3 font-semibold text-right">Events</th>
                <th className="p-3 font-semibold text-right">Bookings</th>
                <th className="p-3 font-semibold text-right">Lifetime revenue</th>
                <th className="p-3 font-semibold text-right">Platform fees</th>
                <th className="p-3 font-semibold">Last paid</th>
                <th className="p-3 font-semibold">Last invite sent</th>
                <th className="p-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.length === 0 ? (
                <tr><td colSpan={9} className="p-8 text-center text-slate-500">No organizers match this filter.</td></tr>
              ) : filteredItems.map((row) => {
                const meta = STATUS_META[row.status] || STATUS_META.not_connected;
                const Icon = meta.icon;
                const isBusy = busyIds.has(row.user_id);
                return (
                  <tr key={row.user_id} className="hover:bg-slate-50" data-testid={`organizer-row-${row.user_id}`}>
                    <td className="p-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full border text-xs font-medium ${meta.chip}`}>
                        <Icon className="w-3.5 h-3.5" /> {meta.label}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="font-medium text-slate-900">{row.name}</div>
                      <div className="text-xs text-slate-500">{row.email}{row.phone ? ` · ${row.phone}` : ""}</div>
                    </td>
                    <td className="p-3 text-right tabular-nums">{row.events_count}</td>
                    <td className="p-3 text-right tabular-nums">{row.bookings_count}</td>
                    <td className="p-3 text-right tabular-nums font-medium text-slate-900">
                      {fmtMoney(row.lifetime_revenue, row.currency)}
                    </td>
                    <td className="p-3 text-right tabular-nums text-emerald-700">
                      {fmtMoney(row.platform_fees_collected, row.currency)}
                    </td>
                    <td className="p-3 text-xs text-slate-600">{fmtDate(row.last_paid_at)}</td>
                    <td className="p-3 text-xs text-slate-600">{fmtDate(row.last_reminder_sent_at)}</td>
                    <td className="p-3 text-right">
                      {row.status === "connected" ? (
                        <span className="text-xs text-slate-400">—</span>
                      ) : (
                        <button
                          data-testid={`remind-organizer-${row.user_id}`}
                          onClick={() => remindOne(row.user_id)}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-slate-200 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 disabled:opacity-50"
                        >
                          {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />}
                          {row.last_reminder_sent_at ? "Invite again" : "Invite to Stripe"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ label, value, accent, testid }) {
  const accentMap = {
    emerald: "border-emerald-200 bg-emerald-50/40",
    amber: "border-amber-200 bg-amber-50/40",
    rose: "border-rose-200 bg-rose-50/40",
    slate: "border-slate-300 bg-slate-50/60",
  };
  return (
    <div
      data-testid={testid}
      className={`rounded-xl border p-4 ${accentMap[accent] || "border-slate-200 bg-white"}`}
    >
      <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">{label}</div>
      <div className="text-2xl font-semibold text-slate-900 mt-1 tabular-nums">{value}</div>
    </div>
  );
}
