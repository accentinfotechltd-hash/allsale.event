import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ArrowLeft, Download, Users, Ticket, TrendingUp, BarChart3, Percent, ScanLine, Bell, Send, Zap, Activity } from "lucide-react";
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
        <div className="flex gap-2 flex-wrap">
          <Link to={`/organizer/events/${eventId}/checkin`} className="btn-ghost" data-testid="open-checkin-btn">
            <ScanLine className="w-4 h-4" /> Door check-in
          </Link>
          <button onClick={downloadCsv} className="btn-primary" data-testid="download-csv-btn">
            <Download className="w-4 h-4" /> Export attendees (CSV)
          </button>
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat label="Revenue" value={`$${totals.revenue.toLocaleString()}`} icon={<TrendingUp />} />
        <Stat label="Tickets sold" value={totals.tickets_sold.toLocaleString()} icon={<Ticket />} />
        <Stat label="Sell-through" value={`${totals.sell_through_pct}%`} sub={`${totals.tickets_sold} / ${totals.capacity}`} icon={<Percent />} />
        <Stat label="Unique attendees" value={totals.unique_attendees.toLocaleString()} icon={<Users />} />
      </div>

      <VelocityWidget eventId={eventId} />

      <div className="grid lg:grid-cols-2 gap-6 mb-8">
        {/* By tier */}
        <Panel title="Revenue by tier" sub="Where the money came from">
          {tiers.length === 0 ? (
            <Empty>No paid tickets yet</Empty>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tiers}>
                  <XAxis dataKey="tier" stroke="#8092A3" fontSize={11} />
                  <YAxis stroke="#8092A3" fontSize={11} />
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8EF", color: "#0F2A3A", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
                    {tiers.map((_, i) => <Cell key={i} fill="#F08A2A" />)}
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
                  <XAxis dataKey="date" stroke="#8092A3" fontSize={11} />
                  <YAxis stroke="#8092A3" fontSize={11} />
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8EF", color: "#0F2A3A", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Line type="monotone" dataKey="revenue" stroke="#F08A2A" strokeWidth={2.5} dot={{ fill: "#F08A2A", r: 3 }} />
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
                  <XAxis type="number" stroke="#8092A3" fontSize={11} />
                  <YAxis type="category" dataKey="code" stroke="#8092A3" fontSize={11} width={80} />
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8EF", color: "#0F2A3A", borderRadius: 8 }} formatter={(v) => `$${v}`} />
                  <Bar dataKey="revenue" radius={[0, 6, 6, 0]}>
                    {codes.map((c, i) => <Cell key={i} fill={c.code === "Direct" ? "#8092A3" : "#F08A2A"} />)}
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

      {/* Waitlist panel */}
      <WaitlistPanel eventId={eventId} />

      {/* Dynamic pricing */}
      <DynamicPricingPanel eventId={eventId} event={event} />
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

const WL_STATUS = {
  waiting: { label: "Waiting", color: "var(--accent)", bg: "var(--accent-soft)" },
  offered: { label: "Offered", color: "var(--success)", bg: "rgba(52,211,153,0.12)" },
  claimed: { label: "Claimed", color: "var(--success)", bg: "rgba(52,211,153,0.12)" },
  expired: { label: "Expired", color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)" },
  cancelled: { label: "Cancelled", color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)" },
};

function WaitlistPanel({ eventId }) {
  const [wl, setWl] = useState(null);
  const [offering, setOffering] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/organizer/events/${eventId}/waitlist`);
      setWl(data);
    } catch { /* event may not have waitlist enabled */ }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [eventId]);

  const offerNext = async () => {
    setOffering(true);
    try {
      const { data } = await api.post(`/organizer/events/${eventId}/waitlist/offer-next`);
      toast.success(`Offered to ${data.user_name} (${data.user_email})`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No one to offer / no capacity");
    } finally { setOffering(false); }
  };

  if (!wl) return null;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Bell className="w-5 h-5" style={{ color: "var(--accent)" }} />
          Waitlist
          {wl.sold_out && <span className="px-2 py-0.5 rounded-full text-xs" style={{ background: "rgba(239,68,68,0.12)", color: "var(--danger)" }}>Sold out</span>}
        </span>
      }
      sub={`${wl.counts.waiting} waiting · ${wl.counts.offered} offered · ${wl.counts.claimed} claimed`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          {wl.counts.waiting > 0
            ? "Click Offer next to release the next held capacity to the head of the queue."
            : "No one waiting yet — the join button appears for attendees once the event is sold out."}
        </div>
        <button onClick={offerNext} disabled={offering || wl.counts.waiting === 0} className="btn-primary" data-testid="offer-next-btn">
          <Send className="w-4 h-4" /> {offering ? "Offering…" : "Offer next"}
        </button>
      </div>

      {wl.items.length === 0 ? (
        <Empty>No waitlist entries yet.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="organizer-waitlist-table">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
                <th className="text-left py-3 text-xs uppercase tracking-widest font-medium">Name</th>
                <th className="text-left py-3 text-xs uppercase tracking-widest font-medium">Email</th>
                <th className="text-left py-3 text-xs uppercase tracking-widest font-medium">Tier pref · Qty</th>
                <th className="text-left py-3 text-xs uppercase tracking-widest font-medium">Joined</th>
                <th className="text-left py-3 text-xs uppercase tracking-widest font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {wl.items.map((e) => {
                const meta = WL_STATUS[e.status] || { label: e.status, color: "var(--text-muted)", bg: "transparent" };
                return (
                  <tr key={e.waitlist_id} className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`waitlist-row-${e.waitlist_id}`}>
                    <td className="py-3">{e.user_name}</td>
                    <td className="py-3" style={{ color: "var(--text-muted)" }}>{e.user_email}</td>
                    <td className="py-3" style={{ color: "var(--text-muted)" }}>{e.tier_preference || "Any"} · {e.quantity}</td>
                    <td className="py-3" style={{ color: "var(--text-muted)" }}>{new Date(e.requested_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</td>
                    <td className="py-3">
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs" style={{ color: meta.color, background: meta.bg }}>
                        {meta.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function DynamicPricingPanel({ eventId, event }) {
  // Initialize from event.dynamic_pricing if present
  const dp = event.dynamic_pricing || {};
  const [enabled, setEnabled] = useState(!!dp.enabled);
  const [threshold, setThreshold] = useState(String(dp.surge_threshold_pct ?? 30));
  const [multiplier, setMultiplier] = useState(String(dp.surge_multiplier ?? 1.2));
  const [saving, setSaving] = useState(false);

  if (event.has_seatmap) return null; // tier-based only for V1

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/organizer/events/${eventId}/dynamic-pricing`, {
        enabled,
        surge_threshold_pct: parseFloat(threshold),
        surge_multiplier: parseFloat(multiplier),
      });
      toast.success(enabled ? "Demand pricing turned on" : "Demand pricing turned off");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || "Failed to save");
    } finally { setSaving(false); }
  };

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Zap className="w-5 h-5" style={{ color: "var(--accent)" }} />
          Demand pricing
          {enabled && <span className="px-2 py-0.5 rounded-full text-xs" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>Active</span>}
        </span>
      }
      sub="Surge tier prices automatically when stock runs low."
    >
      <div className="flex flex-wrap items-center gap-4 mb-5">
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}
            data-testid="dyn-pricing-enabled"
          />
          <span className="text-sm">Enable surge pricing</span>
        </label>
      </div>

      <div className="grid sm:grid-cols-2 gap-5 mb-5">
        <div>
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
            Surge when remaining ≤ ({threshold}%)
          </label>
          <input
            type="range" min="5" max="80" step="5"
            value={threshold} onChange={(e) => setThreshold(e.target.value)}
            disabled={!enabled} className="w-full"
            data-testid="dyn-threshold-slider"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
            Multiplier ({Number(multiplier).toFixed(2)}×)
          </label>
          <input
            type="range" min="1.05" max="2" step="0.05"
            value={multiplier} onChange={(e) => setMultiplier(e.target.value)}
            disabled={!enabled} className="w-full"
            data-testid="dyn-multiplier-slider"
          />
        </div>
      </div>

      <div className="rounded-xl p-4 mb-5 text-sm" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
        Example: a $50 tier becomes <strong style={{ color: "var(--accent)" }}>${(50 * parseFloat(multiplier || 1)).toFixed(2)}</strong> once {threshold}% (or fewer) seats remain.
      </div>

      <button onClick={save} disabled={saving} className="btn-primary" data-testid="save-dyn-pricing-btn">
        {saving ? "Saving…" : "Save"}
      </button>
    </Panel>
  );
}


function VelocityWidget({ eventId }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.get(`/organizer/events/${eventId}/velocity`)
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [eventId]);

  if (!data) return null;

  // Determine accent based on forecast urgency
  const urgent = data.forecast_days !== null && data.forecast_days <= 3;
  const accent = urgent ? "var(--danger)" : data.forecast_days !== null && data.forecast_days <= 14 ? "var(--accent)" : "var(--text-muted)";

  return (
    <div
      className="rounded-2xl p-5 mb-8 flex items-center gap-5 flex-wrap"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
      data-testid="velocity-widget"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: "var(--accent-soft)" }}>
          <Activity className="w-5 h-5" style={{ color: "var(--accent)" }} />
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Sales velocity</div>
          <div className="serif text-2xl" style={{ color: accent }} data-testid="velocity-forecast">{data.forecast_label}</div>
        </div>
      </div>
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm min-w-[280px]">
        <Mini label="Last 24h" value={data.sold_24h} unit="tickets" />
        <Mini label="Last 7d" value={data.sold_7d} unit="tickets" />
        <Mini label="Per hour" value={data.per_hour_24h} unit="/hr" />
        <Mini label="Remaining" value={data.remaining} unit={`of ${data.capacity}`} />
      </div>
    </div>
  );
}

function Mini({ label, value, unit }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-lg">
        <span style={{ color: "var(--text)" }}>{value}</span>{" "}
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{unit}</span>
      </div>
    </div>
  );
}

