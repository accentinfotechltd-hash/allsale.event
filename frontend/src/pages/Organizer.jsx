import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Plus, TrendingUp, Ticket, Calendar } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function Organizer() {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [analytics, setAnalytics] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [e, a] = await Promise.all([api.get("/organizer/events"), api.get("/organizer/analytics")]);
        setEvents(e.data);
        setAnalytics(a.data);
      } catch { /* noop */ }
    })();
  }, []);

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
        <Link to="/organizer/new" className="btn-primary" data-testid="create-event-btn">
          <Plus className="w-4 h-4" /> Create event
        </Link>
      </div>

      {analytics && (
        <>
          <div className="grid sm:grid-cols-3 gap-4 mb-10">
            <Stat label="Total revenue" value={`$${analytics.total_revenue.toLocaleString()}`} icon={<TrendingUp />} />
            <Stat label="Tickets sold" value={analytics.tickets_sold.toLocaleString()} icon={<Ticket />} />
            <Stat label="Events" value={analytics.events_count} icon={<Calendar />} />
          </div>

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
                    <XAxis dataKey="date" stroke="#71717a" fontSize={11} />
                    <YAxis stroke="#71717a" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#17171b", border: "1px solid #26262c", borderRadius: 8 }} />
                    <Line type="monotone" dataKey="revenue" stroke="#ff4f00" strokeWidth={2.5} dot={false} />
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
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr><td colSpan="5" className="p-8 text-center" style={{ color: "var(--text-dim)" }}>No events yet. Create your first one!</td></tr>
            ) : events.map((e) => {
              const perE = (analytics?.per_event || []).find((x) => x.event_id === e.event_id) || {};
              return (
                <tr key={e.event_id} className="border-b hover:bg-[color:var(--bg-elev)] transition cursor-pointer" style={{ borderColor: "var(--border)" }} data-testid={`org-event-row-${e.event_id}`} onClick={() => window.location.assign(`/organizer/events/${e.event_id}`)}>
                  <td className="p-4">
                    <Link to={`/organizer/events/${e.event_id}`} className="hover:text-[color:var(--accent)]" onClick={(ev) => ev.stopPropagation()}>{e.title}</Link>
                    <div className="text-xs" style={{ color: "var(--text-dim)" }}>{e.venue} · {e.city}</div>
                  </td>
                  <td className="p-4" style={{ color: "var(--text-muted)" }}>{new Date(e.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</td>
                  <td className="p-4"><span className={`chip ${e.status === "approved" ? "chip-accent" : ""}`}>{e.status}</span></td>
                  <td className="p-4 text-right" style={{ color: "var(--text-muted)" }}>{perE.tickets || 0}</td>
                  <td className="p-4 text-right">${(perE.revenue || 0).toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, icon }) {
  return (
    <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        <div style={{ color: "var(--accent)" }}>{icon}</div>
      </div>
      <div className="serif text-4xl" style={{ color: "var(--text)" }}>{value}</div>
    </div>
  );
}
