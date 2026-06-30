import { useEffect, useMemo, useState, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ArrowLeft, Download, Search, Users, X, ExternalLink, CheckCircle2 } from "lucide-react";
import { formatMoney } from "@/lib/currencies";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const PAGE_SIZE = 100;

export default function OrganizerBuyers() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  // Filters — `event_id` query param seeds the dropdown so the "Buyers"
  // button on each event row deep-links straight to a pre-filtered view.
  const [eventId, setEventId] = useState(searchParams.get("event_id") || "");
  const [status, setStatus] = useState("paid");
  const [q, setQ] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [offset, setOffset] = useState(0);

  // Keep the URL in sync so refreshes / share-links preserve the selected event.
  useEffect(() => {
    setSearchParams(eventId ? { event_id: eventId } : {}, { replace: true });
  }, [eventId, setSearchParams]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset, status };
      if (eventId) params.event_id = eventId;
      if (q.trim()) params.q = q.trim();
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const { data } = await api.get("/organizer/buyers", { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setEvents(data.events || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load buyers");
    } finally {
      setLoading(false);
    }
  }, [eventId, status, q, fromDate, toDate, offset]);

  useEffect(() => { load(); }, [load]);

  // Reset offset when filters change
  useEffect(() => { setOffset(0); }, [eventId, status, q, fromDate, toDate]);

  const clearFilters = () => {
    setEventId(""); setStatus("paid"); setQ(""); setFromDate(""); setToDate("");
  };

  const downloadCsv = async () => {
    try {
      const token = localStorage.getItem("aura_token");
      const params = new URLSearchParams();
      if (eventId) params.set("event_id", eventId);
      if (status) params.set("status", status);
      if (q.trim()) params.set("q", q.trim());
      if (fromDate) params.set("from_date", fromDate);
      if (toDate) params.set("to_date", toDate);
      const r = await fetch(`${BACKEND}/api/organizer/buyers.csv?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!r.ok) throw new Error("Download failed");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `buyers_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("CSV downloaded");
    } catch {
      toast.error("CSV download failed");
    }
  };

  // Summary numbers based on the current page (server-side total is the
  // authoritative count for "matching" rows).
  const summary = useMemo(() => {
    const revenue = items.reduce((s, b) => s + (b.amount || 0), 0);
    const tickets = items.reduce((s, b) => s + (b.quantity || 0), 0);
    const checkedIn = items.filter((b) => b.checked_in).length;
    return { revenue, tickets, checkedIn };
  }, [items]);

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }

  const hasFilters = eventId || q || fromDate || toDate || status !== "paid";
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <Link to="/organizer" className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: "var(--text-muted)" }} data-testid="back-to-organizer">
        <ArrowLeft className="w-4 h-4" /> Back to dashboard
      </Link>

      <div className="grid md:grid-cols-[1fr_auto] gap-6 items-end mb-10">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Buyers report</div>
          <h1 className="serif text-5xl mb-1">Who bought tickets</h1>
          <p style={{ color: "var(--text-muted)" }}>
            Every paid booking across all your events — searchable, filterable, exportable.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={downloadCsv} className="btn-primary" data-testid="buyers-download-csv-btn">
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </div>

      {/* Summary strip */}
      <div className="grid sm:grid-cols-3 gap-4 mb-6">
        <Stat label="Matching bookings" value={total.toLocaleString()} icon={<Users />} />
        <Stat label="Tickets (this page)" value={summary.tickets.toLocaleString()} />
        <Stat label="Checked in (this page)" value={`${summary.checkedIn}/${items.length}`} icon={<CheckCircle2 />} />
      </div>

      {/* Filter row */}
      <div className="border rounded-2xl p-5 mb-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="grid lg:grid-cols-[2fr_1.5fr_1fr_1fr_auto] gap-3 items-end">
          <div>
            <label className="text-[10px] uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Search</label>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-dim)" }} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Name, email, or booking ID"
                className="w-full pl-9 pr-3 py-2 rounded-lg border bg-transparent text-sm"
                style={{ borderColor: "var(--border)", color: "var(--text)" }}
                data-testid="buyers-search-input"
              />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Event</label>
            <select
              value={eventId}
              onChange={(e) => setEventId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="buyers-event-filter"
            >
              <option value="">All events</option>
              {events.map((e) => (
                <option key={e.event_id} value={e.event_id}>{e.title}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>From</label>
            <input
              type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="buyers-from-date"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>To</label>
            <input
              type="date" value={toDate} onChange={(e) => setToDate(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="buyers-to-date"
            />
          </div>
          <div className="flex gap-2">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="buyers-status-filter"
            >
              <option value="paid">Paid</option>
              <option value="pending">Pending</option>
              <option value="cancelled">Cancelled</option>
              <option value="all">All</option>
            </select>
            {hasFilters && (
              <button onClick={clearFilters} className="btn-ghost !py-2 !px-3" data-testid="buyers-clear-filters">
                <X className="w-4 h-4" /> Clear
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Buyers table */}
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                <th className="text-left p-4">Booked</th>
                <th className="text-left p-4">Buyer</th>
                <th className="text-left p-4">Event</th>
                <th className="text-left p-4">Tier / Seats</th>
                <th className="text-right p-4">Qty</th>
                <th className="text-right p-4">Revenue</th>
                <th className="text-left p-4">Status</th>
                <th className="text-right p-4"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="8" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading buyers…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan="8" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>
                  {hasFilters ? "No buyers match these filters." : "No paid bookings yet."}
                </td></tr>
              ) : items.map((b) => {
                const seats = (b.seats && b.seats.length) ? b.seats.join(", ") : (b.tier_name || "—");
                const when = b.paid_at || b.created_at;
                return (
                  <tr key={b.booking_id} className="border-b hover:bg-[color:var(--bg-elev)] transition" style={{ borderColor: "var(--border)" }} data-testid={`buyer-row-${b.booking_id}`}>
                    <td className="p-4 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                      {when ? new Date(when).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "—"}
                      <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                        {when ? new Date(when).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                      </div>
                    </td>
                    <td className="p-4">
                      <div style={{ color: "var(--text)" }}>{b.user_name || "—"}</div>
                      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{b.user_email}</div>
                    </td>
                    <td className="p-4">
                      <Link to={`/organizer/events/${b.event_id}`} className="hover:underline" style={{ color: "var(--text)" }}>
                        {b.event_title}
                      </Link>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                        {b.event_date ? new Date(b.event_date).toLocaleDateString([], { month: "short", day: "numeric" }) : ""}
                      </div>
                    </td>
                    <td className="p-4 text-xs" style={{ color: "var(--text-muted)" }}>{seats}</td>
                    <td className="p-4 text-right">{b.quantity}</td>
                    <td className="p-4 text-right whitespace-nowrap">{formatMoney(b.amount || 0, b.currency)}</td>
                    <td className="p-4">
                      <StatusChip status={b.status} checkedIn={b.checked_in} />
                    </td>
                    <td className="p-4 text-right">
                      <Link
                        to={`/organizer/events/${b.event_id}#attendees`}
                        className="inline-flex items-center gap-1 text-xs hover:underline"
                        style={{ color: "var(--accent)" }}
                        data-testid={`buyer-open-event-${b.booking_id}`}
                        title="Open event report"
                      >
                        <ExternalLink className="w-3 h-3" /> Open
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between mt-4 text-sm" style={{ color: "var(--text-muted)" }}>
          <div>
            Showing {offset + 1}–{Math.min(offset + items.length, total)} of {total.toLocaleString()}
          </div>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="btn-ghost !py-1.5"
              data-testid="buyers-prev-page"
            >
              Prev
            </button>
            <span className="px-2 py-1">{page} / {totalPages}</span>
            <button
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="btn-ghost !py-1.5"
              data-testid="buyers-next-page"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, icon }) {
  return (
    <div className="border rounded-2xl p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        {icon && <div style={{ color: "var(--accent)" }}>{icon}</div>}
      </div>
      <div className="serif text-3xl" style={{ color: "var(--text)" }}>{value}</div>
    </div>
  );
}

function StatusChip({ status, checkedIn }) {
  if (checkedIn) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs" style={{ background: "rgba(52,211,153,0.12)", color: "var(--success)" }}>
        <CheckCircle2 className="w-3 h-3" /> Checked in
      </span>
    );
  }
  const map = {
    paid: { label: "Paid", color: "var(--accent)", bg: "var(--accent-soft)" },
    pending: { label: "Pending", color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)" },
    cancelled: { label: "Cancelled", color: "var(--danger)", bg: "rgba(239,68,68,0.12)" },
    refunded: { label: "Refunded", color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)" },
  };
  const m = map[status] || { label: status || "—", color: "var(--text-muted)", bg: "transparent" };
  return (
    <span className="inline-flex px-2 py-0.5 rounded-full text-xs" style={{ color: m.color, background: m.bg }}>
      {m.label}
    </span>
  );
}
