import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ArrowLeft, Download, Users, Ticket, TrendingUp, BarChart3, Percent } from "lucide-react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function OrganizerEvent() {
  const { eventId } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [attendees, setAttendees] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [a, t] = await Promise.all([
          api.get(`/organizer/events/${eventId}/analytics`),
          api.get(`/organizer/events/${eventId}/attendees`),
        ]);
        setData(a.data);
        setAttendees(t.data);
      } catch (e) {
        toast.error("Could not load event analytics");
      }
    })();
  }, [eventId]);

  const downloadCsv = async () => {
    try {
      const token = localStorage.getItem("aura_token");
      const r = await fetch(`${BACKEND}/api/organizer/events/${eventId}/attendees.csv`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!r.ok) throw new Error("Download failed");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendees_${eventId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("CSV downloaded");
    } catch (e) {
      toast.error("CSV download failed");
    }
  };

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }
  if (!data) return <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>Loading analytics...</div>;

  const { event, totals, tiers, days, hours, codes } = data;
  const maxHourTickets = Math.max(...hours.map(h => h.tickets), 1);

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <Link to="/organizer" className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: "var(--text-muted)" }} data-testid="back-to-organizer">
        <ArrowLeft className="w-4 h-4" /> Back to dashboard
      </Link>

      <div className="grid md:grid-cols-[1fr_auto] gap-6 items-end mb-10">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Event analytics</div>
          <h1 className="serif text-5xl mb-1">{event.title}</h1>
          <p style={{ color: "var(--text-muted)" }}>{event.venue} · {event.city} · {new Date(event.date).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</p>
        </div>
        <button onClick={downloadCsv} className="btn-primary" data-testid="download-csv-btn">
          <Download className="w-4 h-4" /> Export attendees (CSV)
        </button>
      </div>

      {/* KPI grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat label="Revenue" value={`$${totals.revenue.toLocaleString()}`} icon={<TrendingUp />} />
        <Stat label="Tickets sold" value={totals.tickets_sold.toLocaleString()} icon={<Ticket />} />
        <Stat label="Sell-through" value={`${totals.sell_through_pct}%`} sub={`${totals.tickets_sold} / ${totals.capacity}`} icon={<Percent />} />
        <Stat label="Unique attendees" value={totals.unique_attendees.toLocaleString()} icon={<Users />} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-8">
        {/* By tier */}
        <Panel title="Revenue by tier" sub="Where the money came from">
          {tiers.length === 0 ? (
            <Empty>No paid tickets yet</Empty>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tiers}>
                  <XAxis dataKey="tier" stroke="#71717a" fontSize={11} />
                  <YAxis stroke="#71717a" fontSize={11} />
                  <Tooltip contentStyle={{ background: "#17171b", border: "1px solid #26262c", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
                    {tiers.map((_, i) => <Cell key={i} fill="#ff4f00" />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        {/* By day */}
        <Panel title="Revenue by day" sub="When tickets actually got paid">
          {days.length === 0 ? (
            <Empty>No paid tickets yet</Empty>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={days}>
                  <XAxis dataKey="date" stroke="#71717a" fontSize={11} />
                  <YAxis stroke="#71717a" fontSize={11} />
                  <Tooltip contentStyle={{ background: "#17171b", border: "1px solid #26262c", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Line type="monotone" dataKey="revenue" stroke="#ff4f00" strokeWidth={2.5} dot={{ fill: "#ff4f00", r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>

      {/* By hour */}
      <Panel title="When buyers buy" sub="Tickets purchased by hour of day (24h, UTC)">
        <div className="flex items-end gap-1 h-32">
          {hours.map((h) => {
            const heightPct = h.tickets ? (h.tickets / maxHourTickets) * 100 : 2;
            return (
              <div key={h.hour} className="flex-1 flex flex-col items-center gap-1" title={`${h.hour}:00 — ${h.tickets} tickets`}>
                <div className="w-full rounded-t" style={{ height: `${heightPct}%`, background: h.tickets ? "var(--accent)" : "var(--border)" }} />
                <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>{h.hour}</div>
              </div>
            );
          })}
        </div>
      </Panel>

      {/* Revenue by source (discount-code attribution) */}
      <Panel title="Revenue by source" sub="Direct vs promo-code attribution">
        {!codes || codes.length === 0 ? (
          <Empty>No paid bookings yet.</Empty>
        ) : (
          <div className="grid lg:grid-cols-[1fr_1fr] gap-6 items-start">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={codes} layout="vertical" margin={{ left: 60, right: 20, top: 10, bottom: 10 }}>
                  <XAxis type="number" stroke="#71717a" fontSize={11} />
                  <YAxis type="category" dataKey="code" stroke="#71717a" fontSize={11} width={80} />
                  <Tooltip contentStyle={{ background: "#17171b", border: "1px solid #26262c", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Bar dataKey="revenue" radius={[0, 6, 6, 0]}>
                    {codes.map((c, i) => <Cell key={i} fill={c.code === "Direct" ? "#71717a" : "#ff4f00"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                  <th className="text-left py-2">Source</th>
                  <th className="text-right py-2">Tickets</th>
                  <th className="text-right py-2">Revenue</th>
                  <th className="text-right py-2">Discount given</th>
                </tr>
              </thead>
              <tbody>
                {codes.map((c) => (
                  <tr key={c.code} className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`code-row-${c.code}`}>
                    <td className="py-3">
                      {c.code === "Direct" ? (
                        <span style={{ color: "var(--text-muted)" }}>Direct (no code)</span>
                      ) : (
                        <span className="font-mono" style={{ color: "var(--accent)" }}>{c.code}</span>
                      )}
                    </td>
                    <td className="py-3 text-right">{c.tickets}</td>
                    <td className="py-3 text-right">${c.revenue.toLocaleString()}</td>
                    <td className="py-3 text-right" style={{ color: c.discount_given ? "var(--accent)" : "var(--text-dim)" }}>
                      {c.discount_given ? `−$${c.discount_given}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Tier table + capacity */}
      <Panel title="Tier breakdown" sub="Tickets sold and revenue per tier">
        {tiers.length === 0 ? (
          <Empty>No data yet.</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                <th className="text-left py-2">Tier</th>
                <th className="text-right py-2">Tickets</th>
                <th className="text-right py-2">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {tiers.map((t) => (
                <tr key={t.tier} className="border-b" style={{ borderColor: "var(--border)" }}>
                  <td className="py-3">{t.tier}</td>
                  <td className="py-3 text-right">{t.tickets}</td>
                  <td className="py-3 text-right" style={{ color: "var(--accent)" }}>${t.revenue.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Attendees */}
      <Panel title="Attendees" sub={`${attendees.length} confirmed`}>
        {attendees.length === 0 ? (
          <Empty>No attendees yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                  <th className="text-left py-2">Name</th>
                  <th className="text-left py-2">Email</th>
                  <th className="text-left py-2">Tier / Seats</th>
                  <th className="text-right py-2">Qty</th>
                  <th className="text-right py-2">Paid</th>
                </tr>
              </thead>
              <tbody>
                {attendees.slice(0, 50).map((a) => (
                  <tr key={a.booking_id} className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`attendee-${a.booking_id}`}>
                    <td className="py-3">{a.user_name}</td>
                    <td className="py-3" style={{ color: "var(--text-muted)" }}>{a.user_email}</td>
                    <td className="py-3" style={{ color: "var(--text-muted)" }}>{a.seats?.length ? a.seats.join(", ") : a.tier_name}</td>
                    <td className="py-3 text-right">{a.quantity}</td>
                    <td className="py-3 text-right">${a.amount.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {attendees.length > 50 && (
              <div className="text-xs text-center mt-3" style={{ color: "var(--text-dim)" }}>Showing first 50 of {attendees.length}. Use Export CSV for all rows.</div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}

function Stat({ label, value, sub, icon }) {
  return (
    <div className="border rounded-2xl p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        <div style={{ color: "var(--accent)" }}>{icon}</div>
      </div>
      <div className="serif text-3xl" style={{ color: "var(--text)" }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{sub}</div>}
    </div>
  );
}

function Panel({ title, sub, children }) {
  return (
    <div className="border rounded-2xl p-6 mb-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="mb-5">
        <div className="serif text-2xl">{title}</div>
        {sub && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

function Empty({ children }) {
  return <div className="text-center py-12 text-sm" style={{ color: "var(--text-dim)" }}>{children}</div>;
}
