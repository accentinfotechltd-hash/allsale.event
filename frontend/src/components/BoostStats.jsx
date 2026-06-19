/**
 * BoostStats — small inline widget under boosted events on the organizer
 * dashboard. Shows the +views and +bookings the active (or most recent)
 * Boost actually delivered, so organizers can self-justify the spend.
 *
 * Fetches /api/organizer/events/{id}/boost/stats on mount. Hides silently
 * if the event was never boosted, the data is too thin to compute a
 * meaningful lift, or if the API errors out.
 */
import { useEffect, useState } from "react";
import { Flame, TrendingUp, TrendingDown, Eye, Ticket } from "lucide-react";
import api from "@/lib/api";

function LiftPill({ value, label, icon: Icon }) {
  if (value === null || value === undefined) return null;
  const up = value > 0;
  const Arrow = up ? TrendingUp : TrendingDown;
  const color = up ? "#2ECC71" : value < 0 ? "#E74C3C" : "var(--text-muted)";
  return (
    <div className="inline-flex items-center gap-1.5 text-xs">
      <Icon className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <Arrow className="w-3 h-3" style={{ color }} />
      <span style={{ color, fontWeight: 600 }}>
        {value > 0 ? "+" : ""}
        {value}%
      </span>
    </div>
  );
}

export default function BoostStats({ eventId }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get(`/organizer/events/${eventId}/boost/stats`)
      .then(({ data }) => !cancelled && setStats(data))
      .catch(() => !cancelled && setStats(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  if (loading || !stats || !stats.boosted) return null;

  const tierLabel = stats.boost_kind === "paid" ? `Paid ${stats.boost_tier || ""}`.trim() : "Free boost";
  const activeOrPast = stats.is_active ? "Live now" : "Last boost";

  return (
    <div
      className="rounded-lg p-2.5 mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5"
      style={{ background: "var(--bg-elev)", border: "1px dashed var(--border)" }}
      data-testid={`boost-stats-${eventId}`}
    >
      <div className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
        <Flame className="w-3 h-3" /> {activeOrPast} · {tierLabel}
      </div>
      <LiftPill value={stats.view_lift_pct} label="Views" icon={Eye} />
      <LiftPill value={stats.booking_lift_pct} label="Bookings" icon={Ticket} />
      <div className="text-[10px] ml-auto" style={{ color: "var(--text-dim)" }}>
        {stats.during_views} views · {stats.during_bookings} bookings during Boost
      </div>
    </div>
  );
}
