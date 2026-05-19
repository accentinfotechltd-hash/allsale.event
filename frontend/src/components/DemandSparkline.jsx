/**
 * DemandSparkline — tiny inline SVG showing 7-day views (bars) + bookings (dots).
 *
 * Use on EventDetail to build FOMO ("this event is trending"). Keeps the
 * footprint small — no chart library needed.
 */
export default function DemandSparkline({ items, height = 36, accent }) {
  if (!items || items.length === 0) return null;
  const maxV = Math.max(1, ...items.map((d) => d.views));
  const maxB = Math.max(1, ...items.map((d) => d.bookings));
  const colW = 100 / items.length;
  const totalViews = items.reduce((s, d) => s + d.views, 0);
  const totalBookings = items.reduce((s, d) => s + d.bookings, 0);
  if (totalViews === 0 && totalBookings === 0) return null;

  return (
    <div data-testid="demand-sparkline" className="space-y-1.5">
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        {items.map((d, i) => {
          const x = i * colW;
          const h = (d.views / maxV) * (height - 6);
          return (
            <rect
              key={i}
              x={x + colW * 0.15}
              y={height - h - 4}
              width={colW * 0.7}
              height={Math.max(1, h)}
              rx="1"
              fill={accent || "var(--accent)"}
              opacity="0.55"
            >
              <title>{`${d.date}: ${d.views} views, ${d.bookings} bookings`}</title>
            </rect>
          );
        })}
        {items.map((d, i) => {
          if (!d.bookings) return null;
          const cx = i * colW + colW / 2;
          const cy = height - 3 - (d.bookings / maxB) * (height - 8);
          return <circle key={`b-${i}`} cx={cx} cy={cy} r="1.4" fill="var(--success)" />;
        })}
      </svg>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
        <span>7-day demand</span>
        <span>
          <span style={{ color: "var(--accent)" }}>{totalViews}</span> views ·{" "}
          <span style={{ color: "var(--success)" }}>{totalBookings}</span> bookings
        </span>
      </div>
    </div>
  );
}
