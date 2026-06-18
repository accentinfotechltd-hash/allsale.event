/**
 * SeatMap — public theatre seat picker.
 *
 * Props now support optional theatre-style enhancements:
 *  - sections: [{after_row, label}]
 *  - curved: bool
 *  - backdropOpacity, backdropOffsetY
 *
 * Defaults preserve the original flat-grid behaviour, so existing events
 * continue to render unchanged.
 */
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export default function SeatMap({
  rows,
  cols,
  booked = [],
  held = [],
  selected = [],
  aisles = [],
  sections = [],
  categories = {},  // {wheelchair: ["A-1"], house: [...], disabled: [...], vip: [...], premium: [...]}
  curved = false,
  numberingRtl = false,  // cinemas in India/ME often number seats right→left
  backdropUrl = null,
  backdropOpacity = 0.4,
  backdropOffsetY = 0,
  backdropOffsetX = 0,
  backdropScale = 1,
  onToggle,
}) {
  const aisleSet = new Set(aisles || []);
  const sectionMap = new Map((sections || []).map((s) => [s.after_row, s.label]));
  // Flatten categories into a lookup so each seat render is O(1)
  const seatCategory = new Map();
  Object.entries(categories || {}).forEach(([cat, ids]) => {
    (ids || []).forEach((id) => seatCategory.set(id, cat));
  });
  const CAT_COLOR = {
    wheelchair: "#1E88E5",
    disabled: "#4CAF50",
    house: "#FFD600",
    vip: "#9C27B0",
    premium: "#F08A2A",
  };

  const curveOffset = (r, c) => {
    if (!curved) return 0;
    const center = (cols - 1) / 2;
    const dx = c - center;
    const rowFactor = 0.45 + (r / Math.max(rows - 1, 1)) * 0.55;
    return Math.round((dx * dx) * 0.18 * rowFactor);
  };

  return (
    <div className="space-y-4 relative">
      {backdropUrl && (
        <div
          className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden"
          style={{
            opacity: backdropOpacity,
            transform: `translate(${backdropOffsetX}px, ${backdropOffsetY}px) scale(${backdropScale})`,
            transformOrigin: "center center",
          }}
        >
          <img src={backdropUrl} alt="" className="w-full h-full" style={{ objectFit: "contain" }} />
        </div>
      )}

      <div className="relative z-10 stage-arc" />
      <div className="relative z-10 text-center text-xs uppercase tracking-[0.3em]" style={{ color: "var(--text-dim)" }}>Stage</div>

      <div className="relative z-10 flex flex-col items-center gap-2 overflow-x-auto pb-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="w-full flex flex-col items-center gap-2">
            <div className="flex items-center gap-1.5">
              <div className="w-6 text-xs font-mono text-center" style={{ color: "var(--text-dim)" }}>{LETTERS[r]}</div>
              {Array.from({ length: cols }).map((_, c) => {
                // If RTL numbering is on, the visual column from the left
                // (c=0) maps to seat number `cols` and decreases — so seat #1
                // is the rightmost seat (matches Indian/ME cinema convention).
                const seatNumber = numberingRtl ? cols - c : c + 1;
                const id = `${LETTERS[r]}-${seatNumber}`;
                if (aisleSet.has(id)) {
                  return <div key={id} className="w-7 h-7" aria-hidden="true" />;
                }
                const isBooked = booked.includes(id);
                const isHeld = held.includes(id);
                const isSelected = selected.includes(id);
                const cat = seatCategory.get(id);
                const cls = isSelected
                  ? "seat seat-selected"
                  : isBooked
                  ? "seat seat-booked"
                  : isHeld
                  ? "seat seat-held"
                  : "seat";
                const dy = curveOffset(r, c);
                // If the seat has a category and isn't already in a special
                // state, tint it so customers know it's e.g. wheelchair / VIP.
                const styleExtra = (cat && !isBooked && !isHeld && !isSelected)
                  ? { background: CAT_COLOR[cat], borderColor: CAT_COLOR[cat] }
                  : {};
                return (
                  <button
                    key={id}
                    type="button"
                    className={cls}
                    style={{ ...(dy ? { transform: `translateY(${dy}px)` } : {}), ...styleExtra }}
                    disabled={isBooked || isHeld}
                    onClick={() => onToggle && onToggle(id)}
                    aria-label={`Seat ${id}${cat ? ` (${cat})` : ""}`}
                    title={cat ? `${id} — ${cat}` : id}
                    data-testid={`seat-${id}`}
                  />
                );
              })}
              <div className="w-6 text-xs font-mono text-center" style={{ color: "var(--text-dim)" }}>{LETTERS[r]}</div>
            </div>

            {sectionMap.has(r) && r < rows - 1 && (
              <div className="w-full max-w-md relative mt-1 mb-1">
                <div className="h-px" style={{ background: "var(--accent)", height: 2 }} />
                <span
                  className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
                  style={{ background: "var(--bg-card)", color: "var(--accent)", border: "1px solid var(--accent)" }}
                  data-testid={`section-label-${LETTERS[r]}`}
                >
                  {sectionMap.get(r)}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="relative z-10 flex items-center justify-center gap-5 text-xs flex-wrap pt-2" style={{ color: "var(--text-muted)" }}>
        <div className="flex items-center gap-2"><div className="seat" style={{ width: 16, height: 16 }} /> Available</div>
        <div className="flex items-center gap-2"><div className="seat seat-selected" style={{ width: 16, height: 16 }} /> Selected</div>
        <div className="flex items-center gap-2"><div className="seat seat-held" style={{ width: 16, height: 16 }} /> On hold</div>
        <div className="flex items-center gap-2"><div className="seat seat-booked" style={{ width: 16, height: 16 }} /> Booked</div>
        {aisleSet.size > 0 && <div className="flex items-center gap-2"><div className="w-4 h-4 border border-dashed" style={{ borderColor: "var(--border-strong)" }} /> Aisle</div>}
      </div>
    </div>
  );
}
