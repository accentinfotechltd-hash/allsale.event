import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Plus, TrendingUp, Ticket, Calendar, Tag, Wallet, ScanLine, Pencil, Trash2 } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { formatMoney } from "@/lib/currencies";
import DoorCheckinPanel from "@/components/DoorCheckinPanel";
import OrganizerInboxPanel from "@/components/OrganizerInboxPanel";
import StripeConnectPanel from "@/components/StripeConnectPanel";
import OrganizerPayoutsPanel from "@/components/OrganizerPayoutsPanel";
import { toast } from "sonner";

export default function Organizer() {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [e, a] = await Promise.all([api.get("/organizer/events"), api.get("/organizer/analytics")]);
      setEvents(e.data);
      setAnalytics(a.data);
    } catch { /* noop */ } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const deleteEvent = async (e) => {
    if (!window.confirm(`Delete "${e.title}"?\n\nThis permanently removes the event and ALL of its bookings, holds, seat blocks, scanner tokens and team grants. This cannot be undone.`)) return;
    try {
      const { data } = await api.delete(`/events/${e.event_id}`);
      const cascadeTotal = Object.values(data.cascade || {}).reduce((a, b) => a + b, 0);
      toast.success(`Deleted "${data.title}" — cleaned up ${cascadeTotal} related record${cascadeTotal === 1 ? "" : "s"}`);
      load();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Could not delete");
    }
  };

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="flex items-end justify-between mb-10 flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Organizer dashboard</div>
          <h1 className="serif text-5xl">Hello, {user.name.split(" ")[0]}</h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to="/organizer/codes" className="btn-ghost" data-testid="manage-codes-btn">
            <Tag className="w-4 h-4" /> Discount codes
          </Link>
          <Link to="/organizer/payouts" className="btn-ghost" data-testid="manage-payouts-btn">
            <Wallet className="w-4 h-4" /> Payouts
          </Link>
          <Link to="/organizer/new" className="btn-primary" data-testid="create-event-btn">
            <Plus className="w-4 h-4" /> Create event
          </Link>
        </div>
      </div>

      <StripeConnectPanel />

      <OrganizerInboxPanel />

      {analytics && (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-10">
            <Stat label="Total revenue" value={analytics.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })} sub="across all currencies" icon={<TrendingUp />} />
            <Stat label="Tickets sold" value={analytics.tickets_sold.toLocaleString()} icon={<Ticket />} />
            <Stat label="Events" value={analytics.events_count} icon={<Calendar />} />
          </div>

          <DoorCheckinPanel events={events} />

          <div className="border rounded-2xl p-6 mb-10" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Revenue · last 14 days</div>
                <div className="serif text-2xl">Sales trend</div>
              </div>
            </div>
            {analytics.series.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={analytics.series}>
                    <XAxis dataKey="date" stroke="#8092A3" fontSize={11} />
                    <YAxis stroke="#8092A3" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8EF", color: "#0F2A3A", borderRadius: 8 }} />
                    <Line type="monotone" dataKey="revenue" stroke="#F08A2A" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-center py-12" style={{ color: "var(--text-dim)" }}>No sales yet — once you sell tickets, your trend appears here.</div>
            )}
          </div>
        </>
      )}

      <h2 className="serif text-3xl mb-4">My events</h2>
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
              <th className="text-left p-4">Event</th>
              <th className="text-left p-4">Date</th>
              <th className="text-left p-4">Status</th>
              <th className="text-right p-4">Sold</th>
              <th className="text-right p-4">Revenue</th>
              <th className="text-right p-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" className="p-8 text-center" style={{ color: "var(--text-dim)" }}>Loading your events...</td></tr>
            ) : events.length === 0 ? (
              <tr><td colSpan="6" className="p-8 text-center" style={{ color: "var(--text-dim)" }}>No events yet. Create your first one!</td></tr>
            ) : events.map((e) => {
              const perE = (analytics?.per_event || []).find((x) => x.event_id === e.event_id) || {};
              return (
                <tr key={e.event_id} className="border-b hover:bg-[color:var(--bg-elev)] transition" style={{ borderColor: "var(--border)" }} data-testid={`org-event-row-${e.event_id}`}>
                  <td className="p-4">
                    <Link to={`/organizer/events/${e.event_id}`} className="hover:text-[color:var(--accent)]">{e.title}</Link>
                    <div className="text-xs" style={{ color: "var(--text-dim)" }}>{e.venue} · {e.city}</div>
                  </td>
                  <td className="p-4" style={{ color: "var(--text-muted)" }}>{new Date(e.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</td>
                  <td className="p-4"><span className={`chip ${e.status === "approved" ? "chip-accent" : ""}`}>{e.status}</span></td>
                  <td className="p-4 text-right" style={{ color: "var(--text-muted)" }}>{perE.tickets || 0}</td>
                  <td className="p-4 text-right">{formatMoney(perE.revenue || 0, e.currency)}</td>
                  <td className="p-4 text-right">
                    <div className="flex items-center gap-1.5 justify-end flex-wrap">
                      <Link
                        to={`/organizer/events/${e.event_id}/edit`}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs border"
                        style={{ borderColor: "var(--border)", color: "var(--text)" }}
                        data-testid={`edit-event-${e.event_id}`}
                        title="Edit event details"
                      >
                        <Pencil className="w-3 h-3" /> Edit
                      </Link>
                      <button
                        onClick={() => deleteEvent(e)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs border"
                        style={{ borderColor: "var(--border)", color: "var(--danger)" }}
                        data-testid={`delete-event-${e.event_id}`}
                        title="Delete event"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                      <Link
                        to={`/organizer/events/${e.event_id}/checkin`}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium"
                        style={{ background: "var(--accent)", color: "#fff" }}
                        data-testid={`scan-tickets-${e.event_id}`}
                        title="Open the QR scanner for this event"
                      >
                        <ScanLine className="w-3.5 h-3.5" /> Scan
                      </Link>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <OrganizerPayoutsPanel />
    </div>
  );
}

function Stat({ label, value, sub, icon }) {
  return (
    <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        <div style={{ color: "var(--accent)" }}>{icon}</div>
      </div>
      <div className="serif text-4xl" style={{ color: "var(--text)" }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{sub}</div>}
    </div>
  );
}
